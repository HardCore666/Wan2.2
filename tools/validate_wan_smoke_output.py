#!/usr/bin/env python3
"""Validate and normalize ffprobe metadata for a Wan2.2 smoke output."""

from __future__ import annotations

import argparse
import json
import math
from fractions import Fraction
from pathlib import Path
from typing import Any

DEFAULT_EXPECTED_FPS = 16.0
FPS_TOLERANCE = 0.01
DEFAULT_ALLOWED_CODECS = frozenset({"h264"})


def parse_size(value: str) -> tuple[int, int]:
    try:
        width_text, height_text = value.split("*", 1)
        width, height = int(width_text), int(height_text)
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"invalid size, expected WIDTH*HEIGHT: {value!r}") from exc
    if width <= 0 or height <= 0:
        raise ValueError(f"invalid non-positive size: {value!r}")
    return width, height


def positive_float(value: Any, field: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} is not numeric: {value!r}") from exc
    if not math.isfinite(parsed) or parsed <= 0:
        raise ValueError(f"{field} must be positive: {value!r}")
    return parsed


def parse_fps(value: Any) -> float:
    if isinstance(value, str) and "/" in value:
        try:
            parsed = float(Fraction(value))
        except (ValueError, ZeroDivisionError) as exc:
            raise ValueError(f"invalid avg_frame_rate: {value!r}") from exc
    else:
        parsed = positive_float(value, "avg_frame_rate")
    if not math.isfinite(parsed) or parsed <= 0:
        raise ValueError(f"avg_frame_rate must be positive: {value!r}")
    return parsed


def parse_allowed_codecs(value: Any) -> frozenset[str]:
    if isinstance(value, str):
        candidates = value.split(",")
    else:
        candidates = value
    codecs = {str(item).strip().lower() for item in candidates if str(item).strip()}
    if not codecs:
        raise ValueError("allowed codec set must be non-empty")
    return frozenset(codecs)


def optional_frame_count(stream: dict[str, Any]) -> tuple[int | None, str | None]:
    for field in ("nb_read_frames", "nb_frames"):
        value = stream.get(field)
        if value in (None, "", "N/A"):
            continue
        try:
            count = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid {field}: {value!r}") from exc
        if count <= 0:
            raise ValueError(f"{field} must be positive: {value!r}")
        return count, field
    return None, None


def expand_normalized_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Turn our compact normalized object back into ffprobe-like input.

    This keeps ``--write-normalized`` idempotent: a normalized metadata file
    remains a valid input to the same validator without retaining a path string
    or requiring a second ffprobe invocation.
    """
    if "format" in metadata:
        return metadata
    compact_video = metadata.get("video")
    if not isinstance(compact_video, dict):
        return metadata
    if not {"format_name", "duration", "size"}.issubset(metadata):
        return metadata
    stream: dict[str, Any] = {
        "index": compact_video.get("index"),
        "codec_type": compact_video.get("codec_type"),
        "codec_name": compact_video.get("codec_name"),
        "width": compact_video.get("width"),
        "height": compact_video.get("height"),
        "avg_frame_rate": compact_video.get("avg_frame_rate"),
    }
    if compact_video.get("frame_count") is not None:
        stream["nb_read_frames"] = compact_video["frame_count"]
    return {
        "format": {
            "format_name": metadata["format_name"],
            "duration": metadata["duration"],
            "size": metadata["size"],
        },
        "streams": [stream],
    }


def validate_metadata(
    metadata: dict[str, Any],
    expected_width: int,
    expected_height: int,
    expected_frames: int,
    expected_fps: float = DEFAULT_EXPECTED_FPS,
    allowed_codecs: Any = DEFAULT_ALLOWED_CODECS,
) -> dict[str, Any]:
    expected_fps = positive_float(expected_fps, "expected_fps")
    allowed_codecs = parse_allowed_codecs(allowed_codecs)
    metadata = expand_normalized_metadata(metadata)
    format_data = metadata.get("format")
    if not isinstance(format_data, dict):
        raise ValueError("ffprobe metadata lacks format object")
    required_format = ("format_name", "duration", "size")
    missing = [field for field in required_format if field not in format_data]
    if missing:
        raise ValueError(f"ffprobe format missing fields: {', '.join(missing)}")
    format_name = str(format_data["format_name"])
    if "mp4" not in {part.strip().lower() for part in format_name.split(",")}:
        raise ValueError(f"container is not MP4: {format_name!r}")
    duration = positive_float(format_data["duration"], "duration")
    try:
        size = int(format_data["size"])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"format size is not an integer: {format_data['size']!r}") from exc
    if size <= 0:
        raise ValueError(f"format size must be positive: {size}")

    streams = metadata.get("streams")
    if not isinstance(streams, list):
        raise ValueError("ffprobe metadata lacks streams list")
    video_stream = next(
        (
            stream
            for stream in streams
            if isinstance(stream, dict) and stream.get("codec_type") == "video"
        ),
        None,
    )
    if video_stream is None:
        raise ValueError("ffprobe metadata has no video stream")
    for field in ("codec_type", "codec_name", "width", "height", "avg_frame_rate"):
        if field not in video_stream:
            raise ValueError(f"video stream missing field: {field}")
    try:
        width, height = int(video_stream["width"]), int(video_stream["height"])
    except (TypeError, ValueError) as exc:
        raise ValueError("video width/height are not integers") from exc
    if width != expected_width or height != expected_height:
        raise ValueError(
            f"video dimensions mismatch: got {width}x{height}, "
            f"expected {expected_width}x{expected_height}"
        )
    codec_name = str(video_stream["codec_name"]).strip().lower()
    if not codec_name:
        raise ValueError("video codec_name must be non-empty")
    if codec_name not in allowed_codecs:
        raise ValueError(
            f"unsupported video codec {codec_name!r}; "
            f"allowed: {', '.join(sorted(allowed_codecs))}"
        )
    fps = parse_fps(video_stream["avg_frame_rate"])
    if abs(fps - expected_fps) > FPS_TOLERANCE:
        raise ValueError(
            f"video fps mismatch: got {fps:.6f}, expected {expected_fps:.6f} "
            f"+/- {FPS_TOLERANCE:.2f}"
        )
    frame_count, frame_count_source = optional_frame_count(video_stream)
    if frame_count is not None:
        if frame_count != expected_frames:
            raise ValueError(
                f"frame count mismatch: got {frame_count}, expected {expected_frames}"
            )
    else:
        estimated_frames = duration * fps
        tolerance = max(2.0, expected_frames * 0.08)
        if abs(estimated_frames - expected_frames) > tolerance:
            raise ValueError(
                f"estimated frame count mismatch: got {estimated_frames:.2f}, "
                f"expected {expected_frames} +/- {tolerance:.2f}"
            )

    return {
        "format_name": format_name,
        "duration": duration,
        "size": size,
        "video": {
            "index": video_stream.get("index"),
            "codec_type": video_stream["codec_type"],
            "codec_name": codec_name,
            "width": width,
            "height": height,
            "avg_frame_rate": str(video_stream["avg_frame_rate"]),
            "fps": fps,
            "frame_count": frame_count,
            "frame_count_source": frame_count_source or "duration_times_fps",
        },
    }


def validate_video(
    video: Path,
    metadata_path: Path,
    size: str,
    frame_num: int,
    expected_fps: float = DEFAULT_EXPECTED_FPS,
    allowed_codecs: Any = DEFAULT_ALLOWED_CODECS,
) -> dict[str, Any]:
    if video.suffix.lower() != ".mp4":
        raise ValueError(f"video output must use .mp4: {video}")
    if not video.is_file() or video.stat().st_size <= 0:
        raise ValueError(f"video output is missing or empty: {video}")
    if not metadata_path.is_file() or metadata_path.stat().st_size <= 0:
        raise ValueError(f"ffprobe metadata is missing or empty: {metadata_path}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8-sig"))
    width, height = parse_size(size)
    normalized = validate_metadata(
        metadata,
        width,
        height,
        frame_num,
        expected_fps=expected_fps,
        allowed_codecs=allowed_codecs,
    )
    return {"video": str(video), "metadata_path": str(metadata_path), "ffprobe": normalized}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--size", required=True)
    parser.add_argument("--frame-num", required=True, type=int)
    parser.add_argument("--expected-fps", type=float, default=DEFAULT_EXPECTED_FPS)
    parser.add_argument(
        "--allowed-codecs",
        default=",".join(sorted(DEFAULT_ALLOWED_CODECS)),
        help="comma-separated ffprobe codec_name allowlist",
    )
    parser.add_argument("--write-normalized", action="store_true")
    args = parser.parse_args()
    normalized = validate_video(
        args.video,
        args.metadata,
        args.size,
        args.frame_num,
        expected_fps=args.expected_fps,
        allowed_codecs=args.allowed_codecs,
    )
    if args.write_normalized:
        args.metadata.write_text(
            json.dumps(normalized["ffprobe"], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(normalized, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()

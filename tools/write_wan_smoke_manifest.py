#!/usr/bin/env python3
"""Write a reproducible manifest for a Wan2.2 T2V smoke run.

This tool intentionally uses only the Python standard library. It hashes the
tracked source and an explicit task-file allowlist, never arbitrary untracked
files or the large model weights.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


TASK_FILE_ALLOWLIST = (
    ".gitignore",
    "scripts/setup_wan22_env_pack.sh",
    "scripts/run_t2v_smoke.sh",
    "scripts/download_wan22_t2v_a14b.sh",
    "tools/write_wan_smoke_manifest.py",
    "tools/validate_wan_smoke_output.py",
    "tools/audit_wan22_required_files.py",
    "tools/wan22_modelscope_snapshot.py",
    "tools/wan22_modelscope_api_snapshot.json",
    "tools/wan22_t2v_a14b_modelscope_required_files.tsv",
    "requirements.txt",
    "prompts/t2v_smoke_prompts.tsv",
    "tests/test_wan_lazy_import.py",
    "tests/test_wan_smoke_tools.py",
    "tests/test_wan22_wrappers.py",
)
PROMPT_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
FPS_TOLERANCE = 0.01
PROD_MODEL_REPO_ID = "Wan-AI/Wan2.2-T2V-A14B"
PROD_MODEL_SOURCE = "modelscope"
PROD_MODEL_REVISION = "master"


def run_git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


def run_git_bytes(repo: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_allowed_codecs(value: str) -> list[str]:
    codecs = sorted({item.strip().lower() for item in value.split(",") if item.strip()})
    if not codecs:
        raise ValueError("allowed codec set must be non-empty")
    return codecs


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def source_identity(repo: Path) -> dict[str, object]:
    head = run_git(repo, "rev-parse", "HEAD")
    status = run_git(repo, "status", "--porcelain=v1")
    tracked_paths = [
        path
        for path in run_git_bytes(repo, "ls-files", "-z")
        .decode("utf-8", "surrogateescape")
        .split("\0")
        if path
    ]
    untracked_paths = [
        path
        for path in run_git_bytes(repo, "ls-files", "--others", "--exclude-standard", "-z")
        .decode("utf-8", "surrogateescape")
        .split("\0")
        if path
    ]

    tracked_digest = hashlib.sha256()
    tracked_files: list[dict[str, object]] = []
    for relative in sorted(tracked_paths):
        path = repo / relative
        if not path.is_file():
            continue
        file_hash = sha256_file(path)
        tracked_digest.update(relative.encode("utf-8") + b"\0" + file_hash.encode("ascii"))
        tracked_files.append(
            {"path": relative, "sha256": file_hash, "bytes": path.stat().st_size}
        )

    task_files: list[dict[str, object]] = []
    for relative in TASK_FILE_ALLOWLIST:
        path = repo / relative
        if path.is_file():
            task_files.append(
                {"path": relative, "sha256": sha256_file(path), "bytes": path.stat().st_size}
            )

    diff_hash = sha256_bytes(run_git_bytes(repo, "diff", "--binary", "HEAD"))
    identity_payload = json.dumps(
        {
            "head": head,
            "tracked_manifest_sha256": tracked_digest.hexdigest(),
            "diff_sha256": diff_hash,
            "task_files": task_files,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "head": head,
        "status": status,
        "dirty": bool(status),
        "tracked_manifest_sha256": tracked_digest.hexdigest(),
        "diff_sha256": diff_hash,
        "manifest_sha256": sha256_bytes(identity_payload),
        "tracked_files": tracked_files,
        "task_file_allowlist": list(TASK_FILE_ALLOWLIST),
        "task_files": task_files,
        "untracked_non_allowlist": sorted(
            path for path in untracked_paths if path not in TASK_FILE_ALLOWLIST
        ),
    }


def model_inventory(model_dir: Path) -> dict[str, object]:
    files: list[dict[str, object]] = []
    total_bytes = 0
    sidecars: list[dict[str, object]] = []
    if model_dir.is_dir():
        for path in sorted(model_dir.rglob("*")):
            if not path.is_file():
                continue
            stat = path.stat()
            relative = str(path.relative_to(model_dir)).replace(os.sep, "/")
            item = {"path": relative, "bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns}
            files.append(item)
            total_bytes += stat.st_size
            if path.name.endswith((".sha256", ".sha256sum", "SHA256SUMS", "sha256sums.txt")):
                sidecars.append({**item, "sha256": sha256_file(path)})
    return {
        "directory": str(model_dir),
        "total_bytes": total_bytes,
        "files": files,
        "official_sha256_sidecars": sidecars,
    }


def validate_prompt_id(prompt_id: str, path: Path, line_number: int) -> None:
    if prompt_id in {".", ".."} or not PROMPT_ID_RE.fullmatch(prompt_id):
        raise ValueError(f"invalid prompt id {prompt_id!r} at {path}:{line_number}")


def read_prompts(path: Path) -> list[dict[str, object]]:
    prompts = []
    seen: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split("\t", 2)
        if len(parts) != 3 or not parts[0] or not parts[1].isdigit() or not parts[2]:
            raise ValueError(f"invalid prompt row {path}:{line_number}")
        prompt_id, seed, prompt = parts
        validate_prompt_id(prompt_id, path, line_number)
        if prompt_id in seen:
            raise ValueError(f"duplicate prompt id {prompt_id!r} at {path}:{line_number}")
        seen.add(prompt_id)
        prompts.append({"id": prompt_id, "seed": int(seed), "prompt": prompt})
    return prompts


def ensure_under(path: Path, root: Path, label: str) -> Path:
    resolved_root = root.resolve(strict=False)
    resolved_path = path.resolve(strict=False)
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"{label} escapes {resolved_root}: {resolved_path}") from exc
    return resolved_path


def environment_report() -> dict[str, object]:
    names = (
        "torch",
        "torchvision",
        "flash-attn",
        "einops",
        "decord",
        "transformers",
        "diffusers",
        "accelerate",
        "imageio-ffmpeg",
        "easydict",
        "markupsafe",
    )
    versions: dict[str, str] = {}
    for name in names:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "missing"
    return {
        "python": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "packages": versions,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--model-repo-id", default=PROD_MODEL_REPO_ID)
    parser.add_argument("--model-revision", default=PROD_MODEL_REVISION)
    parser.add_argument("--model-source", default=PROD_MODEL_SOURCE)
    parser.add_argument("--prompts", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--status", required=True)
    parser.add_argument("--exit-code", type=int)
    parser.add_argument("--started-utc")
    parser.add_argument("--ended-utc")
    parser.add_argument("--host")
    parser.add_argument("--container")
    parser.add_argument("--environment-python")
    parser.add_argument("--torchrun")
    parser.add_argument("--command-log", type=Path)
    parser.add_argument("--num-gpus", type=int, default=8)
    parser.add_argument("--size", default="832*480")
    parser.add_argument("--frame-num", type=int, default=81)
    parser.add_argument("--sample-steps", type=int, default=40)
    parser.add_argument("--expected-fps", type=float, default=16.0)
    parser.add_argument("--allowed-codecs", default="h264")
    parser.add_argument("--test-mode", choices=("0", "1"), default="0")
    parser.add_argument("--selected-prompt-id", action="append", default=[])
    parser.add_argument("--max-prompts", type=int)
    parser.add_argument("--output-file", action="append", default=[])
    return parser.parse_args()


def output_record(path: Path, run_root: Path) -> dict[str, object]:
    video_root = run_root / "videos"
    metadata_root = run_root / "metadata"
    ensure_under(path, video_root, "video output")
    metadata_path = ensure_under(
        metadata_root / f"{path.stem}.json", metadata_root, "metadata output"
    )
    item: dict[str, object] = {"path": str(path)}
    if path.is_file():
        item["bytes"] = path.stat().st_size
        item["sha256"] = sha256_file(path)
    item["metadata_path"] = str(metadata_path)
    try:
        if not metadata_path.is_file():
            raise OSError(f"metadata file is missing: {metadata_path}")
        metadata_text = metadata_path.read_text(encoding="utf-8-sig")
        if not metadata_text.strip():
            raise ValueError(f"metadata file is empty: {metadata_path}")
        metadata = json.loads(metadata_text)
        if not isinstance(metadata, dict):
            raise ValueError(f"ffprobe metadata must be a JSON object: {metadata_path}")
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        item["ffprobe"] = None
        item["metadata_error"] = f"{type(exc).__name__}: {exc}"
    else:
        item["ffprobe"] = metadata
    return item


def main() -> None:
    args = parse_args()
    prompts = read_prompts(args.prompts)
    if args.max_prompts is not None and args.max_prompts <= 0:
        raise ValueError("max prompts must be positive")
    if len(set(args.selected_prompt_id)) != len(args.selected_prompt_id):
        raise ValueError("selected prompt ids must be unique")
    prompts_by_id = {str(item["id"]): item for item in prompts}
    if args.selected_prompt_id:
        missing = [item for item in args.selected_prompt_id if item not in prompts_by_id]
        if missing:
            raise ValueError(f"selected prompt ids are not in prompts file: {missing}")
        selected_prompts = [prompts_by_id[item] for item in args.selected_prompt_id]
    else:
        selected_prompts = prompts[: args.max_prompts] if args.max_prompts else prompts
    if args.max_prompts is not None and len(selected_prompts) > args.max_prompts:
        raise ValueError("selected prompts exceed max prompts")
    selected_prompt_ids = [str(item["id"]) for item in selected_prompts]
    effective_max_prompts = args.max_prompts if args.max_prompts is not None else len(selected_prompts)
    if args.test_mode == "0" and (
        args.model_repo_id != PROD_MODEL_REPO_ID
        or args.model_source != PROD_MODEL_SOURCE
        or args.model_revision != PROD_MODEL_REVISION
    ):
        raise ValueError(
            "production model identity must be ModelScope Wan-AI/Wan2.2-T2V-A14B@master"
        )
    if args.expected_fps <= 0:
        raise ValueError(f"expected fps must be positive: {args.expected_fps}")
    allowed_codecs = parse_allowed_codecs(args.allowed_codecs)
    manifest = {
        "schema": "wan2.2.t2v.smoke.v2",
        "run_id": args.run_id,
        "status": args.status,
        "test_mode": args.test_mode == "1",
        "exit_code": args.exit_code,
        "started_utc": args.started_utc or utc_now(),
        "ended_utc": args.ended_utc,
        "host": args.host,
        "container": args.container,
        "environment": {
            "python": args.environment_python,
            "torchrun": args.torchrun,
            "num_gpus": args.num_gpus,
            "report": environment_report(),
        },
        "source": source_identity(args.repo),
        "model": {
            "repository_id": args.model_repo_id,
            "revision": args.model_revision,
            "source": args.model_source,
            **model_inventory(args.model_dir),
        },
        "inputs": {
            "prompts_file": str(args.prompts),
            "available_prompt_count": len(prompts),
            "selected_prompt_ids": selected_prompt_ids,
            "max_prompts": effective_max_prompts,
            "prompts": selected_prompts,
        },
        "generation": {
            "task": "t2v-A14B",
            "size": args.size,
            "frame_num": args.frame_num,
            "sample_steps": args.sample_steps,
            "fps": args.expected_fps,
            "fps_tolerance": FPS_TOLERANCE,
            "allowed_codecs": allowed_codecs,
            "solver": "unipc",
            "shift": 12.0,
            "guide_scale": [3.0, 4.0],
            "prompt_extension": False,
            "convert_model_dtype": False,
            "offload_model": False,
            "distributed": "torchrun + DiT FSDP + T5 FSDP + Ulysses",
        },
        "run_root": str(args.run_root),
        "outputs": [output_record(Path(path), args.run_root) for path in args.output_file],
    }
    if args.command_log:
        command_log = args.command_log
        manifest["command_log"] = {
            "path": str(command_log),
            "sha256": sha256_file(command_log) if command_log.is_file() else None,
            "argv": command_log.read_text(encoding="utf-8").splitlines()
            if command_log.is_file()
            else [],
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()

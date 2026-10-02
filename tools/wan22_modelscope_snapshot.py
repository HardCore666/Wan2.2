#!/usr/bin/env python3
"""Validate a sanitized ModelScope file-list snapshot.

The snapshot is intentionally an offline artifact.  It records the exact
client-visible response used to derive the production manifest, without
cookies, request IDs, or other transport metadata.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any


MODEL_ID = "Wan-AI/Wan2.2-T2V-A14B"
REVISION = "master"
EXPECTED_COUNT = 32
EXPECTED_TOTAL_BYTES = 126201624156
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def load_snapshot(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("snapshot root must be a JSON object")
    return payload


def validate_snapshot(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if payload.get("source") != "modelscope":
        raise ValueError("snapshot source must be modelscope")
    query = payload.get("query")
    if not isinstance(query, dict):
        raise ValueError("snapshot query metadata is missing")
    if query.get("method") != "HubApi.get_model_files":
        raise ValueError("snapshot query method is not HubApi.get_model_files")
    if query.get("model_id") != MODEL_ID or query.get("revision") != REVISION:
        raise ValueError("snapshot model or revision mismatch")
    if query.get("recursive") is not True:
        raise ValueError("snapshot must come from recursive=true")
    sdk = payload.get("sdk")
    if not isinstance(sdk, dict) or not sdk.get("version"):
        raise ValueError("snapshot SDK version is missing")
    items = payload.get("items")
    if not isinstance(items, list):
        raise ValueError("snapshot items must be a list")
    if len(items) != EXPECTED_COUNT:
        raise ValueError(f"snapshot item count mismatch: {len(items)}")
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(items, 1):
        if not isinstance(item, dict):
            raise ValueError(f"snapshot item {index} is not an object")
        path = item.get("Path")
        if not isinstance(path, str) or not path:
            raise ValueError(f"snapshot item {index} has invalid Path")
        candidate = PurePosixPath(path)
        if candidate.is_absolute() or ".." in candidate.parts or "\\" in path:
            raise ValueError(f"unsafe snapshot path: {path!r}")
        if path in seen:
            raise ValueError(f"duplicate snapshot path: {path!r}")
        seen.add(path)
        if item.get("Type") not in {"blob", "file"}:
            raise ValueError(f"snapshot item {path!r} is not a file blob")
        try:
            size = int(item["Size"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid snapshot size for {path!r}") from exc
        if size < 0:
            raise ValueError(f"negative snapshot size for {path!r}")
        sha256 = item.get("Sha256")
        if not isinstance(sha256, str) or not SHA256_RE.fullmatch(sha256):
            raise ValueError(f"invalid snapshot Sha256 for {path!r}")
        # ModelScope returns the commit revision for each blob while the
        # request itself is made against the ``master`` branch.
        item_revision = item.get("Revision")
        if not isinstance(item_revision, str) or not item_revision:
            raise ValueError(f"snapshot item revision is missing for {path!r}")
        normalized.append({"path": path, "size": size, "sha256": sha256.lower()})
    total = sum(int(item["size"]) for item in normalized)
    if total != EXPECTED_TOTAL_BYTES:
        raise ValueError(f"snapshot byte total mismatch: {total}")
    if payload.get("blob_count") != EXPECTED_COUNT:
        raise ValueError("snapshot blob_count mismatch")
    if payload.get("expected_total_bytes") != EXPECTED_TOTAL_BYTES:
        raise ValueError("snapshot expected_total_bytes mismatch")
    return sorted(normalized, key=lambda item: str(item["path"]))


def manifest_rows(payload: dict[str, Any]) -> list[tuple[str, int]]:
    return [(str(item["path"]), int(item["size"])) for item in validate_snapshot(payload)]


def manifest_rows_from_tsv(path: Path) -> list[tuple[str, int]]:
    rows: list[tuple[str, int]] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        relative, size = line.split("\t", 1)
        rows.append((relative, int(size)))
    return sorted(rows)


def snapshot_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    payload = load_snapshot(args.snapshot)
    rows = manifest_rows(payload)
    if args.manifest:
        expected = manifest_rows_from_tsv(args.manifest)
        if rows != expected:
            raise SystemExit("snapshot rows differ from required manifest")
    print(
        json.dumps(
            {
                "snapshot": str(args.snapshot),
                "snapshot_sha256": snapshot_sha256(args.snapshot),
                "count": len(rows),
                "total_bytes": sum(size for _, size in rows),
                "manifest_match": args.manifest is not None,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

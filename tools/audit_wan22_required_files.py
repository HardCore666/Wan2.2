#!/usr/bin/env python3
"""Audit a downloaded Wan2.2 model against the official required-file TSV."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from pathlib import Path, PurePosixPath


ALLOWED_METADATA_FILES = frozenset(
    {
        ".wan22_t2v_a14b.identity",
        ".wan22_t2v_a14b.complete",
        ".wan22_t2v_a14b.inventory.json",
    }
)


def load_required_files(path: Path) -> dict[str, int]:
    required: dict[str, int] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) != 2 or not fields[0] or not fields[1].isdigit():
            raise ValueError(f"invalid required-file row at {path}:{line_number}")
        relative, size_text = fields
        candidate = PurePosixPath(relative)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError(f"unsafe required-file path at {path}:{line_number}: {relative!r}")
        size = int(size_text)
        if size < 0:
            raise ValueError(f"negative required-file size at {path}:{line_number}")
        if relative in required:
            raise ValueError(f"duplicate required-file path at {path}:{line_number}: {relative!r}")
        required[relative] = size
    if not required:
        raise ValueError(f"required-file list is empty: {path}")
    return required


def required_manifest(path: Path, required: dict[str, int]) -> dict[str, object]:
    return {
        "required_files_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "expected_file_count": len(required),
        "expected_total_bytes": sum(required.values()),
    }


def audit_directory(root: Path, required_path: Path) -> dict[str, object]:
    required = load_required_files(required_path)
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError(f"model root must be a real directory: {root}")
    root = root.resolve(strict=True)

    expected_directories: set[str] = set()
    for relative in required:
        parts = PurePosixPath(relative).parts[:-1]
        for index in range(1, len(parts) + 1):
            expected_directories.add("/".join(parts[:index]))

    files: list[dict[str, object]] = []
    metadata_files: list[dict[str, object]] = []
    missing: list[str] = []
    wrong_size: list[dict[str, object]] = []
    extras: list[str] = []
    unexpected_directories: list[str] = []
    symlinks: list[str] = []
    nonregular: list[str] = []

    # Audit the complete directory tree, rather than only the expected paths.
    # A downloaded checkpoint must not silently contain an extra model/config
    # file or a symlink that escapes the audited root.
    for path in sorted(root.rglob("*")):
        relative_path = str(path.relative_to(root)).replace(os.sep, "/")
        if path.is_symlink():
            symlinks.append(relative_path)
            continue
        mode = path.lstat().st_mode
        if stat.S_ISDIR(mode):
            if relative_path not in expected_directories:
                unexpected_directories.append(relative_path)
            continue
        if not stat.S_ISREG(mode):
            nonregular.append(relative_path)
            continue
        if relative_path in required:
            continue
        # Wrapper identity/complete/inventory files are explicitly allowed,
        # but are excluded from the payload so the inventory hash remains
        # stable when the wrapper updates its own metadata on resume.
        if relative_path in ALLOWED_METADATA_FILES:
            continue
        extras.append(relative_path)

    for relative, expected_size in sorted(required.items()):
        path = root.joinpath(*PurePosixPath(relative).parts)
        try:
            resolved = path.resolve(strict=False)
            resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"required path escapes model root: {relative!r}") from exc
        if path.is_symlink() or not path.is_file():
            missing.append(relative)
            continue
        actual_size = path.stat().st_size
        if actual_size != expected_size:
            wrong_size.append(
                {"path": relative, "expected": expected_size, "actual": actual_size}
            )
            continue
        files.append({"path": relative, "bytes": actual_size})
    manifest = required_manifest(required_path, required)
    result = {
        **manifest,
        "root": str(root),
        "files": files,
        "metadata_files": sorted(metadata_files, key=lambda item: str(item["path"])),
        "missing": missing,
        "wrong_size": wrong_size,
        "extras": sorted(extras),
        "unexpected_directories": sorted(unexpected_directories),
        "symlinks": sorted(symlinks),
        "nonregular": sorted(nonregular),
        "complete": not (
            missing
            or wrong_size
            or extras
            or unexpected_directories
            or symlinks
            or nonregular
        )
        and len(files) == len(required),
    }
    if not result["complete"]:
        raise ValueError(json.dumps(result, sort_keys=True))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--required-files", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit_directory(args.root, args.required_files)
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()

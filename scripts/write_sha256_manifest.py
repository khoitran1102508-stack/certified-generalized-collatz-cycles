#!/usr/bin/env python3
"""Write a deterministic SHA-256 manifest for release files."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


EXCLUDED_DIR_NAMES = {
    ".git",
    ".pytest_cache",
    "__MACOSX",
    "__pycache__",
}

EXCLUDED_FILE_NAMES = {
    ".DS_Store",
    "SHA256SUMS.txt",
}

EXCLUDED_SUFFIXES = {
    ".aux",
    ".bbl",
    ".blg",
    ".fdb_latexmk",
    ".fls",
    ".log",
    ".out",
    ".pyc",
    ".pyo",
    ".toc",
}


def iter_release_files(root: Path, output: Path) -> list[Path]:
    """Return release files in deterministic relative-path order."""
    files: list[Path] = []
    output_resolved = output.resolve()
    for path in root.rglob("*"):
        if any(part in EXCLUDED_DIR_NAMES for part in path.relative_to(root).parts):
            continue
        if not path.is_file():
            continue
        if path.resolve() == output_resolved:
            continue
        if path.name in EXCLUDED_FILE_NAMES:
            continue
        if path.suffix in EXCLUDED_SUFFIXES:
            continue
        files.append(path)
    return sorted(files, key=lambda item: item.relative_to(root).as_posix())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(root: Path, output: Path) -> int:
    root = root.resolve()
    output = output.resolve()
    files = iter_release_files(root, output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for path in files:
            rel = "./" + path.relative_to(root).as_posix()
            handle.write(f"{sha256_file(path)}  {rel}\n")
    return len(files)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, default=Path("SHA256SUMS.txt"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    count = write_manifest(args.root, args.output)
    print(f"Wrote {args.output} with {count} files")


if __name__ == "__main__":
    main()

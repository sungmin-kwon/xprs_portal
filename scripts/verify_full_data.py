#!/usr/bin/env python3
"""Verify a complete processed-data installation against the demo manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = ROOT / "data"
DEFAULT_MANIFEST = ROOT / "data" / "demo" / "manifest.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    data_dir = args.data_dir.resolve()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    expected = manifest.get("source_files") or {}
    if not expected:
        raise SystemExit("Manifest does not contain source_files checksums.")

    failures = 0
    for name, details in expected.items():
        path = data_dir / details["path"]
        if not path.is_file():
            print(f"MISSING  {name}: {path}")
            failures += 1
            continue
        actual_bytes = path.stat().st_size
        actual_sha256 = sha256_file(path)
        size_ok = actual_bytes == int(details["bytes"])
        hash_ok = actual_sha256 == details["sha256"]
        status = "OK" if size_ok and hash_ok else "MISMATCH"
        print(f"{status:8} {name}: {path}")
        if not size_ok:
            print(f"         bytes expected={details['bytes']} actual={actual_bytes}")
        if not hash_ok:
            print(f"         sha256 expected={details['sha256']} actual={actual_sha256}")
        failures += int(not (size_ok and hash_ok))

    if failures:
        print(f"Full processed-data verification failed for {failures} file(s).")
        return 1
    print("Full processed-data verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

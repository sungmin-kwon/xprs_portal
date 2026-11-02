"""Wipe runtime-generated state so the system behaves as if freshly installed.

Debug utility. Removes session chat logs, both provider literature caches, and
the ChromaDB vector store. Leaves source data
(data/*.csv, data/plot_cache/*.parquet, ref/, static assets, configs) untouched.

Note: data/plot_cache/ holds parquet files produced by build_parquet.py
from an upstream .rds file — they are *source data*, not runtime cache,
and are NOT wiped here.

Usage:
    python scripts/reset_runtime_state.py          # dry run, prints targets
    python scripts/reset_runtime_state.py --yes    # actually delete

After running with --yes, the next backend startup re-creates the empty
directories via ensure_runtime_dirs().
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

# Allow `python scripts/reset_runtime_state.py` from the project root by
# adding the parent dir to sys.path before importing config.
REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR))

from config import (  # noqa: E402
    CHROMA_DIR,
    EUROPE_PMC_CACHE_DIR,
    LOG_DIR,
    S2_CACHE_DIR,
)


def _human_size(path: Path) -> str:
    if not path.exists():
        return "missing"
    total = 0
    if path.is_file():
        total = path.stat().st_size
    else:
        for p in path.rglob("*"):
            if p.is_file():
                total += p.stat().st_size
    for unit in ("B", "KB", "MB", "GB"):
        if total < 1024:
            return f"{total:.1f} {unit}"
        total /= 1024
    return f"{total:.1f} TB"


def _count_entries(path: Path) -> int:
    if not path.exists() or path.is_file():
        return 0
    return sum(1 for _ in path.iterdir())


def _wipe_contents(path: Path) -> None:
    """Remove everything inside `path` but leave the directory itself."""
    if not path.exists():
        return
    for child in path.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Actually delete. Without this flag, runs as a dry run.",
    )
    args = parser.parse_args()

    # (label, path). Order is just for readable output.
    targets: list[tuple[str, Path]] = [
        ("session chat logs", LOG_DIR),
        ("Europe PMC cache", EUROPE_PMC_CACHE_DIR),
        ("Semantic Scholar cache", S2_CACHE_DIR),
        ("ChromaDB vector store", CHROMA_DIR),
    ]

    print(f"Project root: {REPO_DIR}\n")
    print(f"{'Target':<28}{'Entries':>10}{'Size':>14}  Path")
    print("-" * 90)
    for label, path in targets:
        entries = _count_entries(path) if path.exists() else 0
        size = _human_size(path)
        print(f"{label:<28}{entries:>10}{size:>14}  {path}")
    print()

    if not args.yes:
        print("Dry run. Re-run with --yes to delete.")
        return 0

    for label, path in targets:
        if not path.exists():
            print(f"  [skip]   {label}: does not exist ({path})")
            continue
        _wipe_contents(path)
        print(f"  [wiped]  {label}: {path}")
    print("\nDone. Restart the backend; ensure_runtime_dirs() will recreate empty dirs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

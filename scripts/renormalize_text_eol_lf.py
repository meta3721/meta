#!/usr/bin/env python3
"""Coordinate LF renormalization after .gitattributes is introduced.

This is intentionally opt-in. Running ``git add --renormalize`` can dirty a
very large tracked tree. Prefer:

1. Commit ``.gitattributes`` alone when practical.
2. Dry-run this helper and review the predicted dirty set with the team.
3. Apply renormalization only when coordinated.
4. Rebuild ``configs/frozen/E1_R2_FROZEN_CONFIG_MANIFEST.json`` so checkout
   file hashes remain authoritative for ``protocol_file_hash``.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PATTERNS = ("*.py", "*.yaml", "*.yml", "*.json", "*.md", "*.txt", "*.csv")


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout


def list_matching(root: Path) -> list[str]:
    rows: list[str] = []
    for pattern in PATTERNS:
        rows.extend(
            line.strip()
            for line in _git(root, "ls-files", pattern).splitlines()
            if line.strip()
        )
    return sorted(set(rows))


def dry_run(root: Path) -> dict[str, object]:
    matching = list_matching(root)
    porcelain = [
        line for line in _git(root, "status", "--porcelain").splitlines() if line
    ]
    return {
        "matching_tracked_files": len(matching),
        "current_dirty_paths": len(porcelain),
        "note": (
            "Applying renormalization may rewrite index/working-tree EOLs for "
            f"{len(matching)} tracked files. Coordinate before --apply."
        ),
        "next_steps": [
            "git add --renormalize -- " + " ".join(PATTERNS),
            "python scripts/rebuild_e1_r2_frozen_manifest.py",
            "review git status / frozen manifest hash deltas before commit",
        ],
    }


def apply(root: Path) -> int:
    cmd = ["git", "add", "--renormalize", "--", *PATTERNS]
    result = subprocess.run(cmd, cwd=root, check=False)
    if result.returncode != 0:
        return result.returncode
    rebuild = root / "scripts" / "rebuild_e1_r2_frozen_manifest.py"
    return subprocess.run(
        [sys.executable, str(rebuild), "--root", str(root)],
        cwd=root,
        check=False,
    ).returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Run git add --renormalize for text patterns and rebuild manifest.",
    )
    args = parser.parse_args(argv)
    root = args.root.resolve()
    if args.apply:
        print(
            "WARNING: renormalization can create a large dirty tree. "
            "Proceeding because --apply was requested."
        )
        return apply(root)
    import json

    print(json.dumps(dry_run(root), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

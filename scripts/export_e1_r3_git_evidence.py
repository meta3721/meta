#!/usr/bin/env python3
"""Export clean Git identity evidence for E1-R3."""
from __future__ import annotations

import subprocess
from pathlib import Path


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True,
    ).stdout


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    output = root / "outputs/evidence_r3/git"
    output.mkdir(parents=True, exist_ok=True)
    status = _git(root, "status", "--porcelain")
    (output / "GIT_STATUS.txt").write_text(
        "CLEAN\n" if not status.strip() else status,
        encoding="utf-8",
    )
    (output / "GIT_LOG.txt").write_text(
        _git(root, "log", "-20", "--oneline", "--decorate"),
        encoding="utf-8",
    )
    (output / "GIT_DIFF_SUMMARY.txt").write_text(
        _git(root, "diff", "--stat") or "CLEAN\n",
        encoding="utf-8",
    )
    (output / "GIT_HEAD.txt").write_text(
        _git(root, "rev-parse", "HEAD"),
        encoding="utf-8",
    )
    if status.strip():
        raise RuntimeError("Git evidence requires a clean worktree")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

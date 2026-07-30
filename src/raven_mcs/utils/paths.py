"""Run directory and checkpoint path helpers."""

from __future__ import annotations

import re
from pathlib import Path

_RUN_ID_SAFE = re.compile(r"[^a-zA-Z0-9._-]+")


def sanitize_run_token(token: str) -> str:
    return _RUN_ID_SAFE.sub("_", token.strip()) or "na"


def make_run_id(
    *,
    experiment: str,
    dataset: str,
    method: str,
    scenario: str,
    seed: int,
    run_hash: str | None = None,
) -> str:
    parts = [
        sanitize_run_token(experiment),
        sanitize_run_token(dataset),
        sanitize_run_token(method),
        sanitize_run_token(scenario),
        f"seed{int(seed)}",
    ]
    if run_hash is not None:
        parts.append(sanitize_run_token(run_hash[:12]))
    return "__".join(parts)


def run_dir(output_root: Path, run_id: str) -> Path:
    return Path(output_root) / run_id


def ensure_run_layout(path: Path) -> Path:
    """Create standard per-run subdirectory layout (constitution §十一)."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    (path / "checkpoints").mkdir(parents=True, exist_ok=True)
    (path / "failure_snapshot").mkdir(parents=True, exist_ok=True)
    return path


def checkpoint_path(run_path: Path, window_r: int) -> Path:
    return Path(run_path) / "checkpoints" / f"window_{int(window_r):06d}.pkl"


def latest_checkpoint(run_path: Path) -> Path | None:
    ckpt_dir = Path(run_path) / "checkpoints"
    if not ckpt_dir.exists():
        return None
    files = sorted(ckpt_dir.glob("window_*.pkl"))
    return files[-1] if files else None

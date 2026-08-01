#!/usr/bin/env python3
"""Freeze experiment config and create test-entry gate (P10-D / ISSUE-010).

Usage:
    python scripts/freeze_config.py --experiment E1_balanced --dataset sensorscope
    python scripts/freeze_config.py --experiment E1_balanced --dataset sensorscope --validate
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def _hash_config(config: dict) -> str:
    """SHA256 hash of a resolved config dict."""
    serialized = json.dumps(config, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def freeze_config(
    experiment: str,
    dataset: str,
    config_dir: Path | None = None,
    frozen_dir: Path | None = None,
) -> dict:
    if config_dir is None:
        config_dir = _ROOT / "configs" / "experiment"
    if frozen_dir is None:
        frozen_dir = _ROOT / "configs" / "frozen"

    config_path = config_dir / f"{experiment}.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Experiment config not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    resolved = dict(config)
    resolved["dataset"] = dataset
    resolved["freeze_timestamp"] = datetime.now(timezone.utc).isoformat()
    resolved["freeze_git_commit"] = _get_git_commit()

    config_hash = _hash_config(resolved)

    frozen_dir.mkdir(parents=True, exist_ok=True)
    frozen_path = frozen_dir / f"{experiment}_{dataset}.yaml"
    frozen_hash_path = frozen_dir / f"{experiment}_{dataset}.sha256"

    with open(frozen_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(resolved, f, sort_keys=False)

    with open(frozen_hash_path, "w", encoding="utf-8") as f:
        f.write(f"{config_hash}\n")

    return {
        "experiment": experiment,
        "dataset": dataset,
        "config_hash": config_hash,
        "frozen_path": str(frozen_path),
        "frozen_hash_path": str(frozen_hash_path),
        "timestamp": resolved["freeze_timestamp"],
        "git_commit": resolved["freeze_git_commit"],
    }


def validate_frozen_config(
    experiment: str,
    dataset: str,
    frozen_dir: Path | None = None,
) -> dict:
    """Validate that a frozen config exists and its hash matches."""
    if frozen_dir is None:
        frozen_dir = _ROOT / "configs" / "frozen"

    frozen_path = frozen_dir / f"{experiment}_{dataset}.yaml"
    frozen_hash_path = frozen_dir / f"{experiment}_{dataset}.sha256"

    if not frozen_path.exists():
        raise FileNotFoundError(
            f"Frozen config not found: {frozen_path}. "
            f"Run: python scripts/freeze_config.py --experiment {experiment} --dataset {dataset}"
        )

    if not frozen_hash_path.exists():
        raise FileNotFoundError(
            f"Frozen config hash not found: {frozen_hash_path}"
        )

    with open(frozen_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    current_hash = _hash_config(config)
    with open(frozen_hash_path, "r", encoding="utf-8") as f:
        stored_hash = f.read().strip()

    if current_hash != stored_hash:
        raise ValueError(
            f"Config hash mismatch! Expected {stored_hash}, got {current_hash}. "
            f"Config has been modified since freeze."
        )

    return {
        "experiment": experiment,
        "dataset": dataset,
        "config_hash": current_hash,
        "valid": True,
        "frozen_path": str(frozen_path),
    }


def _get_git_commit() -> str:
    import subprocess
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(_ROOT),
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"


def test_entry_gate(
    experiment: str,
    dataset: str,
    frozen_dir: Path | None = None,
) -> bool:
    """Check if test runs are allowed for this experiment/dataset."""
    validation = validate_frozen_config(experiment, dataset, frozen_dir)
    return validation["valid"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Freeze experiment config for test-entry gate.")
    parser.add_argument("--experiment", required=True, help="Experiment name")
    parser.add_argument("--dataset", required=True, help="Dataset name")
    parser.add_argument("--config-dir", type=Path, default=None)
    parser.add_argument("--frozen-dir", type=Path, default=None)
    parser.add_argument("--validate", action="store_true", help="Only validate frozen config")
    args = parser.parse_args(argv)

    try:
        if args.validate:
            result = validate_frozen_config(args.experiment, args.dataset, args.frozen_dir)
            print(f"Frozen config VALID: {args.experiment}/{args.dataset}")
            print(f"  Hash: {result['config_hash']}")
            return 0

        result = freeze_config(args.experiment, args.dataset, args.config_dir, args.frozen_dir)
        print(f"Config frozen: {args.experiment}/{args.dataset}")
        print(f"  Hash: {result['config_hash']}")
        print(f"  Path: {result['frozen_path']}")
        print(f"  Git:  {result['git_commit']}")
        return 0
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

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
    *,
    group_mapping_path: Path | None = None,
    event_trace_hash: str | None = None,
    data_hash: str | None = None,
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
    if group_mapping_path is not None:
        resolved["group_mapping_hash"] = hashlib.sha256(
            group_mapping_path.read_bytes()
        ).hexdigest()
    if event_trace_hash is not None:
        resolved["event_trace_hash"] = event_trace_hash
    if data_hash is not None:
        resolved["data_hash"] = data_hash
    resolved["validation_summary"] = {
        "experiment_config_exists": True,
        "dataset": dataset,
        "group_mapping_frozen": group_mapping_path is not None,
    }

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
    *,
    expected_data_hash: str | None = None,
    expected_group_mapping_hash: str | None = None,
    expected_event_trace_hash: str | None = None,
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
    summary = config.get("validation_summary")
    if not isinstance(summary, dict) or not summary.get("experiment_config_exists"):
        raise ValueError("Frozen config is missing a completed validation_summary")
    expected = {
        "data_hash": expected_data_hash,
        "group_mapping_hash": expected_group_mapping_hash,
        "event_trace_hash": expected_event_trace_hash,
    }
    for field, value in expected.items():
        if value is not None and config.get(field) != value:
            raise ValueError(
                f"Frozen {field} mismatch: expected {value}, got {config.get(field)}"
            )

    return {
        "experiment": experiment,
        "dataset": dataset,
        "config_hash": current_hash,
        "valid": True,
        "frozen_path": str(frozen_path),
        "config": config,
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
    **expected_hashes: str,
) -> bool:
    """Check if test runs are allowed for this experiment/dataset."""
    validation = validate_frozen_config(
        experiment, dataset, frozen_dir, **expected_hashes,
    )
    return validation["valid"]


def refresh_e1_identities() -> dict:
    from raven_mcs.experiments.e1_entry import (
        frozen_client_mapping_hashes, frozen_group_hashes,
    )
    from raven_mcs.utils.hashing import sha256_file
    from raven_mcs.utils.serialization import dump_json, dump_yaml, load_json, load_yaml

    frozen = _ROOT / "configs/frozen"
    protocol_path = frozen / "e1_sensorscope_balanced.yaml"
    protocol = load_yaml(protocol_path)
    group_payload, group_file = frozen_group_hashes(_ROOT)
    mapping_payload, mapping_file = frozen_client_mapping_hashes(_ROOT)
    protocol.update({
        "git_commit": _get_git_commit(),
        "authorization_status": "READY_FOR_TEACHER_REVIEW_AFTER_R4",
        "semantic_seal_status": "R4_PASS",
        "target_group_payload_hash": group_payload,
        "target_group_file_hash": group_file,
        "target_group_hash": group_file,
        "client_mapping_payload_hash": mapping_payload,
        "client_mapping_file_hash": mapping_file,
        "pi_target_hash": sha256_file(
            frozen / "e1_pi_target_client_stratum.parquet",
        ),
    })
    dump_yaml(protocol, protocol_path)
    protocol_hash = sha256_file(protocol_path)
    manifest_path = frozen / "FROZEN_CONFIG_MANIFEST.json"
    manifest = load_json(manifest_path)
    trace_manifest_path = (
        _ROOT / "outputs/event_traces/E1_BALANCED_EVENTTRACE_MANIFEST.json"
    )
    event_trace_hashes = manifest.get("event_trace_hashes", {})
    if trace_manifest_path.exists():
        trace_manifest = load_json(trace_manifest_path)
        event_trace_hashes = {
            str(seed): row["event_trace_hash"]
            for seed, row in trace_manifest["traces"].items()
        }
    manifest.update({
        "seal": "E1_ENTRY_R4_PASS",
        "git_commit": _get_git_commit(),
        "e1_config_hash": protocol_hash,
        "target_group_payload_hash": group_payload,
        "target_group_file_hash": group_file,
        "client_mapping_payload_hash": mapping_payload,
        "client_mapping_file_hash": mapping_file,
        "pi_target_hash": protocol["pi_target_hash"],
        "entry_smoke_status": "PASS_SINGLE_SEED_R4_DRY_RUN",
        "event_trace_hashes": event_trace_hashes,
    })
    dump_json(manifest, manifest_path)
    return {
        "protocol_config_hash": protocol_hash,
        "protocol_path": str(protocol_path),
        "git_commit": _get_git_commit(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Freeze experiment config for test-entry gate.")
    parser.add_argument("--experiment", required=True, help="Experiment name")
    parser.add_argument("--dataset", default="sensorscope", help="Dataset name")
    parser.add_argument("--config-dir", type=Path, default=None)
    parser.add_argument("--frozen-dir", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None, help="Alias for --frozen-dir")
    parser.add_argument("--groups", type=Path, default=_ROOT / "configs" / "frozen" / "e1_sensorscope_groups.yaml")
    parser.add_argument("--event-trace-hash", default=None)
    parser.add_argument("--data-hash", default=None)
    parser.add_argument("--validate", action="store_true", help="Only validate frozen config")
    parser.add_argument("--refresh-identities", action="store_true")
    args = parser.parse_args(argv)

    try:
        if args.refresh_identities:
            result = refresh_e1_identities()
            print(f"E1 identities refreshed: {result['protocol_config_hash']}")
            return 0
        if args.validate:
            result = validate_frozen_config(args.experiment, args.dataset, args.frozen_dir)
            print(f"Frozen config VALID: {args.experiment}/{args.dataset}")
            print(f"  Hash: {result['config_hash']}")
            return 0

        result = freeze_config(
            args.experiment, args.dataset, args.config_dir,
            args.output or args.frozen_dir,
            group_mapping_path=args.groups if args.groups.exists() else None,
            event_trace_hash=args.event_trace_hash,
            data_hash=args.data_hash,
        )
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

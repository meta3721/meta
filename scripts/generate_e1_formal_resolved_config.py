#!/usr/bin/env python3
"""Generate deterministic formal resolved config and hash."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from raven_mcs.utils.hashing import sha256_file, sha256_json
from raven_mcs.utils.serialization import dump_yaml, load_json, load_yaml


def build_resolved(root: Path, protocol_path: Path) -> dict:
    protocol = load_yaml(protocol_path)
    baseline = load_yaml(root / "configs/frozen/e1_selected_baseline.yaml")
    manifest = load_json(root / "configs/frozen/FROZEN_CONFIG_MANIFEST.json")
    if "local_steps" not in protocol:
        raise RuntimeError("frozen protocol missing local_steps")
    resolved = {
        "experiment": protocol["name"],
        "dataset": protocol["dataset"],
        "scenario": protocol["scenario"],
        "methods": list(protocol["methods"]),
        "seeds": list(protocol["seeds"]),
        "num_windows": int(protocol["num_windows"]),
        "local_steps": int(protocol["local_steps"]),
        "num_clients": int(protocol["num_clients"]),
        "S_max": int(protocol["s_max"]),
        "no_harm_threshold": float(protocol["no_harm_threshold"]),
        "selected_baseline": baseline["selected_baseline"],
        "authorized_algorithm_commit": protocol["authorized_algorithm_commit"],
        "protocol_parent_commit": protocol["protocol_parent_commit"],
        "execution_commit_policy": protocol["execution_commit_policy"],
        "authorization_status": protocol["authorization_status"],
        "execution_status": protocol["execution_status"],
        "protocol_config_hash": sha256_file(protocol_path),
        "selected_baseline_hash": manifest["selected_baseline"]["file_sha256"],
        "target_group_payload_hash": protocol["target_group_payload_hash"],
        "target_group_file_hash": protocol["target_group_file_hash"],
        "client_mapping_payload_hash": protocol["client_mapping_payload_hash"],
        "client_mapping_file_hash": protocol["client_mapping_file_hash"],
        "pi_target_hash": protocol["pi_target_hash"],
        "event_trace_hashes": manifest["event_trace_hashes"],
    }
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--protocol",
        type=Path,
        default=Path("configs/frozen/e1_sensorscope_balanced.yaml"),
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    protocol_path = (
        args.protocol if args.protocol.is_absolute() else root / args.protocol
    )
    resolved = build_resolved(root, protocol_path)
    out_dir = root / "outputs/preflight"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "e1_formal_resolved_config.yaml"
    dump_yaml(resolved, path)
    digest = sha256_json(resolved)
    (out_dir / "e1_formal_resolved_config_hash.json").write_text(
        json.dumps({
            "resolved_run_config_hash": digest,
            "protocol_config_hash": resolved["protocol_config_hash"],
            "local_steps": resolved["local_steps"],
            "contains_timestamp": False,
        }, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({
        "resolved_path": str(path.relative_to(root)),
        "resolved_run_config_hash": digest,
        "local_steps": resolved["local_steps"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

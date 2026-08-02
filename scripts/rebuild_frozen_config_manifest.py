#!/usr/bin/env python3
"""Rebuild FROZEN_CONFIG_MANIFEST from actual frozen file hashes."""
from __future__ import annotations

import argparse
from pathlib import Path

from raven_mcs.utils.hashing import sha256_file
from raven_mcs.utils.serialization import dump_json, load_yaml

AUTHORIZED = "53e277c53b01695330652b8e1bc8a234909d56e5"

FILES = {
    "configs/frozen/e1_sensorscope_balanced.yaml": "protocol",
    "configs/frozen/e1_sensorscope_groups.yaml": "target_groups",
    "configs/frozen/e1_sensorscope_clients.yaml": "client_mapping",
    "configs/frozen/e1_pi_target_client_stratum.parquet": "pi_target",
    "configs/frozen/e1_pi_target_manifest.json": "pi_target_manifest",
    "configs/frozen/e1_selected_baseline.yaml": "selected_baseline",
    "configs/frozen/e1_weight_safety.yaml": "weight_safety",
    "configs/frozen/e1_protocol_schema.yaml": "protocol_schema",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", default="E1_balanced")
    args = parser.parse_args()
    if args.experiment != "E1_balanced":
        raise ValueError("only E1_balanced is supported")
    root = Path(__file__).resolve().parents[1]
    protocol = load_yaml(root / "configs/frozen/e1_sensorscope_balanced.yaml")
    baseline = load_yaml(root / "configs/frozen/e1_selected_baseline.yaml")
    files = {}
    roles = set()
    for relative, role in FILES.items():
        path = root / relative
        if not path.exists():
            raise FileNotFoundError(relative)
        if role in roles:
            raise RuntimeError(f"duplicate semantic role: {role}")
        roles.add(role)
        files[relative.replace("\\", "/")] = {
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
            "semantic_role": role,
        }
    baseline_path = "configs/frozen/e1_selected_baseline.yaml"
    manifest = {
        "manifest_schema_version": 1,
        "experiment": "E1_balanced",
        "authorized_algorithm_commit": AUTHORIZED,
        "protocol_parent_commit": protocol.get(
            "protocol_parent_commit", AUTHORIZED,
        ),
        "protocol_config_hash": files[
            "configs/frozen/e1_sensorscope_balanced.yaml"
        ]["sha256"],
        "files": files,
        "selected_baseline": {
            "method": baseline["selected_baseline"],
            "file_path": baseline_path,
            "file_sha256": files[baseline_path]["sha256"],
        },
        "local_steps": int(protocol["local_steps"]),
        "num_clients": int(protocol["num_clients"]),
        "S_max": int(protocol["s_max"]),
        "seeds": list(protocol["seeds"]),
        "no_harm_threshold": float(protocol["no_harm_threshold"]),
        "e1_methods": list(protocol["methods"]),
        "authorization_status": protocol["authorization_status"],
        "execution_status": protocol["execution_status"],
        "execution_commit_policy": protocol["execution_commit_policy"],
        "seal": "E1_FORMAL_FREEZE_R1",
        "e2_e9_status": "NOT_STARTED",
        "entry_smoke_status": "PASS_SINGLE_SEED_R4_DRY_RUN",
        "pi_target_hash": protocol["pi_target_hash"],
        "target_group_payload_hash": protocol["target_group_payload_hash"],
        "target_group_file_hash": protocol["target_group_file_hash"],
        "client_mapping_payload_hash": protocol["client_mapping_payload_hash"],
        "client_mapping_file_hash": protocol["client_mapping_file_hash"],
        "event_trace_hashes": {
            "26001": "e212661f5262e0559100d7f852c38a199dac9046b2b8c520fc913c9834f21a50",
            "26002": "e8286dee49c025f5c3fa5bc4b9fbc658342a608c4b7374063951b2c9e56e05cb",
            "26003": "06b434948310df5bbd72aac048ed54fb677321d681686d18a711e6a85190ee72",
            "26004": "76b886994aeb651a406f465591180a170f2c25537dc144bf4735c6b47d9a1ec5",
            "26005": "9fa446409c2edbb46407e0eb1cd936696117e7c6194b4b480a49f0cfb0a84d45",
        },
    }
    dump_json(manifest, root / "configs/frozen/FROZEN_CONFIG_MANIFEST.json")
    print(f"protocol_config_hash={manifest['protocol_config_hash']}")
    print(
        "selected_baseline_hash="
        f"{manifest['selected_baseline']['file_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

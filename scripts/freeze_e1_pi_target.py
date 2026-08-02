#!/usr/bin/env python3
"""Freeze E1 client-stratum target mass."""
from __future__ import annotations

import argparse
from pathlib import Path

from raven_mcs.correction.pi_target import build_pi_target
from raven_mcs.data.target import GroupMapper, TargetBuilder
from raven_mcs.experiments.e1_entry import (
    add_e1_groups, git_commit, sensorscope_dataset,
)
from raven_mcs.utils.hashing import sha256_file, sha256_json
from raven_mcs.utils.serialization import dump_json, load_yaml


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="sensorscope")
    parser.add_argument("--scenario", default="balanced")
    parser.add_argument(
        "--support-source", default="station-client-mapping",
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if (args.dataset, args.scenario) != ("sensorscope", "balanced"):
        raise ValueError("official E1 pi target is SensorScope balanced")
    if args.support_source != "station-client-mapping":
        raise ValueError("official support source is station-client-mapping")
    root = Path(__file__).resolve().parents[1]
    dataset = sensorscope_dataset(root)
    mapping_path = root / "configs/frozen/e1_sensorscope_clients.yaml"
    mapping_config = load_yaml(mapping_path)
    station_to_client = mapping_config["station_to_client"]
    grouped = add_e1_groups(dataset.atomic_df)
    frame = build_pi_target(
        grouped, station_to_client, split="test",
    )
    path = root / "configs/frozen/e1_pi_target_client_stratum.parquet"
    if path.exists() and not args.overwrite:
        raise FileExistsError("use --overwrite to replace frozen pi target")
    frame.to_parquet(path, index=False)
    digest = sha256_file(path)
    mapping_payload_hash = sha256_json({
        str(key): str(value)
        for key, value in sorted(station_to_client.items())
    })
    strata = sorted(grouped["opportunity_stratum"].astype(str).unique())
    target = frame[[
        "client_id", "opportunity_stratum", "pi_k_s_tar",
    ]].to_dict(orient="records")
    atomic_target = TargetBuilder(
        group_mapper=GroupMapper(column="target_group_main"),
    ).build(grouped, split="test").atom_mass
    atomic_records = [
        {"unit_id": str(unit_id), "target_weight": float(weight)}
        for unit_id, weight in atomic_target.sort_index().items()
    ]
    commit = git_commit(root)
    manifest = {
        "dataset": args.dataset,
        "scenario": args.scenario,
        "evaluation_target_split": "test",
        "construction": "Lambda_s_tar times unique station-mapped client share",
        "construction_source": "station_client_mapping",
        "atomic_target_weight_hash": sha256_json(atomic_records),
        "client_stratum_target_mass_hash": sha256_json(target),
        "pi_target_file_hash": digest,
        "station_client_mapping_payload_hash": mapping_payload_hash,
        "station_client_mapping_file_hash": sha256_file(mapping_path),
        "stratum_definition_hash": sha256_json(strata),
        "support_pair_count": int(frame["support_flag"].sum()),
        "positive_pi_pair_count": int((frame["pi_k_s_tar"] > 0).sum()),
        "row_count": int(len(frame)),
        "pi_sum": float(frame["pi_k_s_tar"].sum()),
        "positive_rows": int((frame["pi_k_s_tar"] > 0).sum()),
        "support_violations": int(
            ((frame["pi_k_s_tar"] > 0) & ~frame["support_flag"].astype(bool)).sum()
        ),
        "pi_target_hash": digest,
        "recomputed_pi_target_hash": digest,
        "sum_pi": float(frame["pi_k_s_tar"].sum()),
        "creation_git_commit": commit,
        "verification_git_commit": commit,
        "verification_status": "RECOMPUTED_MATCH",
        "hard_gate_pass": bool(
            abs(float(frame["pi_k_s_tar"].sum()) - 1.0) <= 1e-12
            and (frame["pi_k_s_tar"] >= 0).all()
        ),
    }
    dump_json(manifest, root / "configs/frozen/e1_pi_target_manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

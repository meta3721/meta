#!/usr/bin/env python3
"""Freeze repeatable SensorScope E1 groups and split-support evidence."""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from raven_mcs.data.target import GroupMapper, TargetBuilder
from raven_mcs.experiments.e1_entry import add_e1_groups, sensorscope_dataset
from raven_mcs.utils.hashing import sha256_file, sha256_json
from raven_mcs.utils.serialization import dump_json, dump_yaml, load_yaml


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="sensorscope")
    parser.add_argument("--mapping", default="repeatable_time_of_day_4")
    args = parser.parse_args()
    if args.dataset != "sensorscope" or args.mapping != "repeatable_time_of_day_4":
        raise ValueError("official E1 freezes SensorScope repeatable_time_of_day_4")
    root = Path(__file__).resolve().parents[1]
    dataset = sensorscope_dataset(root)
    atomic = add_e1_groups(dataset.atomic_df)
    spec = {
        "group_count": 4,
        "mapping": args.mapping,
        "timezone": "UTC",
        "spatial_partition": "none",
        "boundaries": [
            {"id": 0, "name": "UTC_00_06", "start_hour": 0, "end_hour": 6},
            {"id": 1, "name": "UTC_06_12", "start_hour": 6, "end_hour": 12},
            {"id": 2, "name": "UTC_12_18", "start_hour": 12, "end_hour": 18},
            {"id": 3, "name": "UTC_18_24", "start_hour": 18, "end_hour": 24},
        ],
        "group_names": ["UTC_00_06", "UTC_06_12", "UTC_12_18", "UTC_18_24"],
        "version": "e1-r1-v1",
    }
    spec["mapping_hash"] = sha256_json(spec)
    measurements = dataset.client_df[["client_id", "unit_id"]].copy()
    measured_units = set(measurements["unit_id"].astype(str))
    rows = []
    for split in ("train", "validation", "test"):
        target = TargetBuilder(
            group_mapper=GroupMapper("target_group_main"),
        ).build(atomic, split=split)
        selected = atomic.loc[atomic["split"].astype(str) == split]
        for group in range(4):
            frame = selected.loc[selected["target_group_main"] == group]
            unit_ids = set(frame["unit_id"].astype(str))
            group_measurements = measurements.loc[
                measurements["unit_id"].astype(str).isin(unit_ids)
            ]
            rows.append({
                "split": split,
                "group_id": group,
                "atomic_count": int(len(frame)),
                "target_mass": float(target.group_mass.get(str(group), 0.0)),
                "observed_count": int(
                    frame["unit_id"].astype(str).isin(measured_units).sum()
                ),
                "usable_count": int(
                    (
                        frame["support_flag"].astype(bool)
                        & frame["unit_id"].astype(str).isin(measured_units)
                    ).sum()
                ),
                "supported_client_count": int(
                    group_measurements["client_id"].astype(str).nunique()
                ),
            })
    audit = pd.DataFrame(rows)
    if bool((audit["atomic_count"] <= 0).any()):
        raise RuntimeError("all four groups require atomic support in every split")
    if bool((audit["target_mass"] <= 0).any()):
        raise RuntimeError("positive target support missing")
    sums = audit.groupby("split")["target_mass"].sum()
    if bool(((sums - 1.0).abs() > 1e-12).any()):
        raise RuntimeError("group target mass must sum to one per split")
    audit_dir = root / "outputs/audits"
    audit_dir.mkdir(parents=True, exist_ok=True)
    audit.to_csv(audit_dir / "e1_r1_group_support_by_split.csv", index=False)
    summary = {
        "mapping": args.mapping,
        "timezone": "UTC",
        "mapping_hash": spec["mapping_hash"],
        "all_four_supported_each_split": True,
        "target_mass_sums": {str(k): float(v) for k, v in sums.items()},
        "hard_gate_pass": True,
    }
    dump_json(summary, audit_dir / "e1_r1_group_support_summary.json")
    spec["validation_audit_hash"] = sha256_json(summary)
    spec["fine_grained_diagnostic_groups"] = "station_x_repeatable_time_block"
    spec["selection_rule"] = "protocol_predefined_repeatable_utc_time_blocks"
    spec["reason"] = (
        "Repeatable UTC blocks preserve all four groups in each chronological split."
    )
    group_path = root / "configs/frozen/e1_sensorscope_groups.yaml"
    dump_yaml(spec, group_path)
    protocol_path = root / "configs/frozen/e1_sensorscope_balanced.yaml"
    if protocol_path.exists():
        protocol = load_yaml(protocol_path)
        protocol["target_group_hash"] = sha256_file(group_path)
        protocol["target_group_mapping"] = args.mapping
        protocol["target_group_timezone"] = "UTC"
        dump_yaml(protocol, protocol_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

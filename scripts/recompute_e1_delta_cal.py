#!/usr/bin/env python3
"""Recompute E1 calibration residual on real station-client support."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from raven_mcs.data.target import GroupMapper, TargetBuilder
from raven_mcs.experiments.e1_entry import add_e1_groups, sensorscope_dataset
from raven_mcs.utils.hashing import sha256_file, sha256_json
from raven_mcs.utils.serialization import dump_json, load_yaml


def recompute(root: Path) -> tuple[pd.DataFrame, dict]:
    dataset = sensorscope_dataset(root)
    atomic = add_e1_groups(dataset.atomic_df)
    target = TargetBuilder(
        group_mapper=GroupMapper("target_group_main"),
    ).build(atomic, split="test")
    mapping_path = root / "configs/frozen/e1_sensorscope_clients.yaml"
    station_to_client = load_yaml(mapping_path)["station_to_client"]
    params = dataset.client_df[[
        "client_id", "controlled_generator_parameters",
    ]].drop_duplicates("client_id")
    bias_by_client = {
        str(row.client_id): float(
            json.loads(row.controlled_generator_parameters)["bias"],
        )
        for row in params.itertuples()
    }
    selected = atomic.loc[
        atomic["unit_id"].astype(str).isin(target.atom_mass.index),
        ["unit_id", "spatial_id"],
    ].copy()
    selected["unit_id"] = selected["unit_id"].astype(str)
    selected["target_weight"] = selected["unit_id"].map(target.atom_mass)
    selected["mapped_client"] = selected["spatial_id"].astype(str).map(
        station_to_client,
    )
    if selected["mapped_client"].isna().any():
        raise RuntimeError("target station missing client mapping")
    selected["client_bias"] = selected["mapped_client"].map(bias_by_client)
    selected["bar_b_target"] = selected["client_bias"]
    selected["weighted_abs_bias"] = (
        selected["target_weight"] * selected["bar_b_target"].abs()
    )
    delta = float(selected["weighted_abs_bias"].sum())
    selected["Delta_cal"] = delta
    summary = {
        "Delta_cal": delta,
        "support_source": "station_client_mapping",
        "target_split": "test_weights_only_no_bias_centering",
        "bias_centering_split": None,
        "test_split_used_for_bias_centering": False,
        "target_weight_sum": float(selected["target_weight"].sum()),
        "mapped_client_count": int(selected["mapped_client"].nunique()),
        "client_stratum_target_mass_hash": sha256_json(
            selected[["unit_id", "target_weight"]].to_dict(orient="records"),
        ),
        "client_mapping_file_hash": sha256_file(mapping_path),
    }
    return selected, summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="sensorscope")
    parser.add_argument("--pi-target", type=Path)
    args = parser.parse_args()
    if args.dataset != "sensorscope":
        raise ValueError("E1 calibration dataset is SensorScope")
    root = Path(__file__).resolve().parents[1]
    if args.pi_target and not args.pi_target.exists():
        raise FileNotFoundError(args.pi_target)
    frame, summary = recompute(root)
    output = root / "outputs/audits"
    output.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(
        output / "e1_r3_calibration_residual.parquet", index=False,
    )
    dump_json(summary, output / "e1_r3_calibration_summary.json")
    summary["calibration_audit_hash"] = sha256_file(
        output / "e1_r3_calibration_residual.parquet",
    )
    dump_json(
        summary,
        root / "configs/frozen/e1_measurement_calibration_manifest.json",
    )
    print(f"Delta_cal={summary['Delta_cal']:.12g}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

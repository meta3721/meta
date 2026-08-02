#!/usr/bin/env python3
"""Freeze E1 client-stratum target mass."""
from __future__ import annotations

import argparse
from pathlib import Path

from raven_mcs.correction.pi_target import build_pi_target
from raven_mcs.experiments.e1_entry import add_e1_groups, sensorscope_dataset
from raven_mcs.utils.hashing import sha256_file
from raven_mcs.utils.serialization import dump_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="sensorscope")
    parser.add_argument("--scenario", default="balanced")
    args = parser.parse_args()
    if (args.dataset, args.scenario) != ("sensorscope", "balanced"):
        raise ValueError("official E1 pi target is SensorScope balanced")
    root = Path(__file__).resolve().parents[1]
    dataset = sensorscope_dataset(root)
    frame = build_pi_target(
        add_e1_groups(dataset.atomic_df), dataset.client_df, split="test",
    )
    path = root / "configs/frozen/e1_pi_target_client_stratum.parquet"
    frame.to_parquet(path, index=False)
    digest = sha256_file(path)
    manifest = {
        "dataset": args.dataset,
        "scenario": args.scenario,
        "evaluation_target_split": "test",
        "construction": (
            "Lambda_s_tar from frozen atomic target weights; "
            "uniform supported client share within stratum"
        ),
        "row_count": int(len(frame)),
        "pi_sum": float(frame["pi_k_s_tar"].sum()),
        "positive_rows": int((frame["pi_k_s_tar"] > 0).sum()),
        "support_violations": int(
            ((frame["pi_k_s_tar"] > 0) & ~frame["support_flag"].astype(bool)).sum()
        ),
        "pi_target_hash": digest,
        "hard_gate_pass": bool(
            abs(float(frame["pi_k_s_tar"].sum()) - 1.0) <= 1e-12
            and (frame["pi_k_s_tar"] >= 0).all()
        ),
    }
    dump_json(manifest, root / "configs/frozen/e1_pi_target_manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

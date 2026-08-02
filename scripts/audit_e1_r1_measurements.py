#!/usr/bin/env python3
"""Recompute E1-R1 local-measurement integrity evidence."""
from __future__ import annotations

import inspect
import json
from pathlib import Path

import numpy as np
import pandas as pd

from raven_mcs.data import window_dataset
from raven_mcs.experiments.e1_entry import E1_SEEDS, sensorscope_dataset
from raven_mcs.simulation.event_trace import load_event_trace
from raven_mcs.utils.serialization import dump_json


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    dataset = sensorscope_dataset(root)
    available = set(zip(
        dataset.client_df["client_id"].astype(str),
        dataset.client_df["unit_id"].astype(str),
    ))
    requested = []
    for seed in E1_SEEDS:
        trace, _ = load_event_trace(
            root / f"outputs/event_traces/e1_balanced_seed{seed}",
        )
        requested.extend(
            (str(row.client_id), str(unit))
            for row in trace.events.itertuples()
            for unit in row.observed_unit_ids
        )
    missing = [key for key in requested if key not in available]
    params = dataset.client_df["controlled_generator_parameters"].map(json.loads)
    bias = np.asarray([float(value["bias"]) for value in params])
    noise = np.asarray([float(value["noise"]) for value in params])
    delta_cal = np.asarray([float(value["delta_cal"]) for value in params])
    source = inspect.getsource(window_dataset.extract_window_slice)
    direct_target_usage = int("obs_value = unit.target_value" in source)
    report = {
        "number_local_training_records": len(requested),
        "number_potential_measurements_found": len(requested) - len(missing),
        "missing_measurement_count": len(missing),
        "direct_target_value_usage_count": direct_target_usage,
        "client_bias_mean": float(bias.mean()),
        "client_bias_std": float(bias.std()),
        "measurement_noise_mean": float(noise.mean()),
        "measurement_noise_std": float(noise.std()),
        "calibration_centering_status": (
            "CENTERED" if abs(float(delta_cal.mean())) <= 1e-12 else "NONZERO"
        ),
        "Delta_cal": float(delta_cal.mean()),
        "hard_gate_pass": len(missing) == 0 and direct_target_usage == 0,
    }
    if not report["hard_gate_pass"]:
        raise RuntimeError(f"measurement audit failed: {report}")
    output = root / "outputs/audits/e1_r1_measurement_audit.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    dump_json(report, output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

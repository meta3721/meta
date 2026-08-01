"""Helpers shared by controlled (non-trace) public-field adapters."""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd

from raven_mcs.data.schema import normalize_client_measurements


def time_of_day_block(timestamp: pd.Timestamp, *, blocks: int = 4) -> int:
    hour = int(pd.Timestamp(timestamp).tz_convert("UTC").hour)
    return hour // max(1, 24 // blocks)


def weekday_label(timestamp: pd.Timestamp) -> str:
    return "weekend" if pd.Timestamp(timestamp).tz_convert("UTC").dayofweek >= 5 else "weekday"


def public_time_features(timestamp: pd.Timestamp) -> dict[str, Any]:
    ts = pd.Timestamp(timestamp).tz_convert("UTC")
    hour = ts.hour
    return {
        "hour_sin": float(np.sin(2.0 * np.pi * hour / 24.0)),
        "hour_cos": float(np.cos(2.0 * np.pi * hour / 24.0)),
        "weekday": 1 if ts.dayofweek < 5 else 0,
        "time_block": time_of_day_block(ts),
    }


def build_controlled_client_measurements(
    atomic: pd.DataFrame,
    *,
    seed: int,
    client_count: int = 8,
    noise_std_ratio: float = 0.05,
    bias_std_ratio: float = 0.20,
) -> pd.DataFrame:
    """
    Generate Z* = Y + b + eps for controlled benchmarks.

    Parameters are stored so EventTrace generators can reproduce the same draws.
    """
    rng = np.random.default_rng(int(seed))
    train = atomic.loc[atomic["split"].astype(str) == "train", "target_value"]
    train_std = float(train.std(ddof=0)) if len(train) else 1.0
    train_std = max(train_std, 1e-6)
    noise_std = noise_std_ratio * train_std
    bias_std = bias_std_ratio * train_std

    split_by_unit = atomic.set_index("unit_id")["split"].astype(str).to_dict()
    target_by_unit = atomic.set_index("unit_id")["target_value"].astype(float).to_dict()
    biases = rng.normal(0.0, bias_std, size=client_count)
    biases = biases - biases.mean()

    rows: list[dict[str, object]] = []
    for client_index, bias in enumerate(biases):
        for unit_id, target in target_by_unit.items():
            noise = float(rng.normal(0.0, noise_std))
            params = {
                "generator": "controlled-zstar-v1",
                "bias": float(bias),
                "noise": noise,
                "noise_std": noise_std,
                "bias_std": bias_std,
                "delta_cal": 0.0,
            }
            rows.append(
                {
                    "client_id": f"client-{client_index:03d}",
                    "unit_id": unit_id,
                    "potential_measurement": float(target) + float(bias) + noise,
                    "controlled_generator_parameters": json.dumps(
                        params, sort_keys=True, separators=(",", ":")
                    ),
                    "split": split_by_unit[unit_id],
                    "source_trace_id": f"client::{client_index:03d}::{unit_id}",
                }
            )
    return normalize_client_measurements(pd.DataFrame(rows))

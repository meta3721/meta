#!/usr/bin/env python3
"""Audit Common-NDMF weekday encoding against UTC datetimes."""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from raven_mcs.experiments.e1_entry import sensorscope_dataset
from raven_mcs.models.features import utc_weekday_from_unix_hours
from raven_mcs.utils.serialization import dump_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="sensorscope")
    parser.add_argument("--timezone", default="UTC")
    args = parser.parse_args()
    if (args.dataset, args.timezone) != ("sensorscope", "UTC"):
        raise ValueError("E1 time features are frozen to SensorScope UTC")
    root = Path(__file__).resolve().parents[1]
    known = {
        "1970-01-01T00:00:00Z": 3,
        "1970-01-05T00:00:00Z": 0,
        "2026-08-02T00:00:00Z": 6,
    }
    known_results = {}
    for text, expected in known.items():
        timestamp = pd.Timestamp(text)
        hours = timestamp.timestamp() / 3600.0
        actual = int(utc_weekday_from_unix_hours(np.array([hours]))[0])
        known_results[text] = {"expected": expected, "actual": actual}
    dataset = sensorscope_dataset(root)
    sample = dataset.atomic_df.iloc[:: max(len(dataset.atomic_df) // 1000, 1)]
    timestamps = pd.to_datetime(sample["absolute_time"], utc=True)
    hours = timestamps.map(lambda value: value.timestamp() / 3600.0).to_numpy()
    encoded = utc_weekday_from_unix_hours(hours)
    expected = timestamps.dt.dayofweek.to_numpy()
    mismatch = int(np.sum(encoded != expected))
    report = {
        "timezone": "UTC",
        "grouping_timezone": "UTC",
        "known_dates": known_results,
        "dataset_sample_count": int(len(sample)),
        "weekday_mismatch_count": mismatch,
        "hard_gate_pass": bool(
            mismatch == 0
            and all(
                row["actual"] == row["expected"]
                for row in known_results.values()
            )
        ),
    }
    output = root / "outputs/audits/e1_r3_time_feature_audit.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    dump_json(report, output)
    if not report["hard_gate_pass"]:
        raise RuntimeError("weekday feature audit failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

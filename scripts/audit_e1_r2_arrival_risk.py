#!/usr/bin/env python3
"""Audit formal arrival-risk features and information timing."""
from __future__ import annotations

import inspect
from pathlib import Path

import pandas as pd

from raven_mcs.experiments.e1_entry import _arrival_weights
from raven_mcs.utils.serialization import dump_json


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    source = inspect.getsource(_arrival_weights)
    features = pd.DataFrame([
        {
            "feature": "bias",
            "availability_time": "risk-set formation",
            "source_split": "train",
            "post_outcome": False,
        },
        {
            "feature": "hour_block",
            "availability_time": "risk-set formation",
            "source_split": "train",
            "post_outcome": False,
        },
        {
            "feature": "planned_workload_pre",
            "availability_time": "before O",
            "source_split": "train",
            "post_outcome": False,
        },
    ])
    audit_dir = root / "outputs/audits"
    audit_dir.mkdir(parents=True, exist_ok=True)
    features.to_csv(
        audit_dir / "e1_r2_arrival_risk_feature_audit.csv", index=False,
    )
    report = {
        "raw_workload_usage_count": source.count("raw_workload"),
        "observed_count_usage_count": source.count("observed_count"),
        "planned_workload_pre_usage_count": source.count(
            "planned_workload_pre",
        ),
        "test_outcome_usage_count": source.count("target_value"),
        "history_source_split": "train",
    }
    report["hard_gate_pass"] = bool(
        report["raw_workload_usage_count"] == 0
        and report["observed_count_usage_count"] == 0
        and report["test_outcome_usage_count"] == 0
        and report["planned_workload_pre_usage_count"] > 0
    )
    if not report["hard_gate_pass"]:
        raise RuntimeError(f"arrival-risk feature audit failed: {report}")
    dump_json(report, audit_dir / "e1_r2_arrival_risk_audit.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

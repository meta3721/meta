#!/usr/bin/env python3
"""Audit once-per-window opportunity EMA, including manual fixtures."""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from raven_mcs.opportunities.estimator import OpportunityEstimator
from raven_mcs.utils.serialization import dump_json


def manual_fixtures() -> dict:
    multi = OpportunityEstimator(
        forgetting=0.95, smoothing=0.0, c_prior=0.0,
        counts={("A", "s"): 100.0},
    )
    multi.update_window(0, {("A", "s"): 10.0})
    zero = OpportunityEstimator(
        forgetting=0.9, smoothing=0.0, c_prior=0.0,
        counts={("A", "s"): 50.0},
    )
    zero.update_window(0, {})
    normalized = OpportunityEstimator(
        forgetting=0.5, smoothing=0.0, c_prior=0.0,
        counts={("A", "s1"): 2.0, ("B", "s2"): 3.0},
    )
    normalized.update_window(
        0, {("A", "s1"): 1.0, ("B", "s3"): 4.0},
    )
    return {
        "multi_record_C_new": multi.counts[("A", "s")],
        "multi_record_expected": 105.0,
        "zero_count_C_new": zero.counts[("A", "s")],
        "zero_count_expected": 45.0,
        "normalized_mass_sum": float(normalized.pi_hat().sum()),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    frames = []
    if args.run_root and args.run_root.exists():
        for path in sorted(
            args.run_root.rglob("opportunity_ema_diagnostics.parquet"),
        ):
            frame = pd.read_parquet(path)
            frame.insert(0, "run_dir", str(path.parent))
            frames.append(frame)
    if not frames:
        fixture = OpportunityEstimator(
            forgetting=0.9, smoothing=0.0, c_prior=0.0,
            counts={("A", "s1"): 10.0, ("B", "s2"): 5.0},
        )
        fixture.update_window(0, {("A", "s1"): 2.0})
        frames = [pd.DataFrame(fixture.diagnostics)]
    audit = pd.concat(frames, ignore_index=True)
    duplicates = audit.duplicated(
        [
            column for column in (
                "run_dir", "window_id", "client_id", "stratum_id",
            ) if column in audit
        ],
        keep=False,
    )
    zero_expected = (
        (audit["N_current"] == 0) & (audit["C_old"] > 0)
    )
    zero_violations = int((
        zero_expected & ~audit["zero_count_decay_applied"].astype(bool)
    ).sum())
    fixtures = manual_fixtures()
    summary = {
        "rho_opp": 0.95,
        "c_prior": 1.0,
        "support_rule": "positive frozen station-client pi target pairs",
        "warm_up_windows": 0,
        "max_formula_error": float(audit["formula_error"].max()),
        "duplicate_pair_updates_in_window": int(duplicates.sum()),
        "zero_count_decay_violations": zero_violations,
        "manual_fixtures": fixtures,
    }
    summary["hard_gate_pass"] = bool(
        summary["max_formula_error"] <= 1e-12
        and summary["duplicate_pair_updates_in_window"] == 0
        and zero_violations == 0
        and fixtures["multi_record_C_new"] == 105.0
        and fixtures["zero_count_C_new"] == 45.0
        and abs(fixtures["normalized_mass_sum"] - 1.0) <= 1e-12
    )
    output = root / "outputs/audits"
    output.mkdir(parents=True, exist_ok=True)
    audit.to_parquet(
        output / "e1_r3_opportunity_ema_audit.parquet", index=False,
    )
    dump_json(summary, output / "e1_r3_opportunity_ema_summary.json")
    if not summary["hard_gate_pass"]:
        raise RuntimeError("opportunity EMA audit failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

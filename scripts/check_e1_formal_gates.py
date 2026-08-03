#!/usr/bin/env python3
"""Evaluate E1-G1 through E1-G6 from formal aggregate and statistics artifacts."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from raven_mcs.utils.serialization import dump_json, load_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--aggregate-dir", type=Path, default=ROOT / "outputs/aggregate/E1_balanced")
    parser.add_argument("--statistics-dir", type=Path, default=ROOT / "outputs/statistics/E1_balanced")
    args = parser.parse_args(argv)
    aggregate = load_json(args.aggregate_dir / "aggregate_summary.json")
    audit = load_json(args.aggregate_dir / "identity_audit.json")
    metrics = pd.read_parquet(args.aggregate_dir / "per_seed_metrics.parquet")
    no_harm = load_json(args.statistics_dir / "no_harm_summary.json")
    wilcoxon = pd.read_csv(args.statistics_dir / "wilcoxon_results.csv")
    holm = pd.read_csv(args.statistics_dir / "holm_results.csv")
    checks = {
        "E1-G1": len(metrics) == 25 and aggregate.get("aggregate_status") == "PASS",
        "E1-G2": (
            metrics["formal"].eq(True).all()
            and metrics["hard_gate_status"].eq("PASS").all()
            and metrics["protocol_version"].eq("E1-R2").all()
            and metrics["seed_role"].eq("formal").all()
            and metrics["smoke"].eq(False).all()
        ),
        "E1-G3": (
            metrics["num_windows"].eq(100).all()
            and metrics["local_steps"].eq(2).all()
            and set(metrics["seed"].astype(int)) == set(range(28001, 28006))
            and metrics["selected_candidate"].eq("C2").all()
            and metrics["a_max"].eq(40.0).all()
            and metrics["opportunity_forgetting"].eq(0.95).all()
            and metrics["selected_baseline"].eq(
                "flamf_timealign_adapted"
            ).all()
        ),
        "E1-G4": audit.get("all_hard_gates_pass") is True and len(audit.get("execution_commits", [])) == 1,
        "E1-G5": len(wilcoxon) == 20 and len(holm) == 20,
        "E1-G6": no_harm.get("formal_no_harm_conclusion") is True
                 and "raven" in no_harm.get("no_harm_tests", {})
                 and metrics["c_clip_obs"].notna().all()
                 and metrics["c_clip_obs"].astype(float).le(0.05).all()
                 and metrics["clip_population"].eq("observed_records").all()
                 and metrics["clip_aggregation"].eq(
                     "global_micro_per_seed"
                 ).all()
                 and metrics["clip_comparison"].eq(
                     "u > a_max + 1e-12"
                 ).all(),
    }
    report = {"gates": {key: "PASS" if value else "FAIL" for key, value in checks.items()},
              "all_pass": all(checks.values())}
    dump_json(report, args.aggregate_dir / "E1_FORMAL_GATE_REPORT.json")
    print(report)
    return 0 if report["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

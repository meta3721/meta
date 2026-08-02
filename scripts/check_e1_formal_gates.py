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
        "E1-G2": metrics["formal"].eq(True).all() and metrics["hard_gate_status"].eq("PASS").all(),
        "E1-G3": metrics["num_windows"].eq(100).all() and metrics["local_steps"].eq(2).all(),
        "E1-G4": audit.get("all_hard_gates_pass") is True and len(audit.get("execution_commits", [])) == 1,
        "E1-G5": len(wilcoxon) == 20 and len(holm) == 20,
        "E1-G6": no_harm.get("formal_no_harm_conclusion") is True
                 and "raven" in no_harm.get("no_harm_tests", {}),
    }
    report = {"gates": {key: "PASS" if value else "FAIL" for key, value in checks.items()},
              "all_pass": all(checks.values())}
    dump_json(report, args.aggregate_dir / "E1_FORMAL_GATE_REPORT.json")
    print(report)
    return 0 if report["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

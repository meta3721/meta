#!/usr/bin/env python3
"""Evaluate E1R4-G1 through G10 from machine-readable evidence."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import pandas as pd


REQUIRED_STAGES = {
    "full_pytest", "r4_unit", "r4_integration", "pip_check",
    "pi_target_rebuild", "q_attempt_audit", "arrival_support_audit",
    "validation_baseline", "validation_weight_safety", "entry_smoke",
    "aggregation", "statistics_dry_run", "evidence_export",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("outputs/entry_r4_smoke"))
    parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    q = json.loads((root / "outputs/audits/e1_r4_q_attempt_summary.json").read_text())
    arrival = json.loads((
        root / "outputs/audits/e1_r4_arrival_support_summary.json"
    ).read_text())
    pi = json.loads((
        root / "outputs/audits/e1_r4_pi_target_reproducibility.json"
    ).read_text())
    validation = json.loads((
        root / "outputs/validation/e1_r4_weight_safety_summary.json"
    ).read_text())
    aggregate = pd.read_parquet(
        root / "outputs/aggregate/E1_balanced_entry_r4/per_seed_metrics.parquet"
    )
    stats = json.loads((
        root / "outputs/statistics/E1_balanced/E1_balanced_statistics.json"
    ).read_text())
    tests = json.loads((root / "logs/E1_ENTRY_R4_TEST_SUMMARY.json").read_text())
    command_rows = [
        json.loads(line) for line in (
            root / "logs/E1_ENTRY_R4_EXACT_COMMANDS.jsonl"
        ).read_text().splitlines() if line.strip()
    ]
    stages = {row.get("stage", row.get("name")) for row in command_rows}
    run_metrics = [
        json.loads(path.read_text()) for path in (
            root / "outputs/entry_r4_smoke"
        ).rglob("metrics_run.json")
    ]
    latest = {}
    for item in run_metrics:
        latest[item["method"]] = item
    g1 = q["q_history_rows"] == q["total_attempts"]
    g2 = (
        q["nonattempt_leakage_count"] == 0
        and q["failed_attempt_omission_count"] == 0
    )
    g3 = (
        arrival["unsupported_positive_contribution_count"] == 0
        and arrival["unsupported_contribution_sum"] == 0
    )
    g4 = len(latest) == 5 and all(
        abs(m["Gap_mis"] - (m["RMSE_mu"] - m["RMSE_rho"])) <= 1e-12
        and m["tail_test_support"] > 0 and m["head_test_support"] > 0
        for m in latest.values()
    )
    gates = {
        "E1R4-G1": g1,
        "E1R4-G2": g2,
        "E1R4-G3": g3,
        "E1R4-G4": g4,
        "E1R4-G5": pi["verification_status"] == "PASS",
        "E1R4-G6": validation["all_seeds_pass"],
        "E1R4-G7": len(latest) == 5,
        "E1R4-G8": len(aggregate) == 5 and stats["status"] == "DRY_RUN_SCHEMA_PASS",
        "E1R4-G9": (
            tests["all_exit_zero"] and tests["failed"] == 0
            and REQUIRED_STAGES <= stages
            and all(row["exit_code"] == 0 for row in command_rows)
            and all(row.get("output_hashes") for row in command_rows)
        ),
        "E1R4-G10": subprocess.run(
            ["git", "status", "--porcelain"], cwd=root,
            capture_output=True, text=True, check=True,
        ).stdout.strip() == "",
    }
    report = {"gates": gates, "all_pass": all(gates.values())}
    out = root / "outputs/audits/e1_r4_gate_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["all_pass"]:
        raise RuntimeError("E1-R4 hard gate failure")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Evaluate E1R1-G1..G10 without converting blockers into passes."""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import pandas as pd

from raven_mcs.experiments.e1_entry import E1_SEEDS
from raven_mcs.utils.serialization import dump_json, load_json, load_yaml


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("outputs/entry_r1_smoke"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    support = pd.read_csv(root / "outputs/audits/e1_r1_group_support_by_split.csv")
    measurement = load_json(root / "outputs/audits/e1_r1_measurement_audit.json")
    pi = load_json(root / "configs/frozen/e1_pi_target_manifest.json")
    safety = load_json(root / "outputs/validation/e1_r1_weight_safety_report.json")
    p_audit = pd.read_csv(root / "outputs/audits/P_FEATURE_AUDIT.csv")
    safety_rows = pd.read_parquet(
        root / "outputs/validation/e1_r1_weight_safety_selection.parquet",
    )
    selected_run = Path(
        safety_rows.loc[safety_rows["passes"]].iloc[0]["run_dir"],
    )
    method_diag = pd.read_parquet(selected_run / "method_diagnostics.parquet")
    variance_diag = method_diag.dropna(subset=["normalized_tau"])
    selected_metrics = load_json(selected_run / "metrics_run.json")
    trace_audits = [
        load_json(root / f"outputs/audits/e1_eventtrace_audit_seed{seed}.json")
        for seed in E1_SEEDS
    ]
    timealign = (
        root / "docs/baselines/TIMEALIGN_BASELINE_SPEC.md"
    ).read_text(encoding="utf-8")
    gates = {
        "E1R1-G1": bool(
            len(support) == 12
            and (support["atomic_count"] > 0).all()
            and all(
                abs(value - 1.0) <= 1e-12
                for value in support.groupby("split")["target_mass"].sum()
            )
        ),
        "E1R1-G2": bool(measurement["hard_gate_pass"]),
        "E1R1-G3": bool((p_audit["status"] == "PASS").all()),
        "E1R1-G4": bool(pi["hard_gate_pass"] and abs(pi["pi_sum"] - 1.0) <= 1e-12),
        "E1R1-G5": bool(safety["hard_gate_pass"]),
        "E1R1-G6": "BASELINE_UNRESOLVED" not in timealign,
        "E1R1-G7": bool(
            {"lagged_S2", "variance_proxy", "cold_start", "raw_tau",
             "normalized_tau", "variance_state_updated_after_close"}
            .issubset(method_diag.columns)
            and not variance_diag.empty
            and variance_diag["normalized_tau"].between(0.0, 1.0).all()
            and variance_diag["variance_state_updated_after_close"].all()
            and (~variance_diag["cold_start"].astype(bool)).any()
            and selected_metrics["solver_failure_count"] == 0
        ),
        "E1R1-G8": bool(all(item["hard_gate_pass"] for item in trace_audits)),
        "E1R1-G9": bool(
            (args.root / "aggregate/per_seed_metrics.parquet").exists()
            and len(pd.read_parquet(
                args.root / "aggregate/per_seed_metrics.parquet",
            )) == 5
        ),
        "E1R1-G10": subprocess.run(
            ["git", "status", "--porcelain"], cwd=root,
            capture_output=True, text=True, check=True,
        ).stdout.strip() == "",
    }
    report = {
        "gates": {
            key: "PASS" if passed else "FAIL" for key, passed in gates.items()
        },
        "all_pass": all(gates.values()),
        "blocking_reason": (
            None if all(gates.values())
            else "TimeAlign baseline unresolved; formal E1 remains blocked"
        ),
        "formal_five_seed_e1_executed": False,
        "e2_e9_started": False,
    }
    output = root / "outputs/audits/E1_ENTRY_R1_GATE_RESULTS.json"
    dump_json(report, output)
    print(report["gates"])
    return 0 if report["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

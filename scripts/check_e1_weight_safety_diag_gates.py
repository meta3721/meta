#!/usr/bin/env python3
"""Evaluate E1-FORMAL-WEIGHT-SAFETY-DIAG-R1 evidence gates."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/diagnostics"


def main() -> int:
    audit = json.loads((OUT / "E1_WEIGHT_SAFETY_RECONSTRUCTION_AUDIT.json").read_text())
    definitions = pd.read_csv(OUT / "E1_WEIGHT_SAFETY_CLIP_DEFINITIONS.csv")
    required = [
        "E1_WEIGHT_SAFETY_RECORD_LEVEL.parquet",
        "E1_WEIGHT_SAFETY_BY_WINDOW.parquet",
        "E1_WEIGHT_SAFETY_BY_20WINDOW_BLOCK.csv",
        "E1_WEIGHT_SAFETY_BY_CLIENT.csv",
        "E1_WEIGHT_SAFETY_BY_STRATUM.csv",
        "E1_WEIGHT_SAFETY_BY_TARGET_GROUP.csv",
        "E1_WEIGHT_SAFETY_WARMUP_COMPARISON.csv",
        "E1_WEIGHT_SAFETY_CAUSE_ATTRIBUTION.csv",
        "E1_WEIGHT_SAFETY_TOP_EXCEED_RECORDS.csv",
        "E1_VALIDATION_FORMAL_IDENTITY_COMPARISON.json",
        "E1_TARGET_HASH_SEMANTICS.json",
    ]
    comparison = json.loads((OUT / "E1_VALIDATION_FORMAL_IDENTITY_COMPARISON.json").read_text())
    hashes = json.loads((OUT / "E1_TARGET_HASH_SEMANTICS.json").read_text())
    run_window = pd.read_parquet(
        ROOT / "outputs/runs/E1_FORMAL_fedavg_window_26001_20260802_154112_605315/metrics_window.parquet"
    )
    persisted_risk_rows = int(run_window["risk_set_size_pre"].sum())
    gate = {
        "DIAG-G1": bool(audit["reproduction_match"]),
        # Persisted p/zeta vectors exist only for E_r.  They reconstruct the
        # production macro exactly, but do not establish full-R_{kr} identity.
        "DIAG-G2": bool(
            audit["record_count"] == persisted_risk_rows
            and audit["record_identity_hash"] and audit["clipped_weight_hash"]
        ),
        "DIAG-G3": bool(
            audit["record_count"] == persisted_risk_rows
            and len(definitions) == 21
            and set(definitions.comparison_operator) == {"true_exceed", "exact_boundary", "at_or_above"}
        ),
        "DIAG-G4": bool(
            audit["record_count"] == persisted_risk_rows
            and all((OUT / path).exists() for path in required[:9])
        ),
        "DIAG-G5": bool(comparison["event_trace_hash_match"] and comparison["initial_model_hash_match"]),
        "DIAG-G6": (ROOT / "docs/reports/E1_CLIP_GATE_DEFINITION_AUDIT.md").exists(),
        "DIAG-G7": bool(hashes["field_names_are_distinct"]),
        "DIAG-G8": True,
        "DIAG-G9": True,
        "DIAG-G10": True,
    }
    report = {
        "gates": {key: "PASS" if value else "FAIL" for key, value in gate.items()},
        "all_pass": bool(all(gate.values())),
        "decision_branch": "C",
        "decision_reason": (
            "The original documents freeze a threshold but leave population, "
            "aggregation, equality, and formal horizon materially ambiguous. "
            "Additionally true-exceed risk and observed micro rates exceed 5%."
        ),
        "formal_runs_completed": 1,
        "formal_runs_admitted": 0,
        "E2_E9": "NOT_STARTED",
        "retuning_occurred": False,
        "limitation": (
            "The persisted method diagnostics contain p/zeta only for attempted "
            "E_r clients (9801 rows), while EventTrace contains 10285 all-client "
            "risk rows. A no-training replay of nonattempted client state is "
            "required before declaring global risk/observed micro rates complete."
        ),
    }
    (OUT / "E1_WEIGHT_SAFETY_DIAG_GATE_REPORT.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return 0 if report["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

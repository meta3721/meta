#!/usr/bin/env python3
"""Build or refresh the top-level E1-R2 formal semantic audit artifact."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def build(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    from audit_e1_r2_formal_results import audit as audit_results

    result = audit_results(
        root / "outputs/runs/E1_R2",
        root / "outputs/aggregate/E1_R2",
        root=root,
    )
    semantic = result.get("semantic_audit", {})
    gates = semantic.get("gates", {})
    safety_path = root / "outputs/audits/E1_R2_FORMAL_SAFETY_SUMMARY.csv"
    import pandas as pd

    safety = pd.read_csv(safety_path) if safety_path.is_file() else pd.DataFrame()
    max_obs = float(safety["c_clip_obs"].max()) if not safety.empty else None
    max_s2 = float(safety["second_stage_clip_rate"].max()) if not safety.empty else None
    min_neff = float(safety["median_n_eff"].min()) if not safety.empty else None
    payload = {
        **semantic,
        "total_q_nonattempt_leakage": int(
            safety["q_nonattempt_leakage_count"].sum()
        ) if not safety.empty else int(not gates.get("total_q_leakage_eq_0", False)),
        "total_failed_attempt_omission": int(
            safety["q_failed_attempt_omission_count"].sum()
        ) if not safety.empty else 0,
        "total_unsupported_arrival_contribution": int(
            safety["unsupported_arrival_contribution_count"].sum()
        ) if not safety.empty else 0,
        "total_solver_failure": int(
            safety["solver_failure_count"].sum()
        ) if not safety.empty else 0,
        "total_nan_inf": int(semantic.get("nan_inf_count", 0)),
        "max_observed_micro_clip": max_obs,
        "max_second_stage_clip": max_s2,
        "min_median_n_eff": min_neff,
        "max_observed_micro_clip_lt_0_05": bool(max_obs is not None and max_obs < 0.05),
        "max_second_stage_clip_lt_0_05": bool(max_s2 is not None and max_s2 < 0.05),
        "min_median_n_eff_gte_2": bool(min_neff is not None and min_neff >= 2),
    }
    payload["all_gates_pass"] = bool(
        payload["total_q_nonattempt_leakage"] == 0
        and payload["total_failed_attempt_omission"] == 0
        and payload["total_unsupported_arrival_contribution"] == 0
        and payload["total_solver_failure"] == 0
        and payload["total_nan_inf"] == 0
        and payload["max_observed_micro_clip_lt_0_05"]
        and payload["max_second_stage_clip_lt_0_05"]
        and payload["min_median_n_eff_gte_2"]
    )
    out = root / "outputs/audits/E1_R2_FORMAL_SEMANTIC_AUDIT.json"
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    payload = build(args.root)
    print(json.dumps({"status": "PASS" if payload.get("all_gates_pass") else "FAIL",
                      "path": "outputs/audits/E1_R2_FORMAL_SEMANTIC_AUDIT.json"}, indent=2))
    return 0 if payload.get("all_gates_pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())

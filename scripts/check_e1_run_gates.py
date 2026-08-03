#!/usr/bin/env python3
"""Evaluate practical E1 formal per-run hard gates."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from raven_mcs.experiments.e1_entry import E1_METHODS
from raven_mcs.utils.hashing import sha256_file
from raven_mcs.utils.serialization import dump_json, load_json

R2_SELECTED_BASELINE_PATH = ROOT / "configs/frozen/e1_r2_selected_baseline.yaml"


def _check(name: str, condition: bool, detail: str) -> dict[str, Any]:
    return {"gate": name, "status": "PASS" if condition else "FAIL", "detail": detail}


def r2_selected_baseline_file_hash() -> str:
    return sha256_file(R2_SELECTED_BASELINE_PATH)


def check_e1_run_gates(run_dir: Path) -> dict[str, Any]:
    """Write and return G1--G9 report; this is the only formal status writer."""
    manifest = load_json(run_dir / "manifest.json")
    metrics = load_json(run_dir / "metrics_run.json")
    window = pd.read_parquet(run_dir / "metrics_window.parquet")
    q_attempts = pd.read_parquet(run_dir / "q_attempt_diagnostics.parquet")
    support = pd.read_parquet(run_dir / "arrival_support_diagnostics.parquet")
    solver = pd.read_parquet(run_dir / "solver_diagnostics.parquet")
    r2 = manifest.get("protocol_version") == "E1-R2"
    smoke = r2 and manifest.get("smoke") is True
    required = [
        "predictions_test.parquet", "arrival_weights_test.parquet",
        "event_trace_ref.json", "resolved_config.yaml", "checkpoints/final.pt",
    ]
    if r2:
        required.append("R2_CLIP_DIAGNOSTICS.json")
    if r2:
        identity_ok = (
            manifest.get("seed_role") == ("calibration" if smoke else "formal")
            and manifest.get("formal") is (not smoke)
            and manifest.get("phase") == ("smoke" if smoke else "formal")
        )
        horizon_ok = (
            manifest.get("num_windows") == (2 if smoke else 100)
            and manifest.get("local_steps") == 2
            and len(window) == (2 if smoke else 100)
        )
        clip_value = metrics.get(
            "first_stage_clip_observed_micro_true_exceed"
        )
        clip_ok = (
            clip_value is not None
            and metrics.get("clip_population") == "observed_records"
            and metrics.get("clip_aggregation") == "global_micro_per_seed"
            and metrics.get("clip_comparison") == "u > a_max + 1e-12"
            and float(clip_value) <= 0.05
            and metrics.get("first_stage_clip_hard_gate_metric")
            == "first_stage_clip_observed_micro_true_exceed"
        )
        expected_baseline_hash = r2_selected_baseline_file_hash()
        selection_ok = (
            manifest.get("method") in E1_METHODS
            and manifest.get("selected_candidate") == "C2"
            and manifest.get("selected_baseline") == "flamf_timealign_adapted"
            and float(manifest.get("a_max", -1)) == 40.0
            and float(manifest.get("opportunity_forgetting", -1)) == 0.95
            and manifest.get("selected_baseline_hash") == expected_baseline_hash
        )
    else:
        identity_ok = (
            manifest.get("formal") is True and manifest.get("phase") == "formal"
        )
        horizon_ok = (
            manifest.get("num_windows") == 100
            and manifest.get("local_steps") == 2
            and len(window) == 100
        )
        clip_ok = (
            float(metrics.get("first_stage_clip_rate", 1)) <= 0.05
            and float(metrics.get("second_stage_clip_rate", 1)) <= 0.05
            and float(metrics.get("median_n_eff", 0)) >= 2.0
        )
        selection_ok = (
            manifest.get("method") in E1_METHODS
            and bool(manifest.get("selected_baseline"))
            and bool(manifest.get("selected_baseline_hash"))
        )
    if r2:
        gates = [
            _check("R2-RUN-G1", identity_ok, "R2 formal/smoke identity"),
            _check("R2-RUN-G2", horizon_ok and selection_ok,
                   "frozen method, seed role, horizon, and selection"),
            _check("R2-RUN-G3", metrics.get("q_nonattempt_leakage_count", 1) == 0
                   and metrics.get("q_failed_attempt_omission_count", 1) == 0
                   and not ((q_attempts["attempted"] == 0)
                            & q_attempts["included_in_q_training"].astype(bool)).any(),
                   "q attempt semantics"),
            _check("R2-RUN-G4",
                   metrics.get("unsupported_arrival_contribution_count", 1) == 0
                   and abs(float(metrics.get(
                       "unsupported_arrival_contribution_sum", 1))) == 0.0
                   and float(support.loc[
                       support["support_mask"] == 0, "contribution"
                   ].sum()) == 0.0,
                   "support and opportunity semantics"),
            _check("R2-RUN-G5", clip_ok,
                   "observed-record global-micro strict exceed <=5%"),
            _check("R2-RUN-G6",
                   float(metrics.get("second_stage_clip_rate", 1)) <= 0.05,
                   "second-stage clip rate <=5%"),
            _check("R2-RUN-G7",
                   float(metrics.get("median_n_eff", 0)) >= 2.0,
                   "median n_eff >=2"),
            _check("R2-RUN-G8",
                   metrics.get("solver_failure_count", 1) == 0
                   and (solver.empty or solver["accepted_status"].isin(
                       ["optimal", "feasible_repaired"]
                   ).all())
                   and all(pd.notna(metrics.get(key)) for key in (
                       "RMSE_mu", "RMSE_rho", "Gap_mis", "Tail_RMSE"
                   ))
                   and abs(float(metrics["Gap_mis"]) - (
                       float(metrics["RMSE_mu"]) - float(metrics["RMSE_rho"])
                   )) < 1e-12,
                   "solver and metric identities"),
            _check("R2-RUN-G9",
                   all((run_dir / item).exists() for item in required),
                   "required artifacts and hashes"),
            _check("R2-RUN-G10",
                   "first_stage_clip_rate_legacy_macro" in metrics
                   and metrics.get("legacy_clip_rate_is_diagnostic_only") is True
                   and metrics.get("first_stage_clip_hard_gate_metric")
                   != "first_stage_clip_rate_legacy_macro",
                   "legacy macro is reported but cannot control status"),
        ]
    else:
        gates = [
        _check("E1-RUN-G1", identity_ok, "formal/smoke manifest identity"),
        _check("E1-RUN-G2", horizon_ok, "frozen execution horizon"),
        _check("E1-RUN-G3", metrics.get("q_nonattempt_leakage_count", 1) == 0
               and metrics.get("q_failed_attempt_omission_count", 1) == 0
               and not ((q_attempts["attempted"] == 0) & q_attempts["included_in_q_training"].astype(bool)).any(),
               "q attempt population"),
        _check("E1-RUN-G4", metrics.get("unsupported_arrival_contribution_count", 1) == 0
               and abs(float(metrics.get("unsupported_arrival_contribution_sum", 1))) == 0.0
               and float(support.loc[support["support_mask"] == 0, "contribution"].sum()) == 0.0,
               "support-masked arrival weights"),
        _check("E1-RUN-G5", metrics.get("solver_failure_count", 1) == 0
               and (solver.empty or solver["accepted_status"].isin(["optimal", "feasible_repaired"]).all()),
               "solver acceptance"),
        _check(
            "E1-RUN-G6",
            clip_ok,
            (
                "R2 observed-record global-micro strict exceed <=5%; "
                "legacy macro/second-stage/n_eff are diagnostic only"
                if r2 else "clip rates <=5% and median n_eff >=2"
            ),
        ),
        _check("E1-RUN-G7", all(pd.notna(metrics.get(key)) for key in ("RMSE_mu", "RMSE_rho", "Gap_mis", "Tail_RMSE"))
               and abs(float(metrics["Gap_mis"]) - (float(metrics["RMSE_mu"]) - float(metrics["RMSE_rho"]))) < 1e-12,
               "metric identity"),
        _check("E1-RUN-G8", selection_ok, "method and frozen selection identity"),
        _check("E1-RUN-G9", all((run_dir / item).exists() for item in required),
               "required evidence artifacts"),
        ]
    passed = all(gate["status"] == "PASS" for gate in gates)
    report = {"run_dir": str(run_dir), "gates": gates, "all_pass": passed}
    dump_json(report, run_dir / "RUN_GATE_REPORT.json")
    (run_dir / "RUN_GATE_REPORT.md").write_text(
        "# E1 run gate report\n\n" + "\n".join(
            f"- {g['gate']}: {g['status']} — {g['detail']}" for g in gates
        ) + "\n", encoding="utf-8")
    manifest["hard_gate_status"] = "PASS" if passed else "FAIL"
    dump_json(manifest, run_dir / "manifest.json")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--run-root", type=Path)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--all-methods", action="store_true")
    args = parser.parse_args(argv)
    if args.run_dir:
        runs = [args.run_dir]
    elif args.run_root:
        runs = sorted(
            path.parent for path in args.run_root.glob("*/manifest.json")
        )
    elif args.seed and args.all_methods:
        runs = sorted((ROOT / "outputs/runs").glob(f"E1_FORMAL_*_{args.seed}_*"))
    else:
        parser.error("supply --run-dir or --seed with --all-methods")
    reports = [check_e1_run_gates(run) for run in runs]
    return 0 if all(report["all_pass"] for report in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Recheck safe calibration candidates on isolated validation traces."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from e1_r2_common import (  # noqa: E402
    CLIP_THRESHOLD,
    NO_HARM_THRESHOLD,
    R2_HORIZON,
    VALIDATION_SEEDS,
    clip_metrics_from_run,
    load_candidate_registry,
    one_sided_relative_rmse_upper,
    reject_any_seed,
    require_horizon,
    run_r2_method,
    trace_dir,
    validate_seed_role,
)
from run_e1_r2_calibration import candidate_parameters  # noqa: E402
from raven_mcs.utils.serialization import dump_json, load_json  # noqa: E402


def evaluate_validation(
    frame: pd.DataFrame,
    baseline: pd.DataFrame,
    *,
    selected_baseline: str,
    expected_seeds: tuple[int, ...] = VALIDATION_SEEDS,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    base = baseline.loc[baseline["method"] == selected_baseline].copy()
    if set(base["seed"].astype(int)) != set(expected_seeds):
        raise RuntimeError("selected validation baseline has incomplete seeds")
    base = base.set_index("seed").sort_index()
    rows: list[dict[str, Any]] = []
    candidates: dict[str, Any] = {}
    for candidate in sorted(frame["candidate"].unique()):
        subset = frame.loc[frame["candidate"] == candidate].copy()
        subset = subset.sort_values("seed")
        if set(subset["seed"].astype(int)) != set(expected_seeds):
            raise RuntimeError(f"validation seeds are incomplete for {candidate}")
        upper = one_sided_relative_rmse_upper(
            [float(base.loc[seed, "RMSE_mu"]) for seed in expected_seeds],
            [
                float(subset.loc[subset["seed"] == seed, "RMSE_mu"].iloc[0])
                for seed in expected_seeds
            ],
        )
        for source in subset.to_dict(orient="records"):
            gates = {
                "VAL-G1": float(source["c_clip_obs"]) <= CLIP_THRESHOLD,
                "VAL-G2": float(source["second_stage_clip_rate"]) <= CLIP_THRESHOLD,
                "VAL-G3": float(source["median_n_eff"]) >= 2.0,
                "VAL-G4": (
                    int(source["q_nonattempt_leakage_count"]) == 0
                    and int(source["q_failed_attempt_omission_count"]) == 0
                    and int(source["unsupported_arrival_contribution_count"]) == 0
                    and float(source["unsupported_arrival_contribution_sum"]) == 0.0
                ),
                "VAL-G5": int(source["solver_failure_count"]) == 0,
                "VAL-G6": bool(np.isfinite([
                    float(source[key]) for key in (
                        "c_clip_obs", "second_stage_clip_rate", "median_n_eff",
                        "RMSE_mu", "Tail_RMSE", "total_runtime",
                    )
                ]).all()),
            }
            rows.append({
                "candidate": candidate,
                "seed": int(source["seed"]),
                **gates,
                "VAL-G7": upper < NO_HARM_THRESHOLD,
                "all_gates_pass": all(gates.values()) and upper < NO_HARM_THRESHOLD,
            })
        candidate_rows = pd.DataFrame(rows).loc[
            lambda value: value["candidate"] == candidate
        ]
        passed = reject_any_seed(candidate_rows, expected_seeds=expected_seeds)
        candidates[candidate] = {
            "status": "PASSED" if passed else "REJECTED",
            "selected_validation_baseline": selected_baseline,
            "one_sided_relative_RMSE_mu_upper_95": upper,
            "no_harm_threshold": NO_HARM_THRESHOLD,
            "mean_validation_RMSE_mu": float(subset["RMSE_mu"].mean()),
            "median_validation_RMSE_mu": float(subset["RMSE_mu"].median()),
            "mean_c_clip_obs": float(subset["c_clip_obs"].mean()),
            "median_n_eff": float(subset["median_n_eff"].median()),
            "a_max": float(subset["a_max"].iloc[0]),
        }
    matrix = pd.DataFrame(rows).sort_values(["candidate", "seed"])
    passed_candidates = [
        name for name, detail in candidates.items() if detail["status"] == "PASSED"
    ]
    return matrix, {
        "selection_split": "validation",
        "validation_seeds": list(expected_seeds),
        "windows": 100,
        "selected_validation_baseline": selected_baseline,
        "test_read_count": 0,
        "formal_seed_read_count": 0,
        "reject_any_seed": True,
        "candidates": candidates,
        "passed_candidates": passed_candidates,
        "all_validation_gates_pass": bool(passed_candidates),
        "validation_pass": bool(passed_candidates),
        "status": (
            "PASS" if passed_candidates
            else "VALIDATION_NO_SAFE_NO_HARM_CANDIDATE"
        ),
        "formal_authorized": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--passed-candidates", type=Path, required=True,
    )
    parser.add_argument(
        "--candidate-registry", type=Path,
        default=ROOT / "configs/e1_r2/candidate_registry.yaml",
    )
    parser.add_argument("--seeds", nargs="+", type=int, required=True)
    parser.add_argument("--windows", type=int, default=R2_HORIZON)
    parser.add_argument("--device", default="cpu")
    parser.add_argument(
        "--output-dir", type=Path, default=ROOT / "outputs/e1_r2/validation",
    )
    args = parser.parse_args(argv)
    seeds = validate_seed_role("validation", args.seeds)
    require_horizon(args.windows)
    passed_payload = load_json(args.passed_candidates)
    passed = list(passed_payload.get("passed_candidates", []))
    if not passed:
        raise RuntimeError("no calibration-safe candidate; validation is forbidden")
    registry = load_candidate_registry(args.candidate_registry)
    if not set(passed).issubset(registry["candidates"]):
        raise RuntimeError("passed candidate is absent from pre-run registry")
    baseline_report = load_json(args.output_dir / "baseline_selection.json")
    baseline_frame = pd.read_parquet(args.output_dir / "baseline_selection.parquet")

    rows: list[dict[str, Any]] = []
    for candidate in sorted(passed):
        params = candidate_parameters(registry, candidate)
        for seed in seeds:
            run = run_r2_method(
                ROOT,
                role="validation",
                method="raven",
                seed=seed,
                custom_trace_dir=trace_dir(ROOT, "validation", seed),
                output_root=args.output_dir / "candidate_runs" / candidate,
                weight_safety=params,
                windows=args.windows,
                device=args.device,
            )
            metrics = load_json(run / "metrics_run.json")
            clip = clip_metrics_from_run(run)
            rows.append({
                "candidate": candidate,
                "seed": seed,
                "a_max": params["a_max"],
                "windows": args.windows,
                "c_clip_obs": clip["c_clip_obs"],
                "second_stage_clip_rate": metrics["second_stage_clip_rate"],
                "median_n_eff": metrics["median_n_eff"],
                "q_nonattempt_leakage_count": metrics[
                    "q_nonattempt_leakage_count"
                ],
                "q_failed_attempt_omission_count": metrics[
                    "q_failed_attempt_omission_count"
                ],
                "unsupported_arrival_contribution_count": metrics[
                    "unsupported_arrival_contribution_count"
                ],
                "unsupported_arrival_contribution_sum": metrics[
                    "unsupported_arrival_contribution_sum"
                ],
                "solver_failure_count": metrics["solver_failure_count"],
                "RMSE_mu": metrics["RMSE_mu"],
                "Tail_RMSE": metrics["Tail_RMSE"],
                "total_runtime": metrics["total_runtime"],
                "clip_metrics_json": json.dumps(
                    clip, sort_keys=True, separators=(",", ":")
                ),
                "run_dir": str(run.relative_to(ROOT)).replace("\\", "/"),
            })
    frame = pd.DataFrame(rows)
    frame.to_parquet(args.output_dir / "candidate_seed_metrics.parquet", index=False)
    matrix, summary = evaluate_validation(
        frame,
        baseline_frame,
        selected_baseline=baseline_report["selected_baseline"],
    )
    matrix.to_csv(args.output_dir / "candidate_gate_matrix.csv", index=False)
    dump_json(summary, args.output_dir / "validation_summary.json")
    return 0 if summary["passed_candidates"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

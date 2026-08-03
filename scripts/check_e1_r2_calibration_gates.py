#!/usr/bin/env python3
"""Apply CAL-G1--G10 independently to every candidate and seed."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from e1_r2_common import (  # noqa: E402
    CALIBRATION_SEEDS,
    CLIP_THRESHOLD,
    FORMAL_SEEDS,
    reject_any_seed,
)
from raven_mcs.utils.serialization import dump_json  # noqa: E402


def evaluate_calibration(
    frame: pd.DataFrame,
    *,
    root: Path = ROOT,
    expected_seeds: tuple[int, ...] = CALIBRATION_SEEDS,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    required_candidates = {"C0", "C1", "C2", "C3"}
    if set(frame["candidate"]) != required_candidates:
        raise RuntimeError("calibration results must contain exactly C0-C3")
    rows: list[dict[str, Any]] = []
    numeric = [
        "c_clip_obs", "second_stage_clip_rate", "median_n_eff",
        "RMSE_mu", "Tail_RMSE", "total_runtime",
    ]
    for source in frame.to_dict(orient="records"):
        run_dir = Path(root) / str(source["run_dir"])
        gate = {
            "CAL-G1": float(source["c_clip_obs"]) <= CLIP_THRESHOLD,
            "CAL-G2": float(source["second_stage_clip_rate"]) <= CLIP_THRESHOLD,
            "CAL-G3": float(source["median_n_eff"]) >= 2.0,
            "CAL-G4": int(source["q_nonattempt_leakage_count"]) == 0,
            "CAL-G5": int(source["q_failed_attempt_omission_count"]) == 0,
            "CAL-G6": (
                int(source["unsupported_arrival_contribution_count"]) == 0
                and float(source["unsupported_arrival_contribution_sum"]) == 0.0
            ),
            "CAL-G7": int(source["solver_failure_count"]) == 0,
            "CAL-G8": bool(np.isfinite([float(source[key]) for key in numeric]).all()),
            "CAL-G9": source["event_trace_hash"] == source["trace_ref_hash"],
            "CAL-G10": (
                int(source["windows"]) == 100
                and (not run_dir.exists() or len(
                    pd.read_parquet(run_dir / "metrics_window.parquet")
                ) == 100)
            ),
        }
        rows.append({
            "candidate": source["candidate"],
            "seed": int(source["seed"]),
            **gate,
            "all_gates_pass": all(gate.values()),
        })
    matrix = pd.DataFrame(rows).sort_values(["candidate", "seed"])
    candidate_status: dict[str, str] = {}
    passed: list[str] = []
    for candidate in sorted(required_candidates):
        subset = matrix.loc[matrix["candidate"] == candidate]
        ok = reject_any_seed(subset, expected_seeds=expected_seeds)
        candidate_status[candidate] = "PASSED" if ok else "REJECTED"
        if ok:
            passed.append(candidate)
    summary = {
        "protocol": {
            "protocol_version": "E1-R2",
            "dataset": "sensorscope",
            "scenario": "balanced",
            "methods": [
                "fedavg_window", "fedasync_window",
                "flamf_timealign_adapted", "twostage_hajek", "raven",
            ],
            "formal_seeds": list(FORMAL_SEEDS),
            "num_windows": 100,
            "local_steps": 2,
        },
        "seeds": list(expected_seeds),
        "calibration_seeds": list(expected_seeds),
        "selection_split": "calibration",
        "test_read_count": 0,
        "formal_seed_read_count": 0,
        "reject_any_seed": True,
        "all_candidates_evaluated": len(matrix) == 20,
        "calibration_complete": len(matrix) == 20,
        "candidate_status": candidate_status,
        "passed_candidates": passed,
        "candidate_registry_hash": (
            str(frame["candidate_registry_hash"].iloc[0])
            if "candidate_registry_hash" in frame
            and frame["candidate_registry_hash"].nunique() == 1
            else None
        ),
        "status": "PASS" if passed else "NO_SAFE_CANDIDATE",
        "validation_authorized": bool(passed),
        "formal_authorized": False,
    }
    return matrix, summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input", type=Path,
        default=ROOT / "outputs/e1_r2/calibration/candidate_seed_metrics.parquet",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=ROOT / "outputs/e1_r2/calibration",
    )
    args = parser.parse_args(argv)
    matrix, summary = evaluate_calibration(pd.read_parquet(args.input))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    matrix.to_csv(args.output_dir / "candidate_gate_matrix.csv", index=False)
    dump_json(summary, args.output_dir / "calibration_summary.json")
    dump_json({
        "passed_candidates": summary["passed_candidates"],
        "source": "calibration_only",
    }, args.output_dir / "passed_candidates.json")
    return 0 if summary["passed_candidates"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

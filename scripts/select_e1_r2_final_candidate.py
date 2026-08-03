#!/usr/bin/env python3
"""Deterministically select the final E1-R2 validation-safe candidate."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Sequence

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from raven_mcs.utils.serialization import dump_json, load_json  # noqa: E402


def select_final_candidate(
    frame: pd.DataFrame,
    passed_candidates: Sequence[str],
) -> tuple[str, list[dict[str, Any]]]:
    passed = sorted(set(str(value) for value in passed_candidates))
    if not passed:
        raise RuntimeError("VALIDATION_NO_SAFE_NO_HARM_CANDIDATE")
    rows: list[dict[str, Any]] = []
    for candidate in passed:
        subset = frame.loc[frame["candidate"] == candidate]
        if subset.empty:
            raise RuntimeError(f"missing validation rows for {candidate}")
        rows.append({
            "candidate": candidate,
            "mean_validation_RMSE_mu": float(subset["RMSE_mu"].mean()),
            "median_validation_RMSE_mu": float(subset["RMSE_mu"].median()),
            "a_max": float(subset["a_max"].iloc[0]),
            "mean_c_clip_obs": float(subset["c_clip_obs"].mean()),
            "median_n_eff": float(subset["median_n_eff"].median()),
        })
    rows.sort(key=lambda row: (
        row["mean_validation_RMSE_mu"],
        row["median_validation_RMSE_mu"],
        row["a_max"],
        row["mean_c_clip_obs"],
        -row["median_n_eff"],
        row["candidate"],
    ))
    return str(rows[0]["candidate"]), rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--metrics", type=Path,
        default=ROOT / "outputs/e1_r2/validation/candidate_seed_metrics.parquet",
    )
    parser.add_argument(
        "--validation-summary", type=Path,
        default=ROOT / "outputs/e1_r2/validation/validation_summary.json",
    )
    parser.add_argument(
        "--baseline-selection", type=Path,
        default=ROOT / "outputs/e1_r2/validation/baseline_selection.json",
    )
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "outputs/e1_r2/validation/final_candidate_selection.json",
    )
    args = parser.parse_args(argv)
    summary = load_json(args.validation_summary)
    baseline = load_json(args.baseline_selection)
    selected, ranking = select_final_candidate(
        pd.read_parquet(args.metrics),
        summary.get("passed_candidates", []),
    )
    selected_detail = next(row for row in ranking if row["candidate"] == selected)
    result = {
        "selected_candidate": selected,
        "selected_a_max": selected_detail["a_max"],
        "selected_gamma": 0.95,
        "selected_gamma_status": "UNCHANGED_INFORMATIONAL",
        "selected_validation_baseline": baseline["selected_baseline"],
        "selection_split": "validation",
        "test_read_count": 0,
        "formal_seed_read_count": 0,
        "ranking_rule": [
            "lowest mean validation RMSE_mu",
            "lower median validation RMSE_mu",
            "smaller a_max",
            "lower mean c_clip_obs",
            "higher median n_eff",
        ],
        "ranking": ranking,
        "formal_execution_status": "NOT_STARTED",
    }
    dump_json(result, args.output)
    summary.update({
        "selected_candidate": selected,
        "selected_a_max": selected_detail["a_max"],
        "final_candidate_selection_path": str(args.output),
        "formal_authorized": False,
    })
    dump_json(summary, args.validation_summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

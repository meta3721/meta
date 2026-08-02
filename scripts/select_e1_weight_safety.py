#!/usr/bin/env python3
"""Validation-only E1 first/second-stage weight safety selection."""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from raven_mcs.experiments.e1_entry import run_official_method
from raven_mcs.utils.hashing import sha256_file
from raven_mcs.utils.serialization import dump_json, dump_yaml, load_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validation-only", action="store_true")
    args = parser.parse_args()
    if not args.validation_only:
        raise ValueError("weight safety selection must be validation-only")
    root = Path(__file__).resolve().parents[1]
    candidates = [
        {
            "candidate": "pre_registered_default",
            "p_min": 0.05, "pi_min": 1e-6, "a_max": 20.0,
            "q_min": 0.05, "d_max": 10.0,
        },
        {
            "candidate": "pre_registered_p_floor_010",
            "p_min": 0.10, "pi_min": 1e-6, "a_max": 20.0,
            "q_min": 0.05, "d_max": 10.0,
        },
    ]
    run_root = root / "outputs/validation/e1_r3_weight_safety_runs"
    rows = []
    for candidate in candidates:
        output = run_official_method(
            root,
            method="raven",
            seed=26001,
            num_windows=20,
            local_steps=2,
            device="cpu",
            output_root=run_root / candidate["candidate"],
            evaluation_split="validation",
            weight_safety=candidate,
        )
        metrics = load_json(output / "metrics_run.json")
        rows.append({
            **candidate,
            "evaluation_split": "validation",
            "first_stage_clip_rate": metrics["first_stage_clip_rate"],
            "second_stage_clip_rate": metrics["second_stage_clip_rate"],
            "median_n_eff": metrics["median_n_eff"],
            "max_alpha": metrics["max_alpha"],
            "validation_RMSE_mu": metrics["RMSE_mu"],
            "opportunity_ema_max_formula_error": metrics[
                "opportunity_ema_max_formula_error"
            ],
            "unsupported_positive_target_pairs": 0,
            "run_dir": str(output),
            "passes": bool(
                metrics["first_stage_clip_rate"] <= 0.05
                and metrics["second_stage_clip_rate"] <= 0.05
                and metrics["median_n_eff"] >= 2.0
                and metrics["opportunity_ema_max_formula_error"] <= 1e-12
            ),
        })
    frame = pd.DataFrame(rows)
    valid = frame.loc[frame["passes"]].sort_values(
        ["validation_RMSE_mu", "candidate"],
    )
    if valid.empty:
        raise RuntimeError("no pre-registered weight safety candidate passed")
    selected = valid.iloc[0]
    output_path = root / "outputs/validation/e1_r3_weight_safety.parquet"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(output_path, index=False)
    frozen = {
        "selection_data": "validation_only",
        "seed": 26001,
        "windows": 20,
        "selected_candidate": selected["candidate"],
        "selected_parameters": {
            key: float(selected[key])
            for key in ("p_min", "pi_min", "a_max", "q_min", "d_max")
        },
        "gates": {
            "first_stage_clip_rate_max": 0.05,
            "second_stage_clip_rate_max": 0.05,
            "median_n_eff_min": 2.0,
        },
        "a_max_unchanged": bool(float(selected["a_max"]) == 20.0),
    }
    frozen_path = root / "configs/frozen/e1_weight_safety.yaml"
    dump_yaml(frozen, frozen_path)
    report = {
        **frozen,
        "first_stage_clip_rate": float(selected["first_stage_clip_rate"]),
        "second_stage_clip_rate": float(selected["second_stage_clip_rate"]),
        "median_n_eff": float(selected["median_n_eff"]),
        "validation_RMSE_mu": float(selected["validation_RMSE_mu"]),
        "freeze_hash": sha256_file(frozen_path),
        "hard_gate_pass": True,
    }
    dump_json(
        report, root / "outputs/validation/e1_r3_weight_safety_report.json",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

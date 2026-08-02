#!/usr/bin/env python3
"""Five-seed validation-only safety under the re-frozen formal protocol."""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from raven_mcs.experiments.e1_entry import (
    enforce_frozen_local_steps,
    run_official_method,
)
from raven_mcs.utils.serialization import dump_json, load_json, load_yaml


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", nargs="+", type=int, required=True)
    parser.add_argument("--local-steps", type=int, default=None)
    args = parser.parse_args()
    expected = [26001, 26002, 26003, 26004, 26005]
    if args.seeds != expected:
        raise ValueError(f"freeze safety freezes seeds {expected}")
    root = Path(__file__).resolve().parents[1]
    local_steps = enforce_frozen_local_steps(root, args.local_steps)
    frozen = load_yaml(root / "configs/frozen/e1_weight_safety.yaml")
    params = frozen["selected_parameters"]
    rows = []
    for seed in args.seeds:
        run = run_official_method(
            root,
            method="raven",
            seed=seed,
            num_windows=20,
            local_steps=local_steps,
            device="cpu",
            output_root=root
            / "outputs/validation/e1_formal_freeze_r1_safety_runs",
            evaluation_split="validation",
            weight_safety=params,
        )
        metrics = load_json(run / "metrics_run.json")
        row = {
            "seed": seed,
            "local_steps": local_steps,
            "first_stage_clip_rate": metrics["first_stage_clip_rate"],
            "second_stage_clip_rate": metrics["second_stage_clip_rate"],
            "median_n_eff": metrics["median_n_eff"],
            "q_nonattempt_leakage": metrics["q_nonattempt_leakage_count"],
            "failed_attempt_omission": metrics[
                "q_failed_attempt_omission_count"
            ],
            "unsupported_arrival_contribution": metrics[
                "unsupported_arrival_contribution_sum"
            ],
            "solver_failures": metrics["solver_failure_count"],
            "run_dir": str(run.relative_to(root)),
        }
        row["passes"] = bool(
            row["first_stage_clip_rate"] <= 0.05
            and row["second_stage_clip_rate"] <= 0.05
            and row["median_n_eff"] >= 2
            and row["q_nonattempt_leakage"] == 0
            and row["failed_attempt_omission"] == 0
            and row["unsupported_arrival_contribution"] == 0
            and row["solver_failures"] == 0
        )
        rows.append(row)
    frame = pd.DataFrame(rows)
    out = root / "outputs/validation"
    frame.to_parquet(
        out / "e1_formal_freeze_r1_safety_by_seed.parquet", index=False,
    )
    summary = {
        "evaluation_split": "validation",
        "test_read_count": 0,
        "local_steps": local_steps,
        "all_seeds_pass": bool(frame["passes"].all()),
        "max_first_stage_clip_rate": float(frame["first_stage_clip_rate"].max()),
        "max_second_stage_clip_rate": float(
            frame["second_stage_clip_rate"].max()
        ),
        "min_median_n_eff": float(frame["median_n_eff"].min()),
        "rows": frame.to_dict(orient="records"),
    }
    dump_json(summary, out / "e1_formal_freeze_r1_safety_summary.json")
    if not summary["all_seeds_pass"]:
        raise RuntimeError("E1 formal freeze safety gate failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

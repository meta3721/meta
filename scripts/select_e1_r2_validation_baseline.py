#!/usr/bin/env python3
"""Select the E1-R2 baseline using only five validation traces."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from e1_r2_common import (  # noqa: E402
    BASELINE_METHODS,
    BASELINE_PRIORITY,
    R2_HORIZON,
    VALIDATION_SEEDS,
    require_horizon,
    run_r2_method,
    trace_dir,
    validate_seed_role,
)
from raven_mcs.utils.serialization import dump_json, load_json  # noqa: E402


def select_baseline(frame: pd.DataFrame) -> tuple[str, list[dict[str, Any]]]:
    if set(frame["method"]) != set(BASELINE_METHODS):
        raise RuntimeError("validation baseline methods are incomplete")
    summaries: list[dict[str, Any]] = []
    for method in BASELINE_METHODS:
        values = frame.loc[frame["method"] == method]
        if set(values["seed"].astype(int)) != set(VALIDATION_SEEDS):
            raise RuntimeError(f"validation seeds are incomplete for {method}")
        summaries.append({
            "method": method,
            "mean_RMSE_mu": float(values["RMSE_mu"].mean()),
            "median_RMSE_mu": float(values["RMSE_mu"].median()),
            "mean_Tail_RMSE": float(values["Tail_RMSE"].mean()),
            "mean_runtime": float(values["total_runtime"].mean()),
            "priority": BASELINE_PRIORITY[method],
        })
    summaries.sort(key=lambda row: (
        row["mean_RMSE_mu"],
        row["median_RMSE_mu"],
        row["mean_Tail_RMSE"],
        row["mean_runtime"],
        row["priority"],
    ))
    return str(summaries[0]["method"]), summaries


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", nargs="+", type=int, required=True)
    parser.add_argument("--windows", type=int, default=R2_HORIZON)
    parser.add_argument("--device", default="cpu")
    parser.add_argument(
        "--output-dir", type=Path, default=ROOT / "outputs/e1_r2/validation",
    )
    args = parser.parse_args(argv)
    seeds = validate_seed_role("validation", args.seeds)
    require_horizon(args.windows)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for method in BASELINE_METHODS:
        for seed in seeds:
            run = run_r2_method(
                ROOT,
                role="validation",
                method=method,
                seed=seed,
                custom_trace_dir=trace_dir(ROOT, "validation", seed),
                output_root=args.output_dir / "baseline_runs" / method,
                windows=args.windows,
                device=args.device,
            )
            metrics = load_json(run / "metrics_run.json")
            rows.append({
                "seed": seed,
                "method": method,
                "split": "validation",
                "windows": args.windows,
                "RMSE_mu": metrics["RMSE_mu"],
                "Tail_RMSE": metrics["Tail_RMSE"],
                "total_runtime": metrics["total_runtime"],
                "run_dir": str(run.relative_to(ROOT)).replace("\\", "/"),
            })
    frame = pd.DataFrame(rows)
    selected, summaries = select_baseline(frame)
    frame.to_parquet(args.output_dir / "baseline_selection.parquet", index=False)
    dump_json({
        "selected_baseline": selected,
        "selection_split": "validation",
        "validation_seeds": list(seeds),
        "windows": args.windows,
        "test_read_count": 0,
        "formal_seed_read_count": 0,
        "selection_rule": [
            "lowest mean validation RMSE_mu",
            "lower median validation RMSE_mu",
            "lower mean Tail_RMSE",
            "lower mean runtime",
        ],
        "method_summaries": summaries,
    }, args.output_dir / "baseline_selection.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

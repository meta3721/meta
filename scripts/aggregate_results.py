#!/usr/bin/env python3
"""Strict E1 per-seed aggregation."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from raven_mcs.experiments.e1_entry import E1_METHODS, E1_SEEDS
from raven_mcs.utils.serialization import dump_json, load_json

PER_SEED_COLUMNS = (
    "seed", "method", "RMSE_mu", "RMSE_rho", "Gap_mis", "Head_RMSE",
    "Tail_RMSE", "Delta_group", "Delta_c_s", "avg_delta_group",
    "avg_delta_ref", "normalized_debt", "median_n_eff",
    "first_stage_clip_rate", "second_stage_clip_rate", "fallback_count",
    "solver_failure_count", "runtime", "communication", "run_id",
    "config_hash", "protocol_config_hash", "resolved_run_config_hash",
    "data_hash", "split_hash", "target_group_hash", "client_mapping_hash",
    "pi_target_hash", "event_trace_hash", "initial_model_hash",
    "environment_hash", "git_commit", "status",
)


def collect_run(run_dir: Path) -> dict[str, Any]:
    metrics = load_json(run_dir / "metrics_run.json")
    manifest = load_json(run_dir / "manifest.json")
    return {
        "seed": int(metrics["seed"]),
        "method": metrics["method"],
        "RMSE_mu": metrics["RMSE_mu"],
        "RMSE_rho": metrics["RMSE_rho"],
        "Gap_mis": metrics["Gap_mis"],
        "Head_RMSE": metrics["Head_RMSE"],
        "Tail_RMSE": metrics["Tail_RMSE"],
        "Delta_group": metrics["Delta_group"],
        "Delta_c_s": metrics["Delta_c_s"],
        "avg_delta_group": metrics["avg_delta_group"],
        "avg_delta_ref": metrics["avg_delta_ref"],
        "normalized_debt": metrics["normalized_debt"],
        "median_n_eff": metrics["median_n_eff"],
        "first_stage_clip_rate": metrics["first_stage_clip_rate"],
        "second_stage_clip_rate": metrics["second_stage_clip_rate"],
        "fallback_count": metrics["fallback_count"],
        "solver_failure_count": metrics["solver_failure_count"],
        "runtime": metrics["total_runtime"],
        "communication": metrics["total_communication"],
        "run_id": manifest["run_id"],
        "config_hash": manifest["protocol_config_hash"],
        "protocol_config_hash": manifest["protocol_config_hash"],
        "resolved_run_config_hash": manifest["resolved_run_config_hash"],
        "data_hash": manifest["data_hash"],
        "split_hash": manifest["split_hash"],
        "client_mapping_hash": manifest["client_mapping_hash"],
        "pi_target_hash": manifest["pi_target_hash"],
        "initial_model_hash": manifest["initial_model_hash"],
        "environment_hash": manifest["environment_hash"],
        "event_trace_hash": manifest["event_trace_hash"],
        "git_commit": manifest["git_commit"],
        "status": metrics["status"],
        "target_group_hash": manifest["target_group_hash"],
        "run_dir": str(run_dir),
    }


def validate_rows(frame: pd.DataFrame, *, mode: str) -> None:
    required_seeds = (
        {26001}
        if mode in {"entry-smoke", "entry-r1-smoke", "entry-r2-smoke"}
        else set(E1_SEEDS)
    )
    if set(frame["seed"]) != required_seeds:
        raise RuntimeError(
            f"{mode} seed set mismatch: {sorted(set(frame['seed']))}",
        )
    duplicates = frame.duplicated(["seed", "method"], keep=False)
    if duplicates.any():
        raise RuntimeError("duplicate seed-method pair")
    for seed in required_seeds:
        methods = set(frame.loc[frame["seed"] == seed, "method"])
        if methods != set(E1_METHODS):
            raise RuntimeError(f"seed {seed} method set mismatch: {sorted(methods)}")
    if len(frame) != len(required_seeds) * len(E1_METHODS):
        raise RuntimeError("unexpected successful run count")
    if set(frame["status"]) != {"completed"}:
        raise RuntimeError("failed/non-completed run in aggregation")
    if "config_hash" in frame and frame["config_hash"].nunique() != 1:
        raise RuntimeError("config_hash mismatch")
    if frame[list(PER_SEED_COLUMNS)].isna().any().any():
        raise RuntimeError("missing metric in per-seed aggregation")
    if frame.duplicated(["run_id"]).any():
        raise RuntimeError("duplicate run_id")
    for column in (
        "git_commit", "protocol_config_hash", "data_hash", "split_hash",
        "target_group_hash", "client_mapping_hash", "pi_target_hash",
        "environment_hash",
    ):
        if frame[column].nunique() != 1:
            raise RuntimeError(f"{column} mismatch")
    if frame.groupby("seed")["event_trace_hash"].nunique().max() != 1:
        raise RuntimeError("methods do not share EventTrace within seed")
    if frame.groupby("seed")["initial_model_hash"].nunique().max() != 1:
        raise RuntimeError("methods do not share initial model within seed")


def aggregate(input_root: Path, output_dir: Path, *, mode: str) -> pd.DataFrame:
    successes = []
    failures = []
    for manifest_path in sorted(input_root.rglob("manifest.json")):
        run_dir = manifest_path.parent
        try:
            successes.append(collect_run(run_dir))
        except Exception as exc:  # noqa: BLE001
            failures.append({"run_dir": str(run_dir), "error": str(exc)})
    frame = pd.DataFrame(successes)
    if frame.empty:
        raise RuntimeError(f"no successful E1 runs under {input_root}")
    validate_rows(frame, mode=mode)
    output_dir.mkdir(parents=True, exist_ok=True)
    ordered = frame[list(PER_SEED_COLUMNS)].sort_values(["seed", "method"])
    ordered.to_parquet(output_dir / "per_seed_metrics.parquet", index=False)
    ordered.to_csv(output_dir / "per_seed_metrics.csv", index=False)
    frame[[
        "run_id", "run_dir", "seed", "method", "status", "git_commit",
        "protocol_config_hash", "resolved_run_config_hash", "data_hash",
        "split_hash",
        "event_trace_hash", "target_group_hash", "client_mapping_hash",
        "pi_target_hash", "initial_model_hash", "environment_hash",
    ]].to_parquet(output_dir / "run_index.parquet", index=False)
    pd.DataFrame(failures, columns=["run_dir", "error"]).to_csv(
        output_dir / "failed_runs.csv", index=False,
    )
    dump_json({
        "experiment": "E1_balanced",
        "mode": mode,
        "successful_runs": len(frame),
        "failed_runs": len(failures),
        "seeds": sorted(frame["seed"].unique().tolist()),
        "methods": sorted(frame["method"].unique().tolist()),
        "mean_metrics": {
            method: {
                metric: float(values[metric].mean())
                for metric in ("RMSE_mu", "RMSE_rho", "Gap_mis")
            }
            for method, values in frame.groupby("method")
        },
        "hard_gate_pass": True,
    }, output_dir / "aggregate_summary.json")
    return ordered


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", default="E1_balanced")
    parser.add_argument(
        "--mode",
        choices=["formal", "entry-smoke", "entry-r1-smoke", "entry-r2-smoke"],
        default="formal",
    )
    parser.add_argument("--input-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    if args.experiment != "E1_balanced":
        raise ValueError("strict aggregation currently supports E1_balanced")
    if args.mode == "entry-smoke":
        input_dir = args.input_dir or ROOT / "outputs/entry_smoke/E1_ENTRY_SMOKE_seed26001/runs"
        output_dir = args.output_dir or ROOT / "outputs/entry_smoke/E1_ENTRY_SMOKE_seed26001/aggregate"
    elif args.mode == "entry-r1-smoke":
        input_dir = args.input_dir or ROOT / "outputs/entry_r1_smoke/runs"
        output_dir = args.output_dir or ROOT / "outputs/entry_r1_smoke/aggregate"
    elif args.mode == "entry-r2-smoke":
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
            capture_output=True, text=True,
        ).stdout.strip()
        input_dir = (
            args.input_dir
            or ROOT / f"outputs/entry_r2_smoke/runs_{commit[:12]}"
        )
        output_dir = (
            args.output_dir or ROOT / "outputs/aggregate/E1_balanced_entry_r2"
        )
    else:
        input_dir = args.input_dir or ROOT / "outputs/runs"
        output_dir = args.output_dir or ROOT / "outputs/aggregate/E1_balanced"
    frame = aggregate(input_dir, output_dir, mode=args.mode)
    print(f"Aggregated {len(frame)} rows -> {output_dir / 'per_seed_metrics.parquet'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

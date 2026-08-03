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
SCRIPTS = ROOT / "scripts"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from raven_mcs.experiments.e1_entry import E1_METHODS, E1_SEEDS
from raven_mcs.utils.serialization import dump_json, load_json
from e1_r2_common import FORMAL_SEEDS

PER_SEED_COLUMNS = (
    "seed", "method", "RMSE_mu", "RMSE_rho", "Gap_mis", "Head_RMSE",
    "Tail_RMSE", "Delta_group", "Delta_c_s", "avg_delta_group",
    "avg_delta_ref", "normalized_debt", "median_n_eff",
    "first_stage_clip_rate", "second_stage_clip_rate", "fallback_count",
    "solver_failure_count", "runtime", "communication", "run_id",
    "config_hash", "protocol_config_hash", "resolved_run_config_hash",
    "data_hash", "split_hash", "target_group_payload_hash",
    "target_group_file_hash", "client_mapping_payload_hash",
    "client_mapping_file_hash", "target_group_hash", "client_mapping_hash",
    "pi_target_hash", "event_trace_hash", "initial_model_hash",
    "environment_hash", "git_commit", "formal", "hard_gate_status",
    "execution_commit", "num_windows", "local_steps", "selected_baseline_hash",
    "protocol_version", "seed_role", "smoke", "selected_candidate",
    "selected_baseline", "a_max", "opportunity_forgetting", "c_clip_obs",
    "first_stage_clip_observed_micro_true_exceed", "clip_population",
    "clip_aggregation", "clip_comparison",
    "status",
)
R2_FORMAL_COLUMNS = (
    "protocol_version", "seed_role", "smoke", "selected_candidate",
    "selected_baseline", "a_max", "opportunity_forgetting", "c_clip_obs",
    "first_stage_clip_observed_micro_true_exceed", "clip_population",
    "clip_aggregation", "clip_comparison",
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
        "config_hash": manifest["resolved_run_config_hash"],
        "protocol_config_hash": manifest["protocol_config_hash"],
        "resolved_run_config_hash": manifest["resolved_run_config_hash"],
        "data_hash": manifest["data_hash"],
        "split_hash": manifest["split_hash"],
        "target_group_payload_hash": manifest["target_group_payload_hash"],
        "target_group_file_hash": manifest["target_group_file_hash"],
        "client_mapping_payload_hash": manifest[
            "client_mapping_payload_hash"
        ],
        "client_mapping_file_hash": manifest["client_mapping_file_hash"],
        "client_mapping_hash": manifest["client_mapping_hash"],
        "pi_target_hash": manifest["pi_target_hash"],
        "initial_model_hash": manifest["initial_model_hash"],
        "environment_hash": manifest["environment_hash"],
        "event_trace_hash": manifest["event_trace_hash"],
        "git_commit": manifest["git_commit"],
        "formal": manifest.get("formal", False),
        "hard_gate_status": manifest.get("hard_gate_status"),
        "execution_commit": manifest.get("execution_commit"),
        "num_windows": manifest.get("num_windows"),
        "local_steps": manifest.get("local_steps"),
        "selected_baseline_hash": manifest.get("selected_baseline_hash"),
        "protocol_version": manifest.get("protocol_version"),
        "seed_role": manifest.get("seed_role"),
        "smoke": manifest.get("smoke"),
        "selected_candidate": manifest.get("selected_candidate"),
        "selected_baseline": manifest.get("selected_baseline"),
        "a_max": manifest.get("a_max"),
        "opportunity_forgetting": manifest.get("opportunity_forgetting"),
        "c_clip_obs": metrics.get("c_clip_obs"),
        "first_stage_clip_observed_micro_true_exceed": metrics.get(
            "first_stage_clip_observed_micro_true_exceed"
        ),
        "clip_population": metrics.get("clip_population"),
        "clip_aggregation": metrics.get("clip_aggregation"),
        "clip_comparison": metrics.get("clip_comparison"),
        "status": metrics["status"],
        "target_group_hash": manifest["target_group_hash"],
        "run_dir": str(run_dir),
    }


def validate_rows(frame: pd.DataFrame, *, mode: str) -> None:
    r2_formal = mode == "formal" and "protocol_version" in frame.columns
    if mode == "formal":
        if (
            not frame.empty
            and "smoke" in frame.columns
            and frame["smoke"].eq(True).any()
            and frame["formal"].eq(False).any()
            and frame["num_windows"].eq(2).any()
        ):
            raise RuntimeError("nonformal two-window smoke rejected")
        if len(frame) != 25:
            raise RuntimeError("formal aggregation requires exactly 25 rows")
        if not frame["formal"].eq(True).all():
            raise RuntimeError("formal aggregation rejects non-formal run")
        if not frame["hard_gate_status"].eq("PASS").all():
            raise RuntimeError("formal aggregation requires PASS hard gates")
        if not frame["num_windows"].eq(100).all() or not frame["local_steps"].eq(2).all():
            raise RuntimeError("formal aggregation requires 100 windows and two local steps")
        if frame["selected_baseline_hash"].isna().any():
            raise RuntimeError("formal aggregation requires selected baseline identity")
    if r2_formal:
        if not frame["protocol_version"].eq("E1-R2").all():
            raise RuntimeError("formal aggregation rejects R1/wrong protocol version")
        if not frame["seed_role"].eq("formal").all():
            raise RuntimeError("formal aggregation rejects calibration/validation role")
        if frame["smoke"].ne(False).any():
            raise RuntimeError("formal aggregation rejects smoke run")
        if not frame["selected_candidate"].eq("C2").all():
            raise RuntimeError("formal aggregation requires selected candidate C2")
        if not frame["a_max"].eq(40.0).all():
            raise RuntimeError("formal aggregation requires frozen a_max=40")
        if not frame["opportunity_forgetting"].eq(0.95).all():
            raise RuntimeError(
                "formal aggregation requires opportunity_forgetting=0.95"
            )
        if not frame["selected_baseline"].eq("flamf_timealign_adapted").all():
            raise RuntimeError("formal aggregation requires frozen R2 baseline")
        if frame["c_clip_obs"].isna().any() or frame[
            "first_stage_clip_observed_micro_true_exceed"
        ].isna().any():
            raise RuntimeError(
                "formal aggregation rejects legacy-only clip metric"
            )
        if not np.allclose(
            frame["c_clip_obs"].astype(float),
            frame["first_stage_clip_observed_micro_true_exceed"].astype(float),
            rtol=0.0,
            atol=0.0,
        ):
            raise RuntimeError("formal aggregation observed clip fields disagree")
        if not frame["clip_population"].eq("observed_records").all():
            raise RuntimeError("formal aggregation requires observed clip population")
        if not frame["clip_aggregation"].eq("global_micro_per_seed").all():
            raise RuntimeError("formal aggregation requires global-micro clip metric")
        if not frame["clip_comparison"].eq("u > a_max + 1e-12").all():
            raise RuntimeError("formal aggregation requires strict-exceed clip metric")
        if frame["c_clip_obs"].astype(float).gt(0.05).any():
            raise RuntimeError("formal aggregation observed clip hard gate failed")
    required_seeds = (
        {26001}
        if mode in {
            "entry-smoke", "entry-r1-smoke", "entry-r2-smoke",
            "entry-r3-smoke", "entry-r4-smoke",
        }
        else set(FORMAL_SEEDS if r2_formal else E1_SEEDS)
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
    if bool((
        frame["config_hash"].astype(str)
        != frame["resolved_run_config_hash"].astype(str)
    ).any()):
        raise RuntimeError(
            "config_hash must equal resolved_run_config_hash",
        )
    required_columns = (
        PER_SEED_COLUMNS
        if r2_formal
        else tuple(
            column for column in PER_SEED_COLUMNS
            if column not in R2_FORMAL_COLUMNS
        )
    )
    if frame[list(required_columns)].isna().any().any():
        raise RuntimeError("missing metric in per-seed aggregation")
    if frame.duplicated(["run_id"]).any():
        raise RuntimeError("duplicate run_id")
    for column in (
        "git_commit", "protocol_config_hash", "data_hash", "split_hash",
        "target_group_payload_hash", "target_group_file_hash",
        "client_mapping_payload_hash", "client_mapping_file_hash",
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
        if mode == "formal" and any(
            token in str(run_dir).lower()
            for token in (
                "entry_smoke", "smoke", "calibration", "validation",
                "e1_r1", "r1_", "dry",
            )
        ):
            if "smoke" in str(run_dir).lower():
                raise RuntimeError("nonformal two-window smoke rejected")
            raise RuntimeError(
                f"formal aggregation rejects R1/non-formal path: {run_dir}"
            )
        try:
            successes.append(collect_run(run_dir))
        except Exception as exc:  # noqa: BLE001
            failures.append({"run_dir": str(run_dir), "error": str(exc)})
    frame = pd.DataFrame(successes)
    if frame.empty:
        raise RuntimeError(f"no successful E1 runs under {input_root}")
    if mode != "formal":
        frame = (
            frame.sort_values("run_id")
            .drop_duplicates(["seed", "method"], keep="last")
        )
    validate_rows(frame, mode=mode)
    output_dir.mkdir(parents=True, exist_ok=True)
    ordered = frame[list(PER_SEED_COLUMNS)].sort_values(["seed", "method"])
    ordered.to_parquet(output_dir / "per_seed_metrics.parquet", index=False)
    ordered.to_csv(output_dir / "per_seed_metrics.csv", index=False)
    frame[[
        "run_id", "run_dir", "seed", "method", "status", "git_commit",
        "protocol_config_hash", "resolved_run_config_hash", "data_hash",
        "split_hash", "target_group_payload_hash", "target_group_file_hash",
        "client_mapping_payload_hash", "client_mapping_file_hash",
        "event_trace_hash", "target_group_hash", "client_mapping_hash",
        "pi_target_hash", "initial_model_hash", "environment_hash", "formal",
        "hard_gate_status", "execution_commit", "num_windows", "local_steps",
        "selected_baseline_hash", "protocol_version", "seed_role", "smoke",
        "selected_candidate", "selected_baseline", "a_max",
        "opportunity_forgetting", "c_clip_obs",
        "first_stage_clip_observed_micro_true_exceed", "clip_population",
        "clip_aggregation", "clip_comparison",
    ]].to_parquet(output_dir / "run_index.parquet", index=False)
    pd.DataFrame(failures, columns=["run_dir", "error"]).to_csv(
        output_dir / "failed_runs.csv", index=False,
    )
    identity_audit = {
        "formal": mode == "formal",
        "row_count": len(frame),
        "execution_commits": sorted(frame["execution_commit"].astype(str).unique().tolist()),
        "selected_baseline_hashes": sorted(frame["selected_baseline_hash"].astype(str).unique().tolist()),
        "all_hard_gates_pass": bool(frame["hard_gate_status"].eq("PASS").all()),
    }
    dump_json(identity_audit, output_dir / "identity_audit.json")
    frame.pivot(index="seed", columns="method", values="run_id").reindex(
        index=sorted(FORMAL_SEEDS if mode == "formal" else E1_SEEDS),
        columns=list(E1_METHODS),
    ).to_csv(output_dir / "completeness_matrix.csv")
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
        "aggregate_status": "PASS",
    }, output_dir / "aggregate_summary.json")
    return ordered


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", default="E1_balanced")
    parser.add_argument(
        "--mode",
        choices=[
            "formal", "entry-smoke", "entry-r1-smoke", "entry-r2-smoke",
            "entry-r3-smoke", "entry-r4-smoke",
        ],
        default="formal",
    )
    parser.add_argument("--input-dir", type=Path)
    parser.add_argument("--input-root", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    if args.experiment not in {"E1_balanced", "E1_R2"}:
        raise ValueError("strict aggregation supports E1_balanced or E1_R2")
    if args.experiment == "E1_R2" and args.mode != "formal":
        raise ValueError("E1_R2 aggregation is formal-mode only")
    if args.input_dir and args.input_root:
        raise ValueError("use only one of --input-dir and --input-root")
    if args.input_root:
        args.input_dir = args.input_root
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
    elif args.mode == "entry-r3-smoke":
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
            capture_output=True, text=True,
        ).stdout.strip()
        input_dir = (
            args.input_dir
            or ROOT / f"outputs/entry_r3_smoke/runs_{commit[:12]}"
        )
        output_dir = (
            args.output_dir or ROOT / "outputs/aggregate/E1_balanced_entry_r3"
        )
    elif args.mode == "entry-r4-smoke":
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
            capture_output=True, text=True,
        ).stdout.strip()
        input_dir = (
            args.input_dir
            or ROOT / f"outputs/entry_r4_smoke/runs_{commit[:12]}"
        )
        output_dir = (
            args.output_dir or ROOT / "outputs/aggregate/E1_balanced_entry_r4"
        )
    else:
        input_dir = args.input_dir or ROOT / "outputs/runs"
        output_dir = args.output_dir or ROOT / "outputs/aggregate/E1_balanced"
    frame = aggregate(input_dir, output_dir, mode=args.mode)
    print(f"Aggregated {len(frame)} rows -> {output_dir / 'per_seed_metrics.parquet'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

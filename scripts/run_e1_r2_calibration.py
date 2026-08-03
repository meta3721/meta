#!/usr/bin/env python3
"""Run the pre-registered RAVEN candidates on R2 calibration traces."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from e1_r2_common import (  # noqa: E402
    CALIBRATION_SEEDS,
    R2_HORIZON,
    clip_metrics_from_run,
    load_candidate_registry,
    require_horizon,
    run_r2_method,
    trace_dir,
    validate_seed_role,
)
from raven_mcs.utils.serialization import load_json  # noqa: E402


def candidate_parameters(registry: dict, candidate: str) -> dict[str, float]:
    params = {
        key: float(value)
        for key, value in registry["frozen_parameters"].items()
    }
    params.update({
        key: float(value)
        for key, value in registry["candidates"][candidate].items()
    })
    return params


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--candidate-registry", type=Path,
        default=ROOT / "configs/e1_r2/candidate_registry.yaml",
    )
    parser.add_argument("--seeds", nargs="+", type=int, required=True)
    parser.add_argument("--windows", type=int, default=R2_HORIZON)
    parser.add_argument("--device", default="cpu")
    parser.add_argument(
        "--output-dir", type=Path, default=ROOT / "outputs/e1_r2/calibration",
    )
    args = parser.parse_args(argv)
    seeds = validate_seed_role("calibration", args.seeds)
    require_horizon(args.windows)
    registry = load_candidate_registry(args.candidate_registry)
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    for candidate in sorted(registry["candidates"]):
        params = candidate_parameters(registry, candidate)
        for seed in seeds:
            run = run_r2_method(
                ROOT,
                role="calibration",
                method="raven",
                seed=seed,
                custom_trace_dir=trace_dir(ROOT, "calibration", seed),
                output_root=output / "runs" / candidate,
                weight_safety=params,
                windows=args.windows,
                device=args.device,
            )
            metrics = load_json(run / "metrics_run.json")
            manifest = load_json(run / "manifest.json")
            trace_ref = load_json(run / "event_trace_ref.json")
            clip = clip_metrics_from_run(run)
            row = {
                "candidate": candidate,
                "seed": seed,
                "role": "calibration",
                "windows": args.windows,
                "a_max": params["a_max"],
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
                "event_trace_hash": manifest["event_trace_hash"],
                "trace_ref_hash": trace_ref["event_trace_hash"],
                "candidate_registry_hash": registry["candidate_registry_hash"],
                "run_dir": str(run.relative_to(ROOT)).replace("\\", "/"),
            }
            row.update({
                "clip_metrics_json": __import__("json").dumps(
                    clip, sort_keys=True, separators=(",", ":")
                )
            })
            rows.append(row)
    pd.DataFrame(rows).to_parquet(
        output / "candidate_seed_metrics.parquet", index=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

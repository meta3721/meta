#!/usr/bin/env python3
"""Deterministically replay representative clean calibration/validation runs."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd

from e1_r2_common import run_r2_method, trace_dir
from raven_mcs.utils.serialization import dump_json, load_json

ROOT = Path(__file__).resolve().parents[1]


def _clean(root: Path) -> bool:
    return subprocess.run(
        ["git", "status", "--porcelain"], cwd=root, check=True,
        capture_output=True, text=True,
    ).stdout.strip() == ""


def _compare(
    actual: float, expected: float, *, atol: float = 1e-8
) -> dict[str, Any]:
    delta = abs(float(actual) - float(expected))
    return {
        "actual": float(actual),
        "expected": float(expected),
        "absolute_delta": delta,
        "tolerance": atol,
        "within_tolerance": delta <= atol,
        "explanation": (
            "CLARABEL floating-point solve replay tolerance"
            if delta else "bitwise-equal scalar"
        ),
    }


def replay(root: Path, output: Path) -> dict[str, Any]:
    root, output = Path(root).resolve(), Path(output).resolve()
    if not _clean(root):
        raise RuntimeError("deterministic replay requires clean candidate HEAD")
    candidate = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    calibration = pd.read_parquet(
        root / "outputs/e1_r2/calibration/candidate_seed_metrics.parquet"
    )
    validation = pd.read_parquet(
        root / "outputs/e1_r2/validation/candidate_seed_metrics.parquet"
    )
    baseline = pd.read_parquet(
        root / "outputs/e1_r2/validation/baseline_selection.parquet"
    )
    cases = [
        ("calibration", "raven", 27001, calibration,
         {"candidate": "C2"}),
        ("validation", "raven", 27101, validation,
         {"candidate": "C2"}),
        ("validation", "flamf_timealign_adapted", 27101, baseline, {}),
    ]
    results = []
    for role, method, seed, source, filters in cases:
        selected = source.loc[source["seed"].astype(int) == seed]
        if "method" in source.columns:
            selected = selected.loc[source["method"].astype(str) == method]
        for key, value in filters.items():
            selected = selected.loc[selected[key].astype(str) == value]
        if len(selected) != 1:
            raise RuntimeError(f"source row mismatch for {role}/{method}/{seed}")
        run = run_r2_method(
            root,
            role=role,
            method=method,
            seed=seed,
            custom_trace_dir=trace_dir(root, role, seed),
            output_root=output / role / method,
            windows=100,
            device="cpu",
        )
        metrics = load_json(run / "metrics_run.json")
        source_row = selected.iloc[0]
        comparisons = {
            "RMSE_mu": _compare(metrics["RMSE_mu"], source_row["RMSE_mu"]),
            "Tail_RMSE": _compare(
                metrics["Tail_RMSE"], source_row["Tail_RMSE"]
            ),
        }
        if "c_clip_obs" in selected.columns:
            comparisons["c_clip_obs"] = _compare(
                metrics["c_clip_obs"], source_row["c_clip_obs"]
            )
        results.append({
            "role": role,
            "method": method,
            "seed": seed,
            "run_dir": run.relative_to(root).as_posix(),
            "comparisons": comparisons,
            "pass": all(
                item["within_tolerance"] for item in comparisons.values()
            ),
        })
    report = {
        "schema_version": 1,
        "status": "PASS" if all(item["pass"] for item in results) else "FAIL",
        "candidate_commit": candidate,
        "clean_execution": True,
        "scope": "representative deterministic replay",
        "cases": results,
        "formal_seed_read_count": 0,
        "formal_outcomes_accessed": False,
    }
    dump_json(report, output / "E1_R2_CALVAL_DETERMINISTIC_REPLAY.json")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "outputs/replay/e1_r2_calval_source_identity",
    )
    args = parser.parse_args()
    report = replay(args.root, args.output)
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

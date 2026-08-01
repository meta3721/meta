#!/usr/bin/env python3
"""Run the one-seed, five-method smoke through the official E1 entry."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import run_experiment


def write_entry_diagnostics(root: Path, run_root: Path) -> None:
    diagnostics = []
    runs = {}
    for manifest_path in sorted(run_root.rglob("manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        runs[manifest["method"]] = manifest_path.parent
    fedavg_window = pd.read_parquet(
        runs["fedavg_window"] / "metrics_window.parquet",
    )
    fedavg_predictions = pd.read_parquet(
        runs["fedavg_window"] / "predictions_test.parquet",
    )["y_pred"].to_numpy()
    for method, run_dir in sorted(runs.items()):
        window = pd.read_parquet(run_dir / "metrics_window.parquet")
        predictions = pd.read_parquet(
            run_dir / "predictions_test.parquet",
        )["y_pred"].to_numpy()
        diagnostics.append({
            "method": method,
            "alpha_diff_windows_vs_fedavg": int(
                (window["alpha"].to_numpy() != fedavg_window["alpha"].to_numpy()).sum()
            ),
            "prediction_l2_vs_fedavg": float(
                np.linalg.norm(predictions - fedavg_predictions),
            ),
            "staleness_path_active": bool((window["mean_staleness"] > 0).any()),
            "final_model_hash": json.loads(
                (run_dir / "manifest.json").read_text(encoding="utf-8"),
            )["model_hash"],
        })
    pd.DataFrame(diagnostics).to_parquet(
        root / "E1_ENTRY_METHOD_DIAGNOSTICS.parquet", index=False,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=26001)
    parser.add_argument("--windows", type=int, default=20)
    parser.add_argument("--local-steps", type=int, default=2)
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args(argv)
    if args.seed != 26001:
        raise ValueError("E1 entry smoke is frozen to seed 26001")
    root = ROOT / f"outputs/entry_smoke/E1_ENTRY_SMOKE_seed{args.seed}"
    run_root = root / "runs"
    root.mkdir(parents=True, exist_ok=True)
    code = run_experiment.main([
        "--experiment", "E1_balanced",
        "--seed", str(args.seed),
        "--num-windows", str(args.windows),
        "--local-steps", str(args.local_steps),
        "--device", args.device,
        "--output-dir", str(run_root),
        "--trace-cache", str(ROOT / "outputs/event_traces"),
        "--fail-fast",
    ])
    if code:
        return code
    write_entry_diagnostics(root, run_root)
    print(f"Official E1 entry smoke complete: {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

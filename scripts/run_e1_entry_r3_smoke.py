#!/usr/bin/env python3
"""Run the frozen one-seed five-method E1-R3 official-entry smoke."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import run_experiment


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=26001)
    parser.add_argument("--windows", type=int, default=20)
    parser.add_argument("--local-steps", type=int, default=2)
    parser.add_argument("--num-clients", type=int, default=8)
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()
    if args.seed != 26001 or args.num_clients != 8:
        raise ValueError("R3 smoke freezes seed=26001 and num_clients=8")
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    root = ROOT / "outputs/entry_r3_smoke"
    run_root = root / f"runs_{commit[:12]}"
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
    runs = {}
    for manifest_path in run_root.rglob("manifest.json"):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        runs[manifest["method"]] = manifest_path.parent
    expected = {
        "fedavg_window", "fedasync_window", "flamf_timealign_adapted",
        "twostage_hajek", "raven",
    }
    if set(runs) != expected:
        raise RuntimeError(f"R3 smoke method mismatch: {sorted(runs)}")
    for run in runs.values():
        opportunity = pd.read_parquet(
            run / "opportunity_ema_diagnostics.parquet",
        )
        if float(opportunity["formula_error"].max()) > 1e-12:
            raise RuntimeError("opportunity EMA formula gate failed")
        support = json.loads(
            (run / "support_crosscheck_ref.json").read_text(),
        )["summary"]
        if support["unsupported_positive_target_pairs"] != 0:
            raise RuntimeError("positive target support gate failed")
    fedasync = pd.read_parquet(
        runs["fedasync_window"] / "metrics_window.parquet",
    )
    timealign = pd.read_parquet(
        runs["flamf_timealign_adapted"] / "metrics_window.parquet",
    )
    alpha_l1 = []
    for left, right in zip(fedasync["alpha"], timealign["alpha"]):
        fa = np.asarray(json.loads(left), dtype=np.float64)
        ta = np.asarray(json.loads(right), dtype=np.float64)
        alpha_l1.append(
            float(np.abs(fa - ta).sum()) if len(fa) == len(ta) else np.nan,
        )
    comparison = {
        "max_l1_alpha_difference": float(np.nanmax(alpha_l1)),
        "protocol_config_hash": json.loads(
            (runs["fedasync_window"] / "manifest.json").read_text(),
        )["protocol_config_hash"],
    }
    (root / "timealign_fedasync_comparison.json").write_text(
        json.dumps(comparison, indent=2), encoding="utf-8",
    )
    print(f"Official E1-R3 entry smoke complete: {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

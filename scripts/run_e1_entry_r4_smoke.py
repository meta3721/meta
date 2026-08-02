#!/usr/bin/env python3
"""Run the frozen one-seed five-method E1-R4 official-entry smoke."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
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
        raise ValueError("R4 smoke freezes seed=26001 and num_clients=8")
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    root = ROOT / "outputs/entry_r4_smoke"
    run_root = root / f"runs_{commit[:12]}"
    code = run_experiment.main([
        "--experiment", "E1_balanced", "--seed", str(args.seed),
        "--num-windows", str(args.windows), "--local-steps", str(args.local_steps),
        "--device", args.device, "--output-dir", str(run_root),
        "--trace-cache", str(ROOT / "outputs/event_traces"), "--fail-fast",
    ])
    if code:
        return code
    runs = {}
    for path in run_root.rglob("manifest.json"):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        runs[manifest["method"]] = path.parent
    expected = {
        "fedavg_window", "fedasync_window", "flamf_timealign_adapted",
        "twostage_hajek", "raven",
    }
    if set(runs) != expected:
        raise RuntimeError(f"R4 smoke method mismatch: {sorted(runs)}")
    required = {
        "manifest.json", "resolved_config.yaml", "event_trace_ref.json",
        "metrics_window.parquet", "metrics_run.json", "predictions_test.parquet",
        "arrival_weights_test.parquet", "p_propensity_history.parquet",
        "q_propensity_history.parquet", "opportunity_ema_diagnostics.parquet",
        "arrival_support_diagnostics.parquet", "solver_diagnostics.parquet",
        "method_diagnostics.parquet", "system_metrics.json",
    }
    identity_fields = [
        "data_hash", "split_hash", "target_group_payload_hash",
        "target_group_file_hash", "client_mapping_payload_hash",
        "client_mapping_file_hash", "pi_target_hash", "event_trace_hash",
        "initial_model_hash", "protocol_config_hash",
    ]
    identities = []
    for run in runs.values():
        missing = [name for name in required if not (run / name).exists()]
        if missing:
            raise RuntimeError(f"missing R4 artifacts: {missing}")
        metrics = json.loads((run / "metrics_run.json").read_text())
        if metrics["q_nonattempt_leakage_count"] != 0:
            raise RuntimeError("q nonattempt leakage")
        if metrics["q_failed_attempt_omission_count"] != 0:
            raise RuntimeError("q failed-attempt omission")
        if metrics["unsupported_arrival_contribution_count"] != 0:
            raise RuntimeError("unsupported arrival contribution")
        if abs(metrics["Gap_mis"] - (metrics["RMSE_mu"] - metrics["RMSE_rho"])) > 1e-12:
            raise RuntimeError("Gap identity failed")
        manifest = json.loads((run / "manifest.json").read_text())
        identities.append(tuple(manifest.get(key) for key in identity_fields))
    if len(set(identities)) != 1:
        raise RuntimeError("R4 methods do not share frozen identities")
    print(f"Official E1-R4 entry smoke complete: {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

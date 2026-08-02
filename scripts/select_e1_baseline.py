#!/usr/bin/env python3
"""Select and freeze E1's strongest uncorrected baseline from validation only."""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from raven_mcs.experiments.e1_entry import git_commit, run_official_method
from raven_mcs.utils.hashing import sha256_file, sha256_path_tree
from raven_mcs.utils.serialization import dump_json, dump_yaml, load_json, load_yaml

CANDIDATES = ("fedavg_window", "fedasync_window", "timealign_agg")
PRIORITY = {method: index for index, method in enumerate(CANDIDATES)}


def choose_baseline(frame: pd.DataFrame, tolerance: float = 1e-6) -> str:
    if set(frame["method"]) != set(CANDIDATES):
        raise RuntimeError("validation baseline candidates are incomplete")
    if set(frame["split"]) != {"validation"}:
        raise RuntimeError("baseline selection may read validation only")
    ordered = frame.sort_values(["RMSE_mu", "method"])
    best_value = float(ordered.iloc[0]["RMSE_mu"])
    tied = [
        str(row.method) for row in ordered.itertuples()
        if abs(float(row.RMSE_mu) - best_value) < tolerance
    ]
    return min(tied, key=PRIORITY.__getitem__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", type=Path,
        default=ROOT / "configs/frozen/e1_sensorscope_balanced.yaml",
    )
    parser.add_argument("--validation-only", action="store_true")
    parser.add_argument("--seed", type=int, default=26001)
    parser.add_argument("--windows", type=int, default=20)
    parser.add_argument("--local-steps", type=int, default=2)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs/validation/e1_baseline_selection")
    args = parser.parse_args(argv)
    if not args.validation_only:
        raise ValueError("--validation-only is mandatory")
    timealign_spec = (
        ROOT / "docs/baselines/TIMEALIGN_BASELINE_SPEC.md"
    ).read_text(encoding="utf-8")
    if "BASELINE_UNRESOLVED" in timealign_spec:
        raise RuntimeError(
            "TimeAlign baseline is unresolved; baseline selection is blocked",
        )
    cfg = load_yaml(args.config)
    if cfg.get("dataset") != "sensorscope":
        raise RuntimeError("E1 validation config must be SensorScope")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for method in CANDIDATES:
        run_dir = run_official_method(
            ROOT, method=method, seed=args.seed, num_windows=args.windows,
            local_steps=args.local_steps, device="cpu",
            output_root=args.output_dir / "runs",
            evaluation_split="validation",
        )
        metrics = load_json(run_dir / "metrics_run.json")
        manifest = load_json(run_dir / "manifest.json")
        rows.append({
            "seed": args.seed,
            "method": method,
            "split": "validation",
            "RMSE_mu": metrics["RMSE_mu"],
            "run_id": manifest["run_id"],
            "event_trace_hash": manifest["event_trace_hash"],
            "data_hash": manifest["data_hash"],
            "git_commit": manifest["git_commit"],
        })
    frame = pd.DataFrame(rows)
    selected = choose_baseline(frame)
    frame.to_parquet(args.output_dir / "per_seed_validation.parquet", index=False)
    report = {
        "selected_baseline": selected,
        "candidate_methods": list(CANDIDATES),
        "validation_seed": args.seed,
        "validation_split_only": True,
        "validation_rmse_mu": {
            row["method"]: row["RMSE_mu"] for row in rows
        },
        "tie_break_rule": "within 1e-6: FedAvg, FedAsync, TimeAlign",
        "test_metrics_read": False,
        "status": "FROZEN_FROM_VALIDATION",
    }
    dump_json(report, args.output_dir / "selection_report.json")
    report_hash = sha256_file(args.output_dir / "selection_report.json")
    frozen = {
        **report,
        "validation_config_hash": sha256_file(args.config),
        "data_hash": rows[0]["data_hash"],
        "event_trace_hash": rows[0]["event_trace_hash"],
        "git_commit": git_commit(ROOT),
        "selection_timestamp": datetime.now(timezone.utc).isoformat(),
        "report_hash": report_hash,
    }
    dump_yaml(frozen, ROOT / "configs/frozen/e1_selected_baseline.yaml")
    print(f"selected_baseline={selected}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

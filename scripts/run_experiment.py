#!/usr/bin/env python3
"""Experiment runner — launches one (experiment, dataset, method, scenario, seed) tuple.

Usage:
    python scripts/run_experiment.py --experiment E1_balanced --seed 26001
    python scripts/run_experiment.py --experiment E1_balanced --dry-run
    python scripts/run_experiment.py --experiment E2_misalignment --seed 26001 --resume
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import numpy as np

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from raven_mcs.aggregation.methods import get_aggregator
from raven_mcs.simulation.event_trace import (
    EventTrace,
    freeze_event_trace,
    load_event_trace,
    synthesize_event_trace,
)
from raven_mcs.training.synthetic_gate_runner import SyntheticGateRunner, build_synthetic_runner
from raven_mcs.utils.config import resolve_run_config
from raven_mcs.utils.serialization import dump_json, load_yaml


def _get_or_generate_trace(
    dataset: str,
    scenario: str,
    seed: int,
    num_windows: int,
    trace_cache: Path,
) -> tuple[EventTrace, str]:
    """Load frozen trace or raise if missing for real datasets.

    Only dataset="synthetic" is allowed to generate a new EventTrace.
    All other datasets must have a pre-generated frozen trace.
    """
    trace_dir = trace_cache / f"{dataset}_{scenario}_seed{seed}"
    if trace_dir.exists():
        trace, identity = load_event_trace(trace_dir)
        return trace, identity["trace_hash"]

    if dataset == "synthetic":
        print(f"Generating synthetic EventTrace (seed={seed}, windows={num_windows})")
        trace = synthesize_event_trace(
            num_windows=num_windows,
            num_clients=min(10, num_windows // 10 + 1),
            seed=seed,
        )
        identity = freeze_event_trace(trace, trace_dir)
        return trace, identity["trace_hash"]

    # Real dataset — must have pre-generated EventTrace
    expected_path = trace_dir / "events.parquet"
    raise FileNotFoundError(
        f"EventTrace missing for real dataset.\n"
        f"  dataset: {dataset}\n"
        f"  scenario: {scenario}\n"
        f"  seed: {seed}\n"
        f"  expected path: {expected_path}\n"
        f"  Generate via: python scripts/generate_event_trace.py "
        f"--dataset {dataset} --scenario {scenario} --seed {seed}"
    )


def _run_experiment(
    experiment: str,
    dataset: str,
    method: str,
    scenario: str,
    seed: int,
    *,
    num_windows: int = 100,
    n_groups: int = 4,
    trace_cache: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Execute one experiment run and return summary metrics."""
    if trace_cache is None:
        trace_cache = Path("outputs/event_traces")

    print(f"Run: experiment={experiment} dataset={dataset} method={method} scenario={scenario} seed={seed}")

    trace, trace_hash = _get_or_generate_trace(dataset, scenario, seed, num_windows, trace_cache)

    if dry_run:
        return {
            "experiment": experiment,
            "dataset": dataset,
            "method": method,
            "scenario": scenario,
            "seed": seed,
            "trace_hash": trace_hash,
            "status": "dry_run",
        }

    # Build and run
    aggregator = get_aggregator(method)
    runner = SyntheticGateRunner(
        trace=trace,
        aggregator=aggregator,
        mu=np.full(n_groups, 1.0 / n_groups),
    )
    metrics = runner.run()

    # Collect summary
    active_windows = sum(1 for m in metrics if m.active)
    final_debt = float(np.linalg.norm(runner.debt, ord=1))
    omega_bar = runner.omega_bar()

    return {
        "experiment": experiment,
        "dataset": dataset,
        "method": method,
        "scenario": scenario,
        "seed": seed,
        "trace_hash": trace_hash,
        "num_windows": len(metrics),
        "active_windows": active_windows,
        "final_debt_l1": final_debt,
        "omega_bar": omega_bar.tolist(),
        "status": "completed",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="RAVEN-MCS experiment runner — one run per invocation."
    )
    parser.add_argument("--experiment", required=True, help="Experiment name (e.g. E1_balanced)")
    parser.add_argument("--dataset", default=None, help="Override dataset")
    parser.add_argument("--method", default=None, help="Override method")
    parser.add_argument("--scenario", default=None, help="Override scenario")
    parser.add_argument("--seed", type=int, default=None, help="Override seed")
    parser.add_argument("--num-windows", type=int, default=None, help="Override num_windows")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/runs"))
    parser.add_argument("--trace-cache", type=Path, default=Path("outputs/event_traces"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--fail-fast", action="store_true")
    args = parser.parse_args(argv)

    # Load experiment config
    exp_cfg = load_yaml(_ROOT / "configs" / "experiment" / f"{args.experiment}.yaml")
    datasets = exp_cfg.get("datasets", ["sensorscope"])
    methods = exp_cfg.get("methods", ["raven"])
    scenarios = exp_cfg.get("scenarios", ["balanced"])
    seeds = exp_cfg.get("seeds", [26001])
    num_windows = args.num_windows or exp_cfg.get("num_windows", 100)

    # Override from CLI
    if args.dataset:
        datasets = [args.dataset]
    if args.method:
        methods = [args.method]
    if args.scenario:
        scenarios = [args.scenario]
    if args.seed is not None:
        seeds = [args.seed]

    results = []
    failed = 0

    for dataset in datasets:
        for method in methods:
            for scenario in scenarios:
                for seed in seeds:
                    try:
                        result = _run_experiment(
                            experiment=args.experiment,
                            dataset=dataset,
                            method=method,
                            scenario=scenario,
                            seed=seed,
                            num_windows=num_windows,
                            trace_cache=args.trace_cache,
                            dry_run=args.dry_run,
                        )
                        results.append(result)
                        status = result.get("status", "unknown")
                        print(f"  {dataset}/{method}/{scenario}/seed={seed}: {status}")
                    except Exception as exc:
                        failed += 1
                        print(f"  {dataset}/{method}/{scenario}/seed={seed}: FAILED — {exc}")
                        if args.fail_fast:
                            raise

    # Save aggregate results
    args.output_dir.mkdir(parents=True, exist_ok=True)
    out = args.output_dir / f"{args.experiment}_summary.json"
    dump_json({"experiment": args.experiment, "results": results, "failed": failed}, out)
    print(f"\nSummary: {len(results)} runs, {failed} failed → {out}")

    return 1 if failed > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())

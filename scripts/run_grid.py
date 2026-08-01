#!/usr/bin/env python3
"""Hyper-parameter grid search runner for RAVEN-MCS.

Usage:
    python scripts/run_grid.py --experiment E1_balanced --param lambda_group --values 0.1,0.5,1.0,2.0
    python scripts/run_grid.py --experiment E4_ablation --grid configs/grids/ablation_grid.yaml
"""

from __future__ import annotations

import argparse
import itertools
import sys
from pathlib import Path
from typing import Any

import numpy as np

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from raven_mcs.aggregation.methods import get_aggregator
from raven_mcs.simulation.event_trace import synthesize_event_trace
from raven_mcs.training.synthetic_gate_runner import SyntheticGateRunner
from raven_mcs.utils.serialization import dump_json, load_yaml


def _run_single(
    method: str,
    seed: int,
    num_windows: int,
    n_groups: int,
    **kwargs: Any,
) -> dict[str, Any]:
    trace = synthesize_event_trace(num_windows=num_windows, num_clients=10, seed=seed)
    agg_cls = type(get_aggregator(method))

    params = {k: v for k, v in kwargs.items() if k in agg_cls.__init__.__code__.co_varnames}
    aggregator = agg_cls(**params)

    mu = np.full(n_groups, 1.0 / n_groups)
    runner = SyntheticGateRunner(trace=trace, aggregator=aggregator, mu=mu)
    metrics = runner.run()

    active_windows = sum(1 for m in metrics if m.active)
    final_debt = float(np.linalg.norm(runner.debt, ord=1))
    omega_bar = runner.omega_bar()
    delta_group = float(np.linalg.norm(omega_bar - mu, ord=1))

    return {
        "method": method,
        "seed": seed,
        "params": kwargs,
        "active_windows": active_windows,
        "final_debt_l1": final_debt,
        "delta_group": delta_group,
        "omega_bar": omega_bar.tolist(),
        "status": "completed",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RAVEN-MCS grid search runner.")
    parser.add_argument("--experiment", default="E4_ablation")
    parser.add_argument("--method", default="raven")
    parser.add_argument("--grid", type=Path, default=None, help="YAML grid definition")
    parser.add_argument("--param", nargs="*", default=[])
    parser.add_argument("--values", nargs="*", default=[])
    parser.add_argument("--seeds", type=int, nargs="*", default=[26001])
    parser.add_argument("--num-windows", type=int, default=100)
    parser.add_argument("--n-groups", type=int, default=4)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/grid"))
    args = parser.parse_args(argv)

    if args.grid:
        grid_cfg = load_yaml(args.grid)
        param_grid = grid_cfg.get("params", {})
    elif args.param and args.values:
        param_grid = {}
        for p, v in zip(args.param, args.values):
            param_grid[p] = [float(x) for x in v.split(",")]
    else:
        param_grid = {
            "lambda_group": [0.1, 0.5, 1.0, 2.0],
            "lambda_beta": [0.5, 1.0, 2.0],
        }

    keys = list(param_grid.keys())
    value_lists = [param_grid[k] for k in keys]

    results = []
    failed = 0
    total = len(list(itertools.product(*value_lists))) * len(args.seeds)

    for combo in itertools.product(*value_lists):
        params = dict(zip(keys, combo))
        for seed in args.seeds:
            try:
                result = _run_single(
                    method=args.method,
                    seed=seed,
                    num_windows=args.num_windows,
                    n_groups=args.n_groups,
                    **params,
                )
                results.append(result)
                print(f"  {params} seed={seed}: delta_group={result['delta_group']:.6f}")
            except Exception as exc:
                failed += 1
                print(f"  {params} seed={seed}: FAILED — {exc}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "experiment": args.experiment,
        "method": args.method,
        "param_grid": param_grid,
        "total_runs": total,
        "failed": failed,
        "results": results,
    }
    out = args.output_dir / f"{args.experiment}_grid.json"
    dump_json(summary, out)
    best = min(results, key=lambda r: r["delta_group"])
    print(f"\nGrid complete: {len(results)}/{total} runs, {failed} failed → {out}")
    print(f"Best: {best['params']} delta_group={best['delta_group']:.6f}")

    return 1 if failed > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())

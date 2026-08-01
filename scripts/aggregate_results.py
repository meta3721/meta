#!/usr/bin/env python3
"""Aggregate experiment results across seeds, methods, and datasets.

Usage:
    python scripts/aggregate_results.py --experiment E1_balanced
    python scripts/aggregate_results.py --input-dir outputs/runs --output outputs/aggregate/E1_summary.json
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from raven_mcs.utils.serialization import dump_json, load_json


def _collect_results(input_dir: Path, experiment: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    pattern = f"{experiment}_summary.json"
    for path in sorted(input_dir.rglob(pattern)):
        data = load_json(path)
        if isinstance(data.get("results"), list):
            results.extend(data["results"])
        elif isinstance(data, dict) and "status" in data:
            results.append(data)
    return results


def _aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    by_method: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in results:
        method = r.get("method", "unknown")
        by_method[method].append(r)

    summary: dict[str, Any] = {
        "total_runs": len(results),
        "methods": {},
    }

    for method, runs in by_method.items():
        debits = [r.get("final_debt_l1") for r in runs if r.get("final_debt_l1") is not None]
        active = [r.get("active_windows") for r in runs if r.get("active_windows") is not None]
        statuses = [r.get("status") for r in runs]

        summary["methods"][method] = {
            "num_runs": len(runs),
            "num_success": sum(1 for s in statuses if s == "completed"),
            "mean_debt_l1": float(np.mean(debits)) if debits else None,
            "std_debt_l1": float(np.std(debits)) if debits else None,
            "mean_active_windows": float(np.mean(active)) if active else None,
            "std_active_windows": float(np.std(active)) if active else None,
        }

    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Aggregate RAVEN-MCS experiment results.")
    parser.add_argument("--experiment", default=None, help="Experiment name filter")
    parser.add_argument("--input-dir", type=Path, default=Path("outputs/runs"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/aggregate"))
    args = parser.parse_args(argv)

    if not args.input_dir.exists():
        print(f"No results directory: {args.input_dir}")
        return 0

    experiment = args.experiment or "*"
    results = _collect_results(args.input_dir, experiment)
    if not results:
        print(f"No results found in {args.input_dir}")
        return 0

    summary = _aggregate(results)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    out = args.output_dir / f"{experiment}_aggregate.json"
    dump_json(summary, out)
    print(f"Aggregated {len(results)} runs across {len(summary['methods'])} methods → {out}")

    for method, stats in summary["methods"].items():
        print(f"  {method}: {stats['num_success']}/{stats['num_runs']} "
              f"debt={stats['mean_debt_l1']:.6f}±{stats['std_debt_l1']:.6f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

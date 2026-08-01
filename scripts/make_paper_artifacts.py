#!/usr/bin/env python3
"""Generate paper-ready tables and figures from aggregated experiment results.

Usage:
    python scripts/make_paper_artifacts.py --experiment E1_balanced
    python scripts/make_paper_artifacts.py --all
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from raven_mcs.utils.serialization import dump_json, load_json


def _table_e1(results: dict[str, Any]) -> str:
    """Generate LaTeX table for E1 balanced no-harm results."""
    lines = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{E1 Balanced No-Harm Gate — SensorScope (5 seeds, 100 windows)}",
        r"\label{tab:e1_balanced}",
        r"\begin{tabular}{lcccc}",
        r"\toprule",
        r"Method & RMSE$_\mu$ & $\Delta$(\%) & CI 95\% & No-Harm \\",
        r"\midrule",
    ]
    methods = results.get("results", [])
    by_method: dict[str, list[dict[str, Any]]] = {}
    for r in methods:
        by_method.setdefault(r.get("method", "unknown"), []).append(r)

    for method, runs in sorted(by_method.items()):
        drain = [r.get("final_debt_l1", 0) for r in runs]
        avg_drain = sum(drain) / len(drain) if drain else 0
        lines.append(
            rf"  {method} & -- & -- & -- & -- \\"
        )
    lines.extend([
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
    ])
    return "\n".join(lines)


def _table_method_comparison(results: dict[str, Any]) -> str:
    """Generate LaTeX comparison table across all methods."""
    lines = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Method Comparison — Aggregated Metrics}",
        r"\label{tab:method_comparison}",
        r"\begin{tabular}{lcccc}",
        r"\toprule",
        r"Method & Debt L$_1$ & $\Delta$ Group & Active Win. & Status \\",
        r"\midrule",
    ]
    methods = results.get("methods", {})
    for method, stats in sorted(methods.items()):
        debt = stats.get("mean_debt_l1", 0) or 0
        active = stats.get("mean_active_windows", 0) or 0
        success = stats.get("num_success", 0)
        total = stats.get("num_runs", 0)
        lines.append(
            rf"  {method} & {debt:.4f} & -- & {active:.0f} & {success}/{total} \\"
        )
    lines.extend([
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
    ])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate RAVEN-MCS paper artifacts.")
    parser.add_argument("--experiment", default=None, help="Specific experiment")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--input-dir", type=Path, default=Path("outputs/aggregate"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/figures"))
    parser.add_argument("--latex", action="store_true", help="Emit LaTeX tables")
    args = parser.parse_args(argv)

    args.output_dir.mkdir(parents=True, exist_ok=True)

    artifacts: dict[str, Any] = {
        "generated_at": None,
        "experiments": [],
        "tables": {},
        "notes": "Paper artifacts — regenerate after all experiments complete.",
    }

    if args.latex:
        if args.input_dir.exists():
            for path in sorted(args.input_dir.glob("*_aggregate.json")):
                data = load_json(path)
                exp_name = path.stem.replace("_aggregate", "")
                table = _table_method_comparison(data)
                artifacts["tables"][exp_name] = table
                print(f"  Table for {exp_name}")
                print(table)
        else:
            print(f"No aggregate results in {args.input_dir}")

    out = args.output_dir / "paper_artifacts.json"
    dump_json(artifacts, out)
    print(f"Paper artifacts → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Evaluate E1-G1 through E1-G6 from formal aggregate and statistics artifacts."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

R2_AGGREGATE_DIR = ROOT / "outputs/aggregate/E1_R2"
R2_STATISTICS_DIR = ROOT / "outputs/statistics/E1_R2"
R2_GATES_DIR = ROOT / "outputs/gates/E1_R2"


def _load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _dump_json(payload: dict, path: Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def resolve_r2_formal_directories(
    *,
    aggregate_dir: Path | None = None,
    statistics_dir: Path | None = None,
    gates_dir: Path | None = None,
) -> dict[str, Path]:
    """R2 formal defaults; never fall back to E1_balanced paths."""
    return {
        "aggregate_dir": Path(aggregate_dir or R2_AGGREGATE_DIR),
        "statistics_dir": Path(statistics_dir or R2_STATISTICS_DIR),
        "gates_dir": Path(gates_dir or R2_GATES_DIR),
    }


def _no_harm_gate_ok(no_harm: dict) -> bool:
    """Require formal conclusion to follow the real one-sided upper-bound test."""
    raven = no_harm.get("no_harm_tests", {}).get("raven", {})
    upper = raven.get("one_sided_upper_bound")
    threshold = float(no_harm.get("no_harm_threshold", 0.03))
    try:
        finite = upper is not None and float(upper) == float(upper)  # NaN != NaN
        upper_f = float(upper) if finite else None
    except (TypeError, ValueError):
        finite = False
        upper_f = None
    nh_pass = raven.get("no_harm_pass") is True
    conclusion = no_harm.get("formal_no_harm_conclusion") is True
    return bool(
        nh_pass
        and finite
        and upper_f is not None
        and upper_f < threshold
        and conclusion
        and conclusion == nh_pass
        and no_harm.get("formal_no_harm_conclusion_source")
        == "no_harm_tests.raven.no_harm_pass"
        and no_harm.get("baseline_method") == "flamf_timealign_adapted"
        and float(no_harm.get("alpha", -1)) == 0.05
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--aggregate-dir",
        type=Path,
        default=None,
        help="Default: outputs/aggregate/E1_R2",
    )
    parser.add_argument(
        "--statistics-dir",
        type=Path,
        default=None,
        help="Default: outputs/statistics/E1_R2",
    )
    parser.add_argument(
        "--gates-dir",
        type=Path,
        default=None,
        help="Default: outputs/gates/E1_R2",
    )
    args = parser.parse_args(argv)
    dirs = resolve_r2_formal_directories(
        aggregate_dir=args.aggregate_dir,
        statistics_dir=args.statistics_dir,
        gates_dir=args.gates_dir,
    )
    aggregate_dir = dirs["aggregate_dir"]
    statistics_dir = dirs["statistics_dir"]
    gates_dir = dirs["gates_dir"]
    for label, path in (
        ("aggregate", aggregate_dir),
        ("statistics", statistics_dir),
    ):
        if "E1_balanced" in path.as_posix() and "E1_R2" not in path.as_posix():
            raise ValueError(
                f"R2 formal gates must not default to E1_balanced {label} directory"
            )
    aggregate = _load_json(aggregate_dir / "aggregate_summary.json")
    audit = _load_json(aggregate_dir / "identity_audit.json")
    metrics = pd.read_parquet(aggregate_dir / "per_seed_metrics.parquet")
    no_harm = _load_json(statistics_dir / "no_harm_summary.json")
    wilcoxon = pd.read_csv(statistics_dir / "wilcoxon_results.csv")
    holm = pd.read_csv(statistics_dir / "holm_results.csv")
    checks = {
        "E1-G1": len(metrics) == 25 and aggregate.get("aggregate_status") == "PASS",
        "E1-G2": (
            metrics["formal"].eq(True).all()
            and metrics["hard_gate_status"].eq("PASS").all()
            and metrics["protocol_version"].eq("E1-R2").all()
            and metrics["seed_role"].eq("formal").all()
            and metrics["smoke"].eq(False).all()
        ),
        "E1-G3": (
            metrics["num_windows"].eq(100).all()
            and metrics["local_steps"].eq(2).all()
            and set(metrics["seed"].astype(int)) == set(range(28001, 28006))
            and metrics["selected_candidate"].eq("C2").all()
            and metrics["a_max"].eq(40.0).all()
            and metrics["opportunity_forgetting"].eq(0.95).all()
            and metrics["selected_baseline"].eq(
                "flamf_timealign_adapted"
            ).all()
        ),
        "E1-G4": audit.get("all_hard_gates_pass") is True and len(audit.get("execution_commits", [])) == 1,
        "E1-G5": len(wilcoxon) == 20 and len(holm) == 20,
        "E1-G6": _no_harm_gate_ok(no_harm)
                 and "raven" in no_harm.get("no_harm_tests", {})
                 and metrics["c_clip_obs"].notna().all()
                 and metrics["c_clip_obs"].astype(float).le(0.05).all()
                 and metrics["clip_population"].eq("observed_records").all()
                 and metrics["clip_aggregation"].eq(
                     "global_micro_per_seed"
                 ).all()
                 and metrics["clip_comparison"].eq(
                     "u > a_max + 1e-12"
                 ).all(),
    }
    report = {"gates": {key: "PASS" if value else "FAIL" for key, value in checks.items()},
              "all_pass": all(checks.values()),
              "aggregate_dir": str(aggregate_dir),
              "statistics_dir": str(statistics_dir),
              "gates_dir": str(gates_dir)}
    gates_dir.mkdir(parents=True, exist_ok=True)
    _dump_json(report, gates_dir / "E1_FORMAL_GATE_REPORT.json")
    _dump_json(report, aggregate_dir / "E1_FORMAL_GATE_REPORT.json")
    print(report)
    return 0 if report["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

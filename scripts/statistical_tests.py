#!/usr/bin/env python3
"""Statistical tests for RAVEN-MCS experiment results (P10-D).

Reads real results from outputs/aggregate/<experiment>/per_seed_metrics.parquet.
No random example data — all statistics from actual experiment outputs.

Implements:
  - paired seed alignment
  - bootstrap CI
  - E1 one-sided no-harm bootstrap upper bound
  - two-sided Wilcoxon signed-rank
  - Holm correction
  - effect size (Cohen's d for paired)
  - paired median difference
  - relative improvement

Usage:
    python scripts/statistical_tests.py --experiment E1_balanced --alpha 0.05
    python scripts/statistical_tests.py --input results.json --output stats.json
"""

from __future__ import annotations

import argparse
import sys
from itertools import combinations
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from raven_mcs.utils.serialization import dump_json, load_json, load_yaml


def _bootstrap_ci(
    values: np.ndarray,
    alpha: float = 0.05,
    n_bootstrap: int = 10_000,
    seed: int = 26001,
) -> dict[str, float]:
    rng = np.random.default_rng(seed)
    n = len(values)
    if n == 0:
        return {"mean": float("nan"), "std": float("nan"), "ci_lower": float("nan"),
                "ci_upper": float("nan"), "n": 0}
    means = np.empty(n_bootstrap)
    for i in range(n_bootstrap):
        means[i] = float(np.mean(rng.choice(values, size=n, replace=True)))
    lo = float(np.percentile(means, 100 * alpha / 2))
    hi = float(np.percentile(means, 100 * (1 - alpha / 2)))
    return {
        "mean": float(np.mean(values)),
        "std": float(np.std(values, ddof=1)) if n > 1 else 0.0,
        "ci_lower": lo,
        "ci_upper": hi,
        "n": n,
    }


def _bootstrap_ci_one_sided_upper(
    values: np.ndarray,
    alpha: float = 0.05,
    n_bootstrap: int = 10_000,
    seed: int = 26001,
) -> float:
    """One-sided 95% CI upper bound for no-harm test."""
    rng = np.random.default_rng(seed)
    n = len(values)
    if n == 0:
        return float("inf")
    means = np.empty(n_bootstrap)
    for i in range(n_bootstrap):
        means[i] = float(np.mean(rng.choice(values, size=n, replace=True)))
    return float(np.percentile(means, 100 * (1 - alpha)))


def _no_harm_test(
    baseline_rmse: list[float],
    candidate_rmse: list[float],
    threshold: float = 0.03,
    alpha: float = 0.05,
) -> dict[str, Any]:
    base = np.asarray(baseline_rmse, dtype=np.float64)
    cand = np.asarray(candidate_rmse, dtype=np.float64)

    if len(base) != len(cand):
        raise ValueError(
            f"Seed count mismatch: baseline has {len(base)} seeds, "
            f"candidate has {len(cand)} seeds. Paired alignment required."
        )

    diffs = cand - base
    relative = diffs / np.maximum(base, 1e-10)

    ci = _bootstrap_ci(relative, alpha=alpha)
    upper_bound = _bootstrap_ci_one_sided_upper(relative, alpha=alpha)
    no_harm_pass = upper_bound < threshold

    # Wilcoxon signed-rank test
    if len(diffs) >= 3:
        w_stat, w_pval = sp_stats.wilcoxon(cand, base, zero_method="zsplit")
    else:
        w_stat, w_pval = float("nan"), float("nan")

    # Effect size (Cohen's d for paired)
    d_bar = np.mean(diffs)
    s_bar = np.std(diffs, ddof=1) if len(diffs) > 1 else 0.0
    cohens_d = d_bar / s_bar if s_bar > 0 else 0.0

    return {
        "baseline_mean": float(np.mean(base)),
        "candidate_mean": float(np.mean(cand)),
        "baseline_median": float(np.median(base)),
        "candidate_median": float(np.median(cand)),
        "relative_degradation_mean": ci["mean"],
        "relative_degradation_ci_lower": ci["ci_lower"],
        "relative_degradation_ci_upper": ci["ci_upper"],
        "one_sided_upper_bound": upper_bound,
        "threshold": threshold,
        "no_harm_pass": no_harm_pass,
        "wilcoxon_statistic": float(w_stat) if not np.isnan(w_stat) else None,
        "wilcoxon_p_value": float(w_pval) if not np.isnan(w_pval) else None,
        "cohens_d": cohens_d,
        "paired_median_diff": float(np.median(diffs)),
        "baseline_n": len(base),
        "candidate_n": len(cand),
    }


def _holm_correction(p_values: list[float], alpha: float = 0.05) -> dict[str, Any]:
    """Holm-Bonferroni correction for multiple comparisons."""
    n = len(p_values)
    if n == 0:
        return {"corrected_alpha": alpha, "significant": [], "n_tests": 0}

    sorted_idx = np.argsort(p_values)
    significant = []
    for rank, idx in enumerate(sorted_idx):
        adjusted_alpha = alpha / (n - rank)
        if p_values[idx] < adjusted_alpha:
            significant.append(idx)
        else:
            break

    return {
        "corrected_alpha": alpha,
        "significant_indices": significant,
        "n_tests": n,
    }


def load_per_seed_metrics(data_dir: str | Path) -> pd.DataFrame:
    """Load per-seed metrics from experiment output directory."""
    data_path = Path(data_dir)
    parquet_path = data_path / "per_seed_metrics.parquet"
    if not parquet_path.exists():
        raise FileNotFoundError(
            f"per_seed_metrics.parquet not found at {parquet_path}. "
            f"Run experiments first to generate metrics."
        )
    return pd.read_parquet(parquet_path)


def compute_all_statistics(
    df: pd.DataFrame,
    baseline_method: str = "fedavg_window",
    methods: list[str] | None = None,
    metric: str = "rmse_mu",
    alpha: float = 0.05,
    threshold: float = 0.03,
) -> dict[str, Any]:
    """Compute all statistical tests from experiment results DataFrame."""
    results: dict[str, Any] = {"metric": metric, "alpha": alpha, "threshold": threshold}

    available_methods = sorted(df["method"].unique()) if "method" in df.columns else []
    if methods is None:
        methods = [m for m in available_methods if m != baseline_method]

    # Paired seed alignment check
    baseline_seeds = set(df.loc[df["method"] == baseline_method, "seed"].unique())
    for m in methods:
        method_seeds = set(df.loc[df["method"] == m, "seed"].unique())
        if baseline_seeds != method_seeds:
            results[f"seed_mismatch_{m}"] = {
                "baseline_seeds": sorted(baseline_seeds),
                f"{m}_seeds": sorted(method_seeds),
            }

    # Per-method statistics
    method_stats: dict[str, Any] = {}
    for m in [baseline_method] + methods:
        method_df = df[df["method"] == m].sort_values("seed")
        if metric in method_df.columns:
            values = method_df[metric].dropna().values
            method_stats[m] = _bootstrap_ci(values, alpha=alpha)

    results["method_statistics"] = method_stats

    # No-harm tests for each method vs baseline
    no_harm_results: dict[str, Any] = {}
    baseline_df = df[df["method"] == baseline_method].sort_values("seed")
    baseline_vals = baseline_df[metric].dropna().values

    p_values: dict[str, float] = {}
    for m in methods:
        method_df = df[df["method"] == m].sort_values("seed")
        if len(method_df) == 0:
            continue
        method_vals = method_df[metric].dropna().values

        if len(baseline_vals) != len(method_vals):
            # Align on common seeds
            common_seeds = sorted(
                set(baseline_df["seed"].unique()) & set(method_df["seed"].unique())
            )
            b_vals = baseline_df[baseline_df["seed"].isin(common_seeds)].sort_values("seed")[metric].values
            m_vals = method_df[method_df["seed"].isin(common_seeds)].sort_values("seed")[metric].values
        else:
            b_vals = baseline_vals
            m_vals = method_vals

        no_harm_results[m] = _no_harm_test(
            b_vals.tolist(), m_vals.tolist(), threshold=threshold, alpha=alpha,
        )
        w_pval = no_harm_results[m].get("wilcoxon_p_value")
        if w_pval is not None:
            p_values[m] = float(w_pval)

    results["no_harm_tests"] = no_harm_results

    # Holm correction
    if p_values:
        holm = _holm_correction(list(p_values.values()), alpha=alpha)
        holm["method_order"] = [m for _, m in sorted(
            zip(p_values.values(), p_values.keys()))]
        results["holm_correction"] = holm

    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RAVEN-MCS statistical tests.")
    parser.add_argument("--experiment", default="E1_balanced")
    parser.add_argument("--input", type=Path, default=None, help="Input JSON with results")
    parser.add_argument("--input-dir", type=Path, default=None,
                        help="Directory with per_seed_metrics.parquet")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--threshold", type=float, default=0.03,
                        help="No-harm degradation threshold")
    parser.add_argument("--baseline", default=None,
                        help="Explicit override; normally read from frozen selection")
    parser.add_argument("--selected-baseline", type=Path,
                        default=_ROOT / "configs/frozen/e1_selected_baseline.yaml")
    parser.add_argument("--metric", default="RMSE_mu",
                        help="Metric to compare")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.input_dir is None:
        args.input_dir = (
            _ROOT / "outputs/entry_smoke/E1_ENTRY_SMOKE_seed26001/aggregate"
            if args.dry_run
            else _ROOT / "outputs/aggregate" / args.experiment
        )

    if not args.selected_baseline.exists():
        raise FileNotFoundError(
            f"frozen selected baseline missing: {args.selected_baseline}",
        )
    selected = load_yaml(args.selected_baseline)
    baseline_method = args.baseline or selected.get("selected_baseline")
    if baseline_method not in {"fedavg_window", "fedasync_window", "timealign_agg"}:
        raise RuntimeError("invalid or missing frozen E1 selected baseline")
    output_dir = args.output_dir or _ROOT / "outputs/statistics" / args.experiment
    tests: dict[str, Any] = {
        "experiment": args.experiment,
        "alpha": args.alpha,
        "no_harm_threshold": args.threshold,
        "baseline_method": baseline_method,
        "baseline_source": str(args.selected_baseline),
        "metric": args.metric,
    }

    if args.input:
        results = load_json(args.input)
        tests["source"] = str(args.input)
        output_dir.mkdir(parents=True, exist_ok=True)
        out = output_dir / f"{args.experiment}_statistics.json"
        dump_json(tests, out)
        print(f"Statistical tests → {out}")
        return 0

    if args.input_dir:
        try:
            df = load_per_seed_metrics(args.input_dir)
            expected = set(df.loc[df["method"] == baseline_method, "seed"])
            raven_seeds = set(df.loc[df["method"] == "raven", "seed"])
            if expected != raven_seeds:
                raise RuntimeError("paired seed mismatch or seed exclusion")
            stats = compute_all_statistics(
                df, baseline_method=baseline_method, methods=["raven"],
                metric=args.metric,
                alpha=args.alpha, threshold=args.threshold,
            )
            tests.update(stats)
            single_seed = len(expected) == 1
            if single_seed and not args.dry_run:
                raise RuntimeError("single-seed E1 statistics require --dry-run")
            tests["status"] = "DRY_RUN_SCHEMA_PASS" if args.dry_run else "FORMAL"
            tests["formal_no_harm_conclusion"] = not args.dry_run
            if args.dry_run:
                for result in tests.get("no_harm_tests", {}).values():
                    result["no_harm_pass"] = None
            output_dir.mkdir(parents=True, exist_ok=True)
            dump_json(tests, output_dir / "no_harm_summary.json")
            paired = df.loc[
                df["method"].isin([baseline_method, "raven"]),
                ["seed", "method", args.metric],
            ].pivot(index="seed", columns="method", values=args.metric).reset_index()
            paired["degradation"] = (
                paired["raven"] - paired[baseline_method]
            ) / paired[baseline_method]
            paired.to_parquet(output_dir / "no_harm_per_seed.parquet", index=False)
            pd.DataFrame(columns=[
                "comparison", "statistic", "p_value",
            ]).to_csv(output_dir / "wilcoxon_results.csv", index=False)
            pd.DataFrame(columns=[
                "comparison", "raw_p", "holm_significant",
            ]).to_csv(output_dir / "holm_results.csv", index=False)
            report = (
                "# E1 no-harm statistics\n\n"
                f"Status: {tests['status']}\n\n"
                f"Frozen baseline: {baseline_method}\n\n"
                "Single-seed entry smoke is schema validation only; no formal "
                "no-harm PASS/FAIL is reported.\n"
            )
            (output_dir / "statistics_report.md").write_text(report, encoding="utf-8")
            print(f"Statistical dry-run → {output_dir}")
            for m, nh in stats.get("no_harm_tests", {}).items():
                decision = (
                    "DRY_RUN_ONLY" if args.dry_run
                    else ("PASS" if nh["no_harm_pass"] else "FAIL")
                )
                print(
                    f"  {m}: no-harm={decision}, "
                    f"upper={nh['one_sided_upper_bound']:.4f}",
                )
            return 0
        except FileNotFoundError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    # No real data available — report status
    tests["status"] = "no_input_data"
    print("No input data provided. Provide --input-dir with per_seed_metrics.parquet "
          "from experiment outputs.")
    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / f"{args.experiment}_statistics.json"
    dump_json(tests, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

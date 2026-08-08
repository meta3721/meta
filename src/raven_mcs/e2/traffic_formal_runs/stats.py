"""Frozen, transparent formal statistics for E2 traffic."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy import stats


def summarize_vector(values: np.ndarray) -> dict[str, float]:
    arr = np.asarray(values, dtype=np.float64)
    arr = arr[np.isfinite(arr)]
    n = int(arr.size)
    if n == 0:
        return {
            "n": 0, "mean": float("nan"), "std": float("nan"),
            "median": float("nan"), "iqr": float("nan"),
            "ci95_low": float("nan"), "ci95_high": float("nan"),
        }
    mean = float(np.mean(arr))
    std = float(np.std(arr, ddof=1)) if n > 1 else 0.0
    median = float(np.median(arr))
    q1, q3 = np.percentile(arr, [25, 75])
    # Normal approx CI for mean (fixed a priori; documented in report).
    if n > 1:
        se = std / np.sqrt(n)
        z = 1.959963984540054
        lo, hi = mean - z * se, mean + z * se
    else:
        lo = hi = mean
    return {
        "n": n,
        "mean": mean,
        "std": std,
        "median": median,
        "iqr": float(q3 - q1),
        "ci95_low": float(lo),
        "ci95_high": float(hi),
    }


def paired_raven_vs_baseline(
    frame: pd.DataFrame,
    *,
    metric: str,
    raven_method: str = "raven",
    baseline_method: str,
    scenario: str,
) -> dict[str, Any]:
    """Paired seed differences: RAVEN - baseline (smaller error is better)."""
    sub = frame.loc[frame["scenario"] == scenario]
    r = sub.loc[sub["method"] == raven_method].set_index("seed")[metric]
    b = sub.loc[sub["method"] == baseline_method].set_index("seed")[metric]
    seeds = sorted(set(r.index) & set(b.index))
    diff = np.asarray([float(r.loc[s] - b.loc[s]) for s in seeds], dtype=np.float64)
    summary = summarize_vector(diff)
    # Win = RAVEN lower error; tie within 1e-12; loss otherwise.
    wins = int(np.sum(diff < -1e-12))
    losses = int(np.sum(diff > 1e-12))
    ties = int(len(diff) - wins - losses)
    # Two-sided Wilcoxon signed-rank; zeros handled by scipy (omit zeros).
    p_value = float("nan")
    test_name = "wilcoxon_signed_rank_two_sided"
    zero_policy = "scipy_default_omit_zeros"
    if len(diff) >= 1 and np.any(diff != 0):
        try:
            res = stats.wilcoxon(diff, alternative="two-sided", zero_method="wilcox")
            p_value = float(res.pvalue)
        except ValueError:
            p_value = float("nan")
    return {
        "scenario": scenario,
        "metric": metric,
        "raven_method": raven_method,
        "baseline_method": baseline_method,
        "n_pairs": int(len(seeds)),
        "mean_paired_diff": summary["mean"],
        "median_paired_diff": summary["median"],
        "ci95_low": summary["ci95_low"],
        "ci95_high": summary["ci95_high"],
        "wins": wins,
        "ties": ties,
        "losses": losses,
        "test": test_name,
        "zero_difference_policy": zero_policy,
        "multiple_comparison_policy": "none_familywise_raw_p_reported",
        "p_value": p_value,
    }

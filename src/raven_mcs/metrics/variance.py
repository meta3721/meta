"""Variance and stability diagnostics (paper F7.9–F7.10)."""

from __future__ import annotations

import numpy as np
from scipy.stats import spearmanr


def local_n_eff(a: np.ndarray) -> float:
    """Effective sample size from Hájek weights: 1 / Σ ā²."""
    a_arr = np.asarray(a, dtype=np.float64)
    total = float(a_arr.sum())
    if total <= 0:
        return 0.0
    a_bar = a_arr / total
    denom = float(np.sum(a_bar**2))
    if denom <= 0:
        return float("inf")
    return float(1.0 / denom)


def max_local_weight(a: np.ndarray) -> float:
    """Maximum normalised local weight ā."""
    a_arr = np.asarray(a, dtype=np.float64)
    total = float(a_arr.sum())
    if total <= 0:
        return 0.0
    return float((a_arr / total).max())


def variance_proxy(alpha: np.ndarray, v_diag: np.ndarray) -> float:
    """Aggregate variance proxy: α^T V α."""
    a = np.asarray(alpha, dtype=np.float64)
    v = np.asarray(v_diag, dtype=np.float64)
    return float(np.dot(a, v * a))


def empirical_update_variance(
    update_norms: np.ndarray,
) -> float:
    """Empirical variance of update L2 norms across a window."""
    u = np.asarray(update_norms, dtype=np.float64)
    if len(u) < 2:
        return 0.0
    return float(np.var(u, ddof=1))


def proxy_rank_correlation(
    proxy_values: np.ndarray,
    empirical_variances: np.ndarray,
) -> float:
    """Spearman rank correlation between variance proxy and empirical variance."""
    if len(proxy_values) < 3:
        return float("nan")
    corr, _ = spearmanr(
        np.asarray(proxy_values, dtype=np.float64),
        np.asarray(empirical_variances, dtype=np.float64),
    )
    return float(corr) if not np.isnan(corr) else float("nan")


def weight_clip_rate(
    a_raw: np.ndarray,
    a_max: float,
) -> float:
    """Fraction of weights that hit the clipping ceiling."""
    a = np.asarray(a_raw, dtype=np.float64)
    if len(a) == 0:
        return 0.0
    return float(np.mean(a >= a_max - 1e-12))

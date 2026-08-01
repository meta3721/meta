"""Simple IPW / Horvitz–Thompson helpers for E0.2 Monte Carlo checks."""

from __future__ import annotations

import numpy as np


def horvitz_thompson_mean(
    values: np.ndarray,
    observed: np.ndarray,
    propensity: np.ndarray | float,
) -> float:
    """
    HT estimator of E[Y]: (1/n) Σ O_i Y_i / p_i.

    Used only for synthetic Monte Carlo truth checks in E0.2.
    """
    y = np.asarray(values, dtype=np.float64)
    o = np.asarray(observed, dtype=np.float64)
    if np.isscalar(propensity):
        p = np.full_like(y, float(propensity), dtype=np.float64)
    else:
        p = np.asarray(propensity, dtype=np.float64)
    if y.shape != o.shape or y.shape != p.shape:
        raise ValueError("values/observed/propensity shapes must match")
    if np.any(p <= 0):
        raise ValueError("propensity must be positive")
    return float(np.mean((o * y) / p))

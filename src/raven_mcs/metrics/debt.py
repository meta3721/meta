"""Debt diagnostics (paper F7.7–F7.8)."""

from __future__ import annotations

import numpy as np


def debt_normalized(debt: np.ndarray, scale: float) -> float:
    """‖Q‖_1 / S_R."""
    if scale <= 0:
        raise ValueError("scale S_R must be positive")
    return float(np.linalg.norm(np.asarray(debt, dtype=np.float64), ord=1) / scale)


def prefix_debt_bound_holds(
    omega_bar: np.ndarray,
    mu: np.ndarray,
    debt: np.ndarray,
    scale: float,
    *,
    tol: float = 1e-8,
) -> bool:
    """
    Deterministic prefix bound:

    ‖ω̄_R − μ‖_1 ≤ 2 ‖Q_R‖_1 / S_R
    """
    if scale <= 0:
        raise ValueError("scale S_R must be positive")
    left = float(
        np.linalg.norm(
            np.asarray(omega_bar, dtype=np.float64) - np.asarray(mu, dtype=np.float64),
            ord=1,
        )
    )
    right = 2.0 * float(np.linalg.norm(np.asarray(debt, dtype=np.float64), ord=1)) / float(
        scale
    )
    return left <= right + float(tol)

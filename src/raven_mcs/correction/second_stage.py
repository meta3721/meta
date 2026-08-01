"""Stage-2 usable correction d, b, β̂ (paper F5.2–F5.4)."""

from __future__ import annotations

import numpy as np


def d_weight(
    q_hat_use: np.ndarray,
    *,
    d_max: float = 10.0,
    q_min: float = 0.05,
) -> np.ndarray:
    """d = min{d_max, 1 / max(q̂, q_min)}."""
    if d_max <= 0:
        raise ValueError("d_max must be positive")
    if q_min <= 0:
        raise ValueError("q_min must be positive")
    q_hat = np.asarray(q_hat_use, dtype=np.float64)
    if np.any(q_hat < 0):
        raise ValueError("q_hat_use must be nonnegative")
    return np.minimum(float(d_max), 1.0 / np.maximum(q_hat, float(q_min)))


def two_stage_mass(total_masses: np.ndarray, d_weights: np.ndarray) -> np.ndarray:
    """b = m · d."""
    m = np.asarray(total_masses, dtype=np.float64)
    d = np.asarray(d_weights, dtype=np.float64)
    if m.shape != d.shape:
        raise ValueError("total_masses and d_weights must share shape")
    return m * d


def beta_hat(two_stage_masses: np.ndarray) -> np.ndarray:
    """β̂ = b / Σ_{j∈A} b_j with β≥0 and Σβ=1."""
    b = np.asarray(two_stage_masses, dtype=np.float64)
    if np.any(b < 0):
        raise ValueError("two-stage masses must be nonnegative")
    total = float(b.sum())
    if total <= 0.0:
        raise ValueError("active set two-stage mass sum must be positive")
    beta = b / total
    if np.any(beta < -1e-15):
        raise ValueError("beta_hat must be nonnegative")
    if abs(float(beta.sum()) - 1.0) > 1e-12:
        raise ValueError("beta_hat must sum to 1")
    return beta

"""Target-debt dynamics (paper F6.3)."""

from __future__ import annotations

import numpy as np


def update_debt(
    debt: np.ndarray,
    *,
    mu: np.ndarray,
    omega: np.ndarray,
    eta: float,
    active: bool = True,
) -> np.ndarray:
    """
    Q_{r+1} = [Q_r + η_r (μ − ω_r)]_+.

    Empty/inactive windows leave Q unchanged.
    """
    q = np.asarray(debt, dtype=np.float64).copy()
    if not active:
        return q
    if eta < 0:
        raise ValueError("eta must be nonnegative")
    target = np.asarray(mu, dtype=np.float64)
    mix = np.asarray(omega, dtype=np.float64)
    if q.shape != target.shape or q.shape != mix.shape:
        raise ValueError("debt, mu, and omega must share shape")
    updated = q + float(eta) * (target - mix)
    return np.maximum(updated, 0.0)


def coverage_mix(coverage_matrix: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    """ω = M α where columns of M are per-client compositions."""
    m = np.asarray(coverage_matrix, dtype=np.float64)
    a = np.asarray(alpha, dtype=np.float64)
    if m.ndim != 2:
        raise ValueError("coverage_matrix must be 2-D (groups × clients)")
    if a.ndim != 1 or a.shape[0] != m.shape[1]:
        raise ValueError("alpha length must equal number of active clients")
    return m @ a

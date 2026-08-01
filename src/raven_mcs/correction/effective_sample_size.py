"""Effective sample size n_eff (paper F3.9). Never interchange with mass m."""

from __future__ import annotations

import numpy as np


def effective_sample_size(
    observation: np.ndarray,
    raw_a: np.ndarray,
    *,
    total_mass: float | None = None,
    normalized: np.ndarray | None = None,
) -> float:
    """
    n_eff = m² / Σ (O a)² = 1 / Σ ā².

    Both identities are evaluated; they must agree within tolerance.
    """
    o = np.asarray(observation, dtype=np.float64)
    a = np.asarray(raw_a, dtype=np.float64)
    if o.shape != a.shape:
        raise ValueError("observation and raw_a must share shape")
    weighted = o * a
    mass = float(weighted.sum()) if total_mass is None else float(total_mass)
    denom = float(np.square(weighted).sum())
    if denom <= 0.0:
        n_from_raw = 0.0
    else:
        n_from_raw = (mass * mass) / denom

    if normalized is None:
        if mass == 0.0:
            n_from_bar = 0.0
        else:
            a_bar = weighted / mass
            n_from_bar = 1.0 / float(np.square(a_bar).sum())
    else:
        a_bar = np.asarray(normalized, dtype=np.float64)
        ssq = float(np.square(a_bar).sum())
        n_from_bar = 0.0 if ssq <= 0.0 else 1.0 / ssq

    if abs(n_from_raw - n_from_bar) > 1e-9:
        raise ValueError(
            f"ESS identities disagree: m^2/sum(Oa)^2={n_from_raw}, "
            f"1/sum(a_bar)^2={n_from_bar}"
        )
    return float(n_from_raw)

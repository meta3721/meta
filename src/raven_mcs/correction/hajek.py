"""Stage-1 Hájek weights a, m, ā, c (paper F3.4–F3.8)."""

from __future__ import annotations

import numpy as np


def raw_weights(
    zeta_hat: np.ndarray,
    p_hat_obs: np.ndarray,
    *,
    a_max: float = 20.0,
    p_min: float = 0.05,
) -> np.ndarray:
    """
    a = min{a_max, ζ̂ / max(p̂_obs, p_min)}.

    Corresponds to paper F3.4.
    """
    if a_max <= 0:
        raise ValueError("a_max must be positive")
    if p_min <= 0:
        raise ValueError("p_min must be positive")
    zeta = np.asarray(zeta_hat, dtype=np.float64)
    p_hat = np.asarray(p_hat_obs, dtype=np.float64)
    if zeta.shape != p_hat.shape:
        raise ValueError("zeta_hat and p_hat_obs must share shape")
    if np.any(zeta < 0) or np.any(p_hat < 0):
        raise ValueError("zeta_hat and p_hat_obs must be nonnegative")
    return np.minimum(float(a_max), zeta / np.maximum(p_hat, float(p_min)))


def group_mass(
    observation: np.ndarray,
    raw_a: np.ndarray,
    group_ids: np.ndarray,
    *,
    n_groups: int | None = None,
) -> np.ndarray:
    """m_{k,r,g} = Σ_i O a 1{h(i)=g}."""
    o = np.asarray(observation, dtype=np.float64)
    a = np.asarray(raw_a, dtype=np.float64)
    g = np.asarray(group_ids)
    if not (o.shape == a.shape == g.shape):
        raise ValueError("observation, raw_a, group_ids must share shape")
    if n_groups is None:
        if g.size == 0:
            return np.zeros(0, dtype=np.float64)
        n_groups = int(np.max(g)) + 1
    masses = np.zeros(int(n_groups), dtype=np.float64)
    contrib = o * a
    for group_index in range(int(n_groups)):
        masses[group_index] = float(contrib[g == group_index].sum())
    return masses


def total_mass(group_masses: np.ndarray) -> float:
    """m_{k,r} = Σ_g m_{k,r,g} — target-equivalent mass, not ESS."""
    return float(np.asarray(group_masses, dtype=np.float64).sum())


def normalized_weights(
    observation: np.ndarray,
    raw_a: np.ndarray,
    total: float,
) -> np.ndarray:
    """ā = O a / m (Hájek)."""
    if total < 0:
        raise ValueError("total mass must be nonnegative")
    o = np.asarray(observation, dtype=np.float64)
    a = np.asarray(raw_a, dtype=np.float64)
    if o.shape != a.shape:
        raise ValueError("observation and raw_a must share shape")
    if total == 0.0:
        return np.zeros_like(a)
    return (o * a) / float(total)


def composition(group_masses: np.ndarray, total: float) -> np.ndarray:
    """c_{k,r,g} = m_{k,r,g} / m_{k,r}."""
    masses = np.asarray(group_masses, dtype=np.float64)
    if total < 0:
        raise ValueError("total mass must be nonnegative")
    if total == 0.0:
        return np.zeros_like(masses)
    return masses / float(total)

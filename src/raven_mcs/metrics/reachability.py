"""Window reachability diagnostics (paper F7.11)."""

from __future__ import annotations

import numpy as np


def realized_block_group_deviation(
    omega_history: list[np.ndarray],
    mu: np.ndarray,
    active_flags: list[bool],
    eta: list[float],
) -> float:
    """Realized cumulative block-group deviation (previously named epsilon_reach).

    This computes the actual (not counterfactual/optimized) L2 norm of the
    weighted cumulative deviation of realized policies:
        ‖Σ_r η_r (M_r α_r − μ)‖_2 / Σ_r η_r

    For the true epsilon_reach (optimized lower bound), see:
        src/raven_mcs/metrics/reachability_optimization.py::solve_epsilon_reach
    """
    mu_arr = np.asarray(mu, dtype=np.float64)
    total_eta = 0.0
    cumulative = np.zeros_like(mu_arr, dtype=np.float64)
    for omega_r, active, eta_r in zip(omega_history, active_flags, eta):
        if not active:
            continue
        cumulative += eta_r * (omega_r - mu_arr)
        total_eta += eta_r
    if total_eta <= 0:
        return 0.0
    return float(np.linalg.norm(cumulative, ord=2) / total_eta)


def epsilon_reach(
    omega_history: list[np.ndarray],
    mu: np.ndarray,
    active_flags: list[bool],
    eta: list[float],
) -> float:
    """**DEPRECATED** — Use realized_block_group_deviation() instead.

    This function name is misleading: it computes realized deviation, not
    the optimized epsilon_reach lower bound. Renamed for clarity in P10-D.
    """
    return realized_block_group_deviation(omega_history, mu, active_flags, eta)


def epsilon_reach_block(
    omega_history: list[np.ndarray],
    mu: np.ndarray,
    active_flags: list[bool],
    eta: list[float],
    block_length: int,
) -> list[float]:
    """Compute ε_reach over sliding windows of length block_length."""
    mu_arr = np.asarray(mu, dtype=np.float64)
    results: list[float] = []
    n = len(omega_history)
    for start in range(0, n, block_length):
        end = min(start + block_length, n)
        total_eta = 0.0
        cumulative = np.zeros_like(mu_arr, dtype=np.float64)
        for i in range(start, end):
            if i < len(active_flags) and active_flags[i]:
                cumulative += eta[i] * (omega_history[i] - mu_arr)
                total_eta += eta[i]
        if total_eta > 0:
            results.append(float(np.linalg.norm(cumulative, ord=2) / total_eta))
        else:
            results.append(0.0)
    return results


def n_eff_support(
    n_eff_values: list[float],
    threshold: float = 1.0,
) -> float:
    """Fraction of windows where n_eff exceeds the threshold."""
    if not n_eff_values:
        return 0.0
    return float(np.mean(np.asarray(n_eff_values) >= threshold))


def min_propensity_quantile(
    propensity_values: np.ndarray,
    q: float = 0.05,
) -> float:
    """Lower q-quantile of propensity estimates."""
    p = np.asarray(propensity_values, dtype=np.float64)
    if len(p) == 0:
        return 0.0
    return float(np.quantile(p, q))

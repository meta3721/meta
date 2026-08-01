"""Distribution mismatch metrics — Delta_pair, Delta_c-s, Delta_group, etc. (paper F7.4–F7.8)."""

from __future__ import annotations

import numpy as np


def delta_group(omega_hat: np.ndarray, mu: np.ndarray) -> float:
    """Group mismatch: ‖ω̂ − μ‖_1."""
    return float(
        np.linalg.norm(
            np.asarray(omega_hat, dtype=np.float64) - np.asarray(mu, dtype=np.float64),
            ord=1,
        )
    )


def delta_pair(
    pi_hat: np.ndarray,
    pi_target: np.ndarray,
) -> float:
    """Controlled pair mismatch: ‖Π̂ − π^tar‖_1."""
    return float(
        np.linalg.norm(
            np.asarray(pi_hat, dtype=np.float64) - np.asarray(pi_target, dtype=np.float64),
            ord=1,
        )
    )


def delta_c_s(
    pi_hat_ks: np.ndarray,
    pi_target_ks: np.ndarray,
) -> float:
    """Client-stratum mismatch: Σ_{k,s} |Π̂_{k,s} − π^tar_{k,s}|."""
    return float(
        np.sum(
            np.abs(
                np.asarray(pi_hat_ks, dtype=np.float64)
                - np.asarray(pi_target_ks, dtype=np.float64)
            )
        )
    )


def avg_delta_group(
    omega_history: list[np.ndarray],
    mu: np.ndarray,
    active_flags: list[bool],
    eta: list[float],
) -> float:
    """Average per-window group mismatch: Σ_r η_r I_r ‖M_r α_r − μ‖_1 / S_R."""
    mu_arr = np.asarray(mu, dtype=np.float64)
    total_eta = 0.0
    weighted_sum = 0.0
    for omega_r, active, eta_r in zip(omega_history, active_flags, eta):
        if not active:
            continue
        weighted_sum += eta_r * float(np.linalg.norm(omega_r - mu_arr, ord=1))
        total_eta += eta_r
    if total_eta <= 0:
        return 0.0
    return float(weighted_sum / total_eta)


def avg_delta_ref(
    alpha_history: list[np.ndarray],
    beta_hat_history: list[np.ndarray],
    active_flags: list[bool],
    eta: list[float],
) -> float:
    """Average reference deviation: Σ_r η_r I_r √K_r ‖α_r − β̂_r‖_2 / S_R."""
    total_eta = 0.0
    weighted_sum = 0.0
    for alpha_r, beta_r, active, eta_r in zip(
        alpha_history, beta_hat_history, active_flags, eta
    ):
        if not active:
            continue
        k_r = len(alpha_r)
        deviation = float(np.linalg.norm(alpha_r - beta_r, ord=2))
        weighted_sum += eta_r * np.sqrt(k_r) * deviation
        total_eta += eta_r
    if total_eta <= 0:
        return 0.0
    return float(weighted_sum / total_eta)


def effective_group_distribution(
    pi_hat: np.ndarray,
    group_ids: np.ndarray,
    n_groups: int,
) -> np.ndarray:
    """Marginalise effective pair distribution to group distribution ω̂."""
    pi = np.asarray(pi_hat, dtype=np.float64)
    gids = np.asarray(group_ids, dtype=np.int64)
    omega = np.zeros(n_groups, dtype=np.float64)
    for g in range(n_groups):
        omega[g] = float(pi[gids == g].sum())
    return omega


def raw_arrival_distribution(
    raw_counts: np.ndarray,
) -> np.ndarray:
    """Normalise raw sample counts to a probability vector."""
    c = np.asarray(raw_counts, dtype=np.float64)
    total = float(c.sum())
    if total <= 0:
        return np.zeros_like(c)
    return c / total

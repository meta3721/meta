"""Accuracy metrics — RMSE_mu, MAE_mu, RMSE_rho, Gap_mis (paper §十, F7.1–F7.3)."""

from __future__ import annotations

import numpy as np


def atomic_arrival_weights(
    pi_hat_opp: np.ndarray,
    nu_hat: np.ndarray,
    p_hat_obs: np.ndarray,
    q_hat_use: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """F8.3 atomic arrival intensities and normalized arrival weights.

    Each contribution array is shaped ``(n_clients, n_units)``. ``nu_hat`` may
    also be a one-dimensional per-unit vector for exchangeable strata.
    """
    pi = np.asarray(pi_hat_opp, dtype=np.float64)
    p = np.asarray(p_hat_obs, dtype=np.float64)
    q = np.asarray(q_hat_use, dtype=np.float64)
    nu = np.asarray(nu_hat, dtype=np.float64)
    if pi.ndim != 2 or p.shape != pi.shape or q.shape != pi.shape:
        raise ValueError("pi_hat_opp, p_hat_obs, q_hat_use must share (client, unit) shape")
    if nu.ndim == 1:
        if nu.shape[0] != pi.shape[1]:
            raise ValueError("one-dimensional nu_hat must have n_units entries")
        nu = np.broadcast_to(nu, pi.shape)
    if nu.shape != pi.shape:
        raise ValueError("nu_hat must have (client, unit) shape")
    for name, values in (("pi_hat_opp", pi), ("nu_hat", nu), ("p_hat_obs", p), ("q_hat_use", q)):
        if not np.all(np.isfinite(values)) or np.any(values < 0):
            raise ValueError(f"{name} must be finite and non-negative")
    intensity = np.sum(pi * nu * p * q, axis=0)
    total = float(intensity.sum())
    if not np.isfinite(total) or total <= 0:
        raise ValueError("arrival intensity must have positive finite mass")
    return intensity, intensity / total


def _validated_weights(weights: np.ndarray, length: int, name: str) -> np.ndarray:
    values = np.asarray(weights, dtype=np.float64)
    if values.ndim != 1 or len(values) != length:
        raise ValueError(f"{name} must be one-dimensional with matching length")
    if not np.all(np.isfinite(values)) or np.any(values < 0):
        raise ValueError(f"{name} must be finite and non-negative")
    if abs(float(values.sum()) - 1.0) > 1e-10:
        raise ValueError(f"{name} must sum to one")
    return values


def rmse_mu(
    y_pred: np.ndarray,
    y_true: np.ndarray,
    target_weights: np.ndarray,
) -> float:
    """Target-weighted RMSE: sqrt[ Σ_i ϖ_i^tar (Ŷ_i − Y_i)² ].

    Weights are assumed pre-normalised on the test support.
    """
    yp = np.asarray(y_pred, dtype=np.float64)
    yt = np.asarray(y_true, dtype=np.float64)
    w = _validated_weights(target_weights, len(yp), "target_weights")
    if len(yp) != len(yt) or len(yp) != len(w):
        raise ValueError("y_pred, y_true, target_weights must have same length")
    return float(np.sqrt(np.sum(w * (yp - yt) ** 2)))


def mae_mu(
    y_pred: np.ndarray,
    y_true: np.ndarray,
    target_weights: np.ndarray,
) -> float:
    """Target-weighted MAE: Σ_i ϖ_i^tar |Ŷ_i − Y_i|."""
    yp = np.asarray(y_pred, dtype=np.float64)
    yt = np.asarray(y_true, dtype=np.float64)
    w = np.asarray(target_weights, dtype=np.float64)
    return float(np.sum(w * np.abs(yp - yt)))


def rmse_rho(
    y_pred: np.ndarray,
    y_true: np.ndarray,
    arrival_weights: np.ndarray,
) -> float:
    """Arrival-weighted RMSE — must use atomic-unit-level arrival weights."""
    return rmse_mu(y_pred, y_true, arrival_weights)


def gap_mis(
    rmse_target: float,
    rmse_arrival: float,
) -> float:
    """Misalignment gap: RMSE_mu − RMSE_rho.

    Positive → arrival distribution underestimates deployment risk.
    """
    return float(rmse_target - rmse_arrival)


def tail_head_rmse(
    y_pred: np.ndarray,
    y_true: np.ndarray,
    target_weights: np.ndarray,
    rho_g_arr: np.ndarray,  # R_g = rho_g / mu_g per group
    group_ids: np.ndarray,
    mu_g: np.ndarray,
    *,
    tail_quantile: float = 0.2,
    head_quantile: float = 0.2,
) -> dict[str, float]:
    """Compute Tail and Head RMSE based on arrival-to-target ratio R_g = rho_g/mu_g.

    Groups are sorted by R_g. Bottom tail_quantile fraction = tail groups,
    top head_quantile = head groups. Freeze group lists and apply to test.

    This replaces the old tail_rmse that used prediction error top 10%.
    """
    yp = np.asarray(y_pred, dtype=np.float64)
    yt = np.asarray(y_true, dtype=np.float64)
    w = np.asarray(target_weights, dtype=np.float64)
    gids = np.asarray(group_ids, dtype=np.int64)
    rg = np.asarray(rho_g_arr, dtype=np.float64)

    n_groups = len(rg)
    if n_groups == 0:
        return {"tail_rmse": 0.0, "head_rmse": 0.0, "mid_rmse": 0.0}

    sorted_indices = np.argsort(rg)
    n_tail = max(1, int(n_groups * tail_quantile))
    n_head = max(1, int(n_groups * head_quantile))

    tail_groups = set(sorted_indices[:n_tail])
    head_groups = set(sorted_indices[-n_head:])

    def _group_rmse(groups_set: set[int]) -> float:
        mask = np.array([g in groups_set for g in gids])
        if not np.any(mask):
            return 0.0
        w_sub = w[mask]
        w_sub = w_sub / w_sub.sum()
        return float(np.sqrt(np.sum(w_sub * (yp[mask] - yt[mask]) ** 2)))

    tail_rmse_val = _group_rmse(tail_groups)
    head_rmse_val = _group_rmse(head_groups)

    mid_groups = set(range(n_groups)) - tail_groups - head_groups
    mid_rmse_val = _group_rmse(mid_groups)

    return {
        "tail_rmse": tail_rmse_val,
        "head_rmse": head_rmse_val,
        "mid_rmse": mid_rmse_val,
    }


def tail_rmse(
    y_pred: np.ndarray,
    y_true: np.ndarray,
    target_weights: np.ndarray,
    tail_quantile: float = 0.9,
) -> float:
    """DEPRECATED: Old tail_rmse using prediction error ranking.

    Use tail_head_rmse() with R_g = rho_g/mu_g ranking instead.
    Kept for backward compatibility with existing tests.
    """
    yp = np.asarray(y_pred, dtype=np.float64)
    yt = np.asarray(y_true, dtype=np.float64)
    w = np.asarray(target_weights, dtype=np.float64)
    errors = (yp - yt) ** 2
    threshold = float(np.quantile(errors, tail_quantile))
    mask = errors >= threshold
    if not np.any(mask):
        return 0.0
    w_tail = w[mask] / w[mask].sum()
    return float(np.sqrt(np.sum(w_tail * errors[mask])))


def group_rmse(
    y_pred: np.ndarray,
    y_true: np.ndarray,
    target_weights: np.ndarray,
    group_ids: np.ndarray,
) -> dict[int, float]:
    """Per-group RMSE_mu."""
    yp = np.asarray(y_pred, dtype=np.float64)
    yt = np.asarray(y_true, dtype=np.float64)
    w = np.asarray(target_weights, dtype=np.float64)
    groups = np.asarray(group_ids)
    result: dict[int, float] = {}
    for g in np.unique(groups):
        mask = groups == g
        if not np.any(mask):
            result[int(g)] = float("nan")
            continue
        w_g = w[mask] / w[mask].sum()
        result[int(g)] = float(np.sqrt(np.sum(w_g * (yp[mask] - yt[mask]) ** 2)))
    return result

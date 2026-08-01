"""Local Hájek-weighted objective for client training (P10-A).

F_hat_H_{k,r}(theta) = sum_i a_bar_{k,r,i} * 0.5 * (f_theta(i) - Z_{k,r,i})^2

where a_bar sums to 1 within client. Do NOT multiply by m. Do NOT confuse n_eff with m.
"""

from __future__ import annotations

import torch
from torch import nn


def local_hajek_loss(
    predictions: torch.Tensor,
    targets: torch.Tensor,
    a_bar_weights: torch.Tensor,
) -> torch.Tensor:
    """Compute local Hájek-weighted MSE loss.

    Args:
        predictions: Model predictions f_theta(i) for each record, shape (N,).
        targets: Observed values Z_{k,r,i}, shape (N,).
        a_bar_weights: Normalized Hájek weights sum=1 within client, shape (N,).

    Returns:
        Scalar loss = sum_i a_bar_i * 0.5 * (pred_i - target_i)^2.
    """
    if predictions.shape != targets.shape:
        raise ValueError("predictions and targets must have same shape")
    if predictions.shape != a_bar_weights.shape:
        raise ValueError("predictions and a_bar_weights must have same shape")

    squared_errors = (predictions - targets) ** 2
    weighted = a_bar_weights * squared_errors
    return 0.5 * weighted.sum()


def normalize_a_bar(raw_a: torch.Tensor, observations: torch.Tensor) -> torch.Tensor:
    """Compute normalized Hájek weights: a_bar = O * a / m.

    Args:
        raw_a: Raw first-stage weights a_{k,r,i}, shape (N,).
        observations: Observation indicators O_i, shape (N,).

    Returns:
        Normalized weights a_bar sum=1, shape (N,).
    """
    weighted = observations * raw_a
    total = weighted.sum()
    if total <= 0:
        return torch.zeros_like(weighted)
    return weighted / total

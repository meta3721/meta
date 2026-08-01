"""P2 feasibility helpers (paper F6.5–F6.6)."""

from __future__ import annotations


def alpha_bar(*, alpha_max: float, n_active: int) -> float:
    """ᾱ = min(1, max(α_max, 1/K))."""
    if n_active <= 0:
        raise ValueError("n_active must be positive")
    if alpha_max <= 0:
        raise ValueError("alpha_max must be positive")
    return float(min(1.0, max(float(alpha_max), 1.0 / float(n_active))))


def ess_ball_bound(*, e_min: float, n_active: int) -> float:
    """Ē = min(E_min, K); constraint ‖α‖₂² ≤ 1/Ē."""
    if n_active <= 0:
        raise ValueError("n_active must be positive")
    if e_min <= 0:
        raise ValueError("e_min must be positive")
    return float(min(float(e_min), float(n_active)))


def validate_p2_lambdas(
    *,
    lambda_beta: float,
    lambda_group: float,
    max_server_learning_rate: float,
) -> None:
    """Require λ_β>0 and λ_g ≥ max server learning rate."""
    if not (lambda_beta > 0):
        raise ValueError("lambda_beta must be > 0 for P2 uniqueness")
    if lambda_group < max_server_learning_rate:
        raise ValueError(
            "lambda_group must be >= max_server_learning_rate "
            f"(got {lambda_group} < {max_server_learning_rate})"
        )

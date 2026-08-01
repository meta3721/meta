"""First-stage observation selection (Phase 4 / design §8.3).

Generates Bernoulli observation indicators O_{k,r,i} for each
(client, window, risk_unit) tuple using logistic propensity models.
Pre-outcome features only — no Y_i, no current error.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class ObservationConfig:
    """Observation propensity generation parameters."""

    mean_observation_rate: float = 0.20
    p_lo: float = 0.02
    p_hi: float = 0.98
    num_features: int = 3
    seed: int = 26001


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -50, 50)))


def generate_observation_coefficients(
    config: ObservationConfig,
    rng: np.random.Generator,
) -> tuple[float, np.ndarray]:
    """Generate oracle observation propensity coefficients.

    Returns (intercept a0, coefficients a).
    Coefficients are scaled so the population-average observation rate
    approximately matches config.mean_observation_rate.
    """
    # Random coefficients
    a = rng.normal(0, 1.0, config.num_features)
    # Calibrate intercept to hit the target mean rate
    # For N(0,1) features, E[sigmoid(a0 + a^T X)] ≈ sigmoid(a0) + O(var)
    # Solve: sigmoid(a0) ≈ target_rate
    target_logit = np.log(
        config.mean_observation_rate / (1.0 - config.mean_observation_rate)
    )
    a0 = float(target_logit)
    return a0, a


def apply_observation_selection(
    pre_outcome_features: np.ndarray,
    a0: float,
    a: np.ndarray,
    p_lo: float,
    p_hi: float,
) -> np.ndarray:
    """Compute observation probabilities and Bernoulli draws.

    Args:
        pre_outcome_features: (N, D) array of pre-outcome features
        a0: intercept
        a: (D,) coefficients
        p_lo, p_hi: clipping bounds

    Returns:
        (N,) array of boolean observation indicators
    """
    logits = a0 + np.dot(pre_outcome_features, a)
    p_obs = np.clip(_sigmoid(logits), p_lo, p_hi)
    # Use fresh RNG per call for reproducibility within the same seed
    rng = np.random.default_rng()
    return rng.random(len(p_obs)) < p_obs, p_obs


def generate_observations_for_trace(
    num_entries: int,
    config: ObservationConfig,
) -> tuple[np.ndarray, np.ndarray, float, np.ndarray]:
    """Generate oracle observations for an entire EventTrace.

    Returns:
        O: (N,) bool array
        p_oracle: (N,) float array of true observation probabilities
        a0: intercept
        a: coefficients
    """
    rng = np.random.default_rng(config.seed)
    a0, a = generate_observation_coefficients(config, rng)

    # Generate synthetic pre-outcome features
    pre_features = rng.normal(0, 1, (num_entries, config.num_features))

    logits = a0 + np.dot(pre_features, a)
    p_oracle = np.clip(_sigmoid(logits), config.p_lo, config.p_hi)
    O = rng.random(num_entries) < p_oracle

    return O, p_oracle, a0, a

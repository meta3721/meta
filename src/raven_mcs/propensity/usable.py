"""Lagged usable propensity q̂ (Phase 7 skeleton)."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from raven_mcs.propensity.leakage import assert_q_features_leakage_free


def deadline_slack_pre(window_close_time: float, registration_time: float) -> float:
    """Registration-time slack; available before compute/network outcomes."""
    slack = float(window_close_time) - float(registration_time)
    if not np.isfinite(slack):
        raise ValueError("deadline_slack_pre must be finite")
    return slack


@dataclass
class UsablePropensity:
    """
    Server-side online logistic on all registered attempts, including U=0.

    One-window lag: caller must only update with previous-window rows.
    """

    l2: float = 1e-2
    prior_rate: float = 0.5
    q_min: float = 0.05
    q_max: float = 0.95
    min_samples: int = 5
    feature_names: tuple[str, ...] = (
        "bias",
        "model_age",
        "device_class",
        "network_budget",
        "deadline_slack_pre",
    )
    weights: np.ndarray = field(default_factory=lambda: np.zeros(5, dtype=np.float64))
    history_x: list[np.ndarray] = field(default_factory=list)
    history_y: list[float] = field(default_factory=list)

    def __post_init__(self) -> None:
        assert_q_features_leakage_free(self.feature_names)
        self.weights = np.zeros(len(self.feature_names), dtype=np.float64)

    def predict(self, features: np.ndarray) -> float:
        x = np.asarray(features, dtype=np.float64).reshape(-1)
        if x.shape[0] != len(self.feature_names):
            raise ValueError("feature dimension mismatch")
        if len(self.history_y) < self.min_samples:
            raw = float(self.prior_rate)
        else:
            logit = float(self.weights @ x)
            raw = float(1.0 / (1.0 + np.exp(-logit)))
        return float(np.clip(raw, self.q_min, self.q_max))

    def update_lagged(self, features: np.ndarray, usable: float) -> None:
        """Update using a completed previous-window attempt; never drop U=0."""
        x = np.asarray(features, dtype=np.float64).reshape(-1)
        y = float(usable)
        self.history_x.append(x)
        self.history_y.append(y)
        if len(self.history_y) < self.min_samples:
            return
        x_mat = np.asarray(self.history_x, dtype=np.float64)
        y_vec = np.asarray(self.history_y, dtype=np.float64)
        logits = x_mat @ self.weights
        probs = 1.0 / (1.0 + np.exp(-logits))
        grad = x_mat.T @ (probs - y_vec) / len(y_vec) + self.l2 * self.weights
        self.weights = self.weights - 0.5 * grad

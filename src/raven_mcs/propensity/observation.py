"""Lagged observation propensity p̂ with diagnostics (P10-B).

Online L2-logistic using only past completed risk sets.
Current outcome never trains the score used for itself.
Outputs: Brier, log loss, ECE diagnostics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from scipy.special import expit as sigmoid

from raven_mcs.propensity.leakage import assert_q_features_leakage_free


@dataclass
class ObservationPropensityDiagnostics:
    brier: float = 0.0
    log_loss: float = 0.0
    ece: float = 0.0
    calibration_bins: int = 10
    calibration_curve: list[tuple[float, float]] = field(default_factory=list)


@dataclass
class ObservationPropensity:
    """
    Online L2-logistic using only past completed risk sets.

    Current outcome never trains the score used for itself.
    """

    l2: float = 1e-2
    prior_rate: float = 0.2
    min_samples: int = 5
    feature_names: tuple[str, ...] = (
        "bias",
        "hour_block",
        "planned_workload_pre",
    )
    weights: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=np.float64))
    history_x: list[np.ndarray] = field(default_factory=list)
    history_y: list[float] = field(default_factory=list)
    _previous_weights: Optional[np.ndarray] = None

    def __post_init__(self) -> None:
        assert_q_features_leakage_free(self.feature_names)
        self.weights = np.zeros(len(self.feature_names), dtype=np.float64)

    def predict(self, features: np.ndarray) -> float:
        x = np.asarray(features, dtype=np.float64).reshape(-1)
        if x.shape[0] != len(self.feature_names):
            raise ValueError("feature dimension mismatch")
        if len(self.history_y) < self.min_samples:
            return float(self.prior_rate)
        logit = float(self.weights @ x)
        return float(sigmoid(logit))

    def predict_batch(self, features_matrix: np.ndarray) -> np.ndarray:
        X = np.asarray(features_matrix, dtype=np.float64)
        if X.ndim == 1:
            X = X.reshape(1, -1)
        if len(self.history_y) < self.min_samples:
            return np.full(X.shape[0], self.prior_rate, dtype=np.float64)
        return sigmoid(X @ self.weights)

    def update_after_completion(self, features: np.ndarray, observed_rate: float) -> None:
        x = np.asarray(features, dtype=np.float64).reshape(-1)
        y = float(np.clip(observed_rate, 0.0, 1.0))
        self.history_x.append(x)
        self.history_y.append(y)
        self._previous_weights = self.weights.copy()

        if len(self.history_y) < self.min_samples:
            return
        x_mat = np.asarray(self.history_x, dtype=np.float64)
        y_vec = np.asarray(self.history_y, dtype=np.float64)
        logits = x_mat @ self.weights
        probs = sigmoid(logits)
        grad = x_mat.T @ (probs - y_vec) / len(y_vec) + self.l2 * self.weights
        self.weights = self.weights - 0.5 * grad

    def compute_diagnostics(self, n_bins: int = 10) -> ObservationPropensityDiagnostics:
        """Compute Brier score, log loss, and ECE on history."""
        if len(self.history_y) < self.min_samples:
            return ObservationPropensityDiagnostics()

        X = np.asarray(self.history_x, dtype=np.float64)
        y = np.asarray(self.history_y, dtype=np.float64)
        probs = sigmoid(X @ self.weights)

        brier = float(np.mean((probs - y) ** 2))
        eps = 1e-15
        log_loss_val = float(-np.mean(
            y * np.log(np.clip(probs, eps, 1 - eps)) +
            (1 - y) * np.log(1 - np.clip(probs, eps, 1 - eps))
        ))

        # ECE: Expected Calibration Error
        bin_edges = np.linspace(0, 1, n_bins + 1)
        ece = 0.0
        calibration_curve: list[tuple[float, float]] = []
        for i in range(n_bins):
            lo, hi = bin_edges[i], bin_edges[i + 1]
            mask = (probs >= lo) & (probs < hi) if i < n_bins - 1 else (probs >= lo) & (probs <= hi)
            if np.any(mask):
                bin_conf = float(np.mean(probs[mask]))
                bin_acc = float(np.mean(y[mask]))
                calibration_curve.append((bin_conf, bin_acc))
                ece += float(np.abs(bin_conf - bin_acc)) * np.sum(mask) / len(y)

        return ObservationPropensityDiagnostics(
            brier=brier,
            log_loss=log_loss_val,
            ece=ece,
            calibration_bins=n_bins,
            calibration_curve=calibration_curve,
        )

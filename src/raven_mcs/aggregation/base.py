"""Unified Aggregator interface (Phase 8)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class WindowAggregateInput:
    client_ids: list[str]
    raw_counts: np.ndarray
    total_masses: np.ndarray
    compositions: np.ndarray  # groups × clients
    beta_hat: np.ndarray | None = None
    staleness: np.ndarray | None = None
    variance_diag: np.ndarray | None = None
    debt: np.ndarray | None = None
    mu: np.ndarray | None = None
    extras: dict[str, Any] = field(default_factory=dict)


class Aggregator(ABC):
    name: str

    def fit_or_prepare(self, **kwargs: Any) -> None:
        del kwargs

    @abstractmethod
    def compute_server_weights(self, payload: WindowAggregateInput) -> np.ndarray:
        raise NotImplementedError

    def compute_local_weights(self, payload: WindowAggregateInput) -> np.ndarray:
        """Compute per-sample weights used in client-side local training.

        Subclasses that need non-uniform local weighting (e.g. Local-Hajek)
        must override this method. The default returns uniform weights
        proportional to raw_counts.
        """
        raw = np.asarray(payload.raw_counts, dtype=np.float64)
        total = float(raw.sum())
        if total <= 0:
            return np.ones_like(raw) / len(raw)
        return raw / total

    def update_state(self, **kwargs: Any) -> None:
        del kwargs

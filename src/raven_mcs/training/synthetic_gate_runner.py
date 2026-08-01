"""Synthetic gate runner — minimal vector WindowRunner retained for G2–G5 gates.

This module was moved from window_runner.py during P10. The synthetic gate runner
uses synthetic EventTrace rows and a simple vector theta (not full NDMF training).
It serves as the G2–G5 gate verification harness only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from raven_mcs.aggregation.base import Aggregator, WindowAggregateInput
from raven_mcs.aggregation.debt import coverage_mix, update_debt
from raven_mcs.aggregation.methods import get_aggregator
from raven_mcs.correction.second_stage import beta_hat, d_weight, two_stage_mass
from raven_mcs.simulation.event_trace import EventTrace
from raven_mcs.training.window_timing import WindowClock, WindowTimingError
from raven_mcs.utils.hashing import sha256_json


@dataclass
class WindowMetrics:
    window_id: int
    active: bool
    alpha: list[float]
    theta_hash_before: str
    theta_hash_after: str
    debt_l1: float
    active_clients: list[str]


@dataclass
class SyntheticGateRunner:
    """Minimal executable window loop for gates G2–G5.

    Uses synthetic EventTrace rows; model state is a vector θ (not full NDMF training).
    """

    trace: EventTrace
    aggregator: Aggregator
    mu: np.ndarray
    eta: float = 1.0
    theta: np.ndarray = field(default_factory=lambda: np.zeros(4, dtype=np.float64))
    debt: np.ndarray | None = None
    scale: float = 0.0
    omega_sum: np.ndarray | None = None
    metrics: list[WindowMetrics] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.mu = np.asarray(self.mu, dtype=np.float64)
        if self.debt is None:
            self.debt = np.zeros_like(self.mu)
        if self.omega_sum is None:
            self.omega_sum = np.zeros_like(self.mu)
        self.clock = WindowClock(num_windows=int(self.trace.metadata.num_windows))

    def _theta_hash(self) -> str:
        return sha256_json(self.theta.tolist())

    def run(self) -> list[WindowMetrics]:
        events = self.trace.events
        for window_id in range(int(self.trace.metadata.num_windows)):
            before = self._theta_hash()
            version = self.clock.model_version
            rows = events.loc[events["window_id"] == window_id]
            registered = rows
            active_rows = registered.loc[registered["U"].astype(int) == 1]
            if active_rows.empty:
                self.clock.skip_empty_window()
                after = self._theta_hash()
                if before != after:
                    raise WindowTimingError("Empty window must not change theta")
                self.metrics.append(
                    WindowMetrics(
                        window_id=window_id,
                        active=False,
                        alpha=[],
                        theta_hash_before=before,
                        theta_hash_after=after,
                        debt_l1=float(np.linalg.norm(self.debt, ord=1)),
                        active_clients=[],
                    )
                )
                continue

            for _, row in active_rows.iterrows():
                self.clock.register_local_work(int(row["downloaded_version"]))
                if int(row["downloaded_version"]) != version:
                    raise WindowTimingError("downloaded_version drifted inside window")

            client_ids = active_rows["client_id"].astype(str).tolist()
            raw_counts = active_rows["raw_workload"].to_numpy(dtype=np.float64)
            logits = np.vstack(
                [raw_counts, np.full_like(raw_counts, raw_counts.mean())]
            )
            compositions = np.exp(logits - logits.max(axis=0, keepdims=True))
            compositions = compositions / compositions.sum(axis=0, keepdims=True)
            if compositions.shape[0] != self.mu.shape[0]:
                compositions = np.tile(
                    1.0 / self.mu.shape[0], (self.mu.shape[0], len(client_ids))
                )

            masses = np.maximum(raw_counts, 1e-6)
            q_hat = active_rows["oracle_q"].to_numpy(dtype=np.float64)
            d = d_weight(q_hat)
            b = two_stage_mass(masses, d)
            beta = beta_hat(b)
            staleness = active_rows["model_age"].to_numpy(dtype=np.float64)
            payload = WindowAggregateInput(
                client_ids=client_ids,
                raw_counts=raw_counts,
                total_masses=masses,
                compositions=compositions,
                beta_hat=beta,
                staleness=staleness,
                variance_diag=np.ones(len(client_ids)),
                debt=self.debt,
                mu=self.mu,
            )
            alpha = self.aggregator.compute_server_weights(payload)
            if abs(float(alpha.sum()) - 1.0) > 1e-8:
                raise WindowTimingError("alpha must sum to 1")

            updates = np.stack(
                [
                    np.full(self.theta.shape, fill_value=1.0 + 0.1 * idx)
                    for idx in range(len(client_ids))
                ],
                axis=0,
            )
            mid_hash = self._theta_hash()
            if mid_hash != before:
                raise WindowTimingError("theta changed before the single server update")

            self.theta = self.theta - float(self.eta) * (alpha[:, None] * updates).sum(
                axis=0
            )
            self.clock.apply_server_update()

            omega = coverage_mix(compositions, alpha)
            self.debt = update_debt(
                self.debt, mu=self.mu, omega=omega, eta=float(self.eta), active=True
            )
            self.scale += float(self.eta)
            self.omega_sum = self.omega_sum + float(self.eta) * omega

            after = self._theta_hash()
            self.metrics.append(
                WindowMetrics(
                    window_id=window_id,
                    active=True,
                    alpha=alpha.tolist(),
                    theta_hash_before=before,
                    theta_hash_after=after,
                    debt_l1=float(np.linalg.norm(self.debt, ord=1)),
                    active_clients=client_ids,
                )
            )
        return self.metrics

    def omega_bar(self) -> np.ndarray:
        if self.scale <= 0:
            raise RuntimeError("No active windows accumulated")
        return self.omega_sum / self.scale


def build_synthetic_runner(
    trace: EventTrace,
    *,
    method: str = "raven",
    n_groups: int = 2,
) -> SyntheticGateRunner:
    mu = np.full(n_groups, 1.0 / n_groups)
    return SyntheticGateRunner(trace=trace, aggregator=get_aggregator(method), mu=mu)

"""Method aggregators used by WindowRunner (P10-C — method semantics correction).

Deployable methods (11/11):
  1. Central-All          — true centralized training (NOT uniform alpha)
  2. Central-Delivered    — true centralized training (NOT uniform alpha)
  3. FedAvg-Window        — raw-count proportional
  4. FedAsync-Window      — staleness-decayed raw counts
  5. TimeAlign-Agg        — staleness-aligned weights (no target correction)
  6. Local-Hajek          — local Hajek weights (first-stage only)
  7. TwoStage-Hajek       — beta_hat via two-stage correction
  8. Inst-Cal             — full two-stage correction + P2 with Q=0
  9. Debt-Cal             — raw composition + P2 group+debt (rewards debt coverage)
  10. RAVEN-MCS           — full P2 convex optimization
  11. RAVEN-SimOracle     — RAVEN with oracle q (true usable probabilities)

External baseline pending (1):
  - FLAMF-Original        — EXTERNAL_BASELINE_NOT_INTEGRATED

CRITICAL CHANGES (P10-C):
  - Central-All/Central-Delivered: removed from aggregation-only; require true centralized training
  - Inst-Cal: fixed — uses full two-stage correction + P2 with Q=0 (was broken 1/raw_counts)
  - Debt-Cal: fixed — uses raw composition + P2 group+debt (was broken exp(-debt))
  - FLAMF: marked as external, removed from "completed methods"
"""

from __future__ import annotations

import numpy as np

from raven_mcs.aggregation.base import Aggregator, WindowAggregateInput
from raven_mcs.aggregation.p2_cvxpy import solve_p2


def _normalize(weights: np.ndarray) -> np.ndarray:
    w = np.asarray(weights, dtype=np.float64)
    if np.any(w < 0):
        raise ValueError("server weights must be nonnegative")
    total = float(w.sum())
    if total <= 0:
        raise ValueError("server weights sum to zero")
    return w / total


# ---------------------------------------------------------------------------
# 1. Central-All — equal weights for all active clients
# ---------------------------------------------------------------------------

class CentralAllAggregator(Aggregator):
    """True centralized training baseline — uses all valid observations without
    compute/network U restriction, same Common-NDMF architecture.

    NOT a simple uniform-alpha aggregator. Must run full centralized SGD.
    This aggregator raises NotImplementedError in the aggregation pathway;
    centralized training is handled separately by scripts/run_central.py.
    """

    name = "central_all"

    def compute_server_weights(self, payload: WindowAggregateInput) -> np.ndarray:
        raise NotImplementedError(
            "Central-All requires true centralized training, not aggregation. "
            "Use scripts/run_central.py for centralized baselines."
        )


# ---------------------------------------------------------------------------
# 2. Central-Delivered — true centralized training on delivered data
# ---------------------------------------------------------------------------

class CentralDeliveredAggregator(Aggregator):
    """True centralized training on final usable data — no correction applied.
    Uses same Common-NDMF architecture. More raw data access than federated methods.

    NOT a raw-count proportional aggregator. Must run full centralized SGD.
    """

    name = "central_delivered"

    def compute_server_weights(self, payload: WindowAggregateInput) -> np.ndarray:
        raise NotImplementedError(
            "Central-Delivered requires true centralized training, not aggregation. "
            "Use scripts/run_central.py for centralized baselines."
        )


# ---------------------------------------------------------------------------
# 3. FedAvg-Window — sample-size proportional
# ---------------------------------------------------------------------------

class FedAvgWindowAggregator(Aggregator):
    name = "fedavg_window"

    def compute_server_weights(self, payload: WindowAggregateInput) -> np.ndarray:
        return _normalize(payload.raw_counts)


# ---------------------------------------------------------------------------
# 4. FedAsync-Window — staleness-decayed sample-size proportional
# ---------------------------------------------------------------------------

class FedAsyncWindowAggregator(Aggregator):
    name = "fedasync_window"

    def __init__(self, kappa_tau: float = 0.1) -> None:
        self.kappa_tau = float(kappa_tau)

    def compute_server_weights(self, payload: WindowAggregateInput) -> np.ndarray:
        staleness = (
            np.asarray(payload.staleness, dtype=np.float64)
            if payload.staleness is not None
            else np.zeros_like(payload.raw_counts, dtype=np.float64)
        )
        return _normalize(payload.raw_counts * np.exp(-self.kappa_tau * staleness))


# ---------------------------------------------------------------------------
# 5. TimeAlign-Agg — staleness-aligned weights, no target correction
# ---------------------------------------------------------------------------

class TimeAlignAggregator(Aggregator):
    """TimeAlign-Agg: same Common-NDMF backbone with time/staleness-aligned
    weights.  No design ratio, no observation/usable correction, no
    instant calibration, no debt, no reference, no variance —
    staleness penalty only.

    Design §13.2 / execution instruction E1 baseline.
    """

    name = "timealign_agg"

    def __init__(self, kappa_tau: float = 0.1, use_sample_size: bool = True) -> None:
        self.kappa_tau = float(kappa_tau)
        self.use_sample_size = bool(use_sample_size)

    def compute_server_weights(self, payload: WindowAggregateInput) -> np.ndarray:
        staleness = (
            np.asarray(payload.staleness, dtype=np.float64)
            if payload.staleness is not None
            else np.zeros_like(payload.raw_counts, dtype=np.float64)
        )
        base = (
            payload.raw_counts.astype(np.float64)
            if self.use_sample_size
            else np.ones(len(payload.client_ids), dtype=np.float64)
        )
        return _normalize(base * np.exp(-self.kappa_tau * staleness))


# ---------------------------------------------------------------------------
# 6. FLAMF-Original — placeholder for external baseline
# ---------------------------------------------------------------------------

class FLAMFOriginalAggregator(Aggregator):
    """FLAMF-Original — EXTERNAL BASELINE, NOT INTEGRATED.

    This is a stub placeholder. FLAMF is an external baseline that requires
    loading a separately-trained FLAMF model and converting its output format.
    It is NOT a completed method and must NOT enter E1 or generate paper results.

    Status: EXTERNAL_BASELINE_NOT_INTEGRATED.
    """

    name = "flamf_original"

    def compute_server_weights(self, payload: WindowAggregateInput) -> np.ndarray:
        raise NotImplementedError(
            "FLAMF-Original is an external baseline and is not integrated. "
            "Do not use in P10 smoke or E1 experiments."
        )


# ---------------------------------------------------------------------------
# 7. Local-Hajek — first-stage Hajek weights only (no second-stage)
# ---------------------------------------------------------------------------

class LocalHajekAggregator(Aggregator):
    """Local-Hajek: uses first-stage Hajek weights (design ratio × IPW)
    without second-stage reference correction.  Suitable for local-only
    weighting where two-stage is unavailable.
    """

    name = "local_hajek"

    def compute_server_weights(self, payload: WindowAggregateInput) -> np.ndarray:
        # Fall back to raw-count proportional when two-stage data unavailable
        return _normalize(payload.raw_counts)

    def compute_local_weights(self, payload: WindowAggregateInput) -> np.ndarray:
        """First-stage Hajek local weights = raw total_masses."""
        masses = np.asarray(payload.total_masses, dtype=np.float64)
        total = float(masses.sum())
        if total <= 0:
            n = len(payload.client_ids)
            return np.ones(n) / n
        return masses / total


# ---------------------------------------------------------------------------
# 8. TwoStage-Hajek — beta_hat via two-stage correction
# ---------------------------------------------------------------------------

class TwoStageHajekAggregator(Aggregator):
    name = "twostage_hajek"

    def compute_server_weights(self, payload: WindowAggregateInput) -> np.ndarray:
        if payload.beta_hat is None:
            raise ValueError("TwoStage-Hajek requires beta_hat")
        return _normalize(payload.beta_hat)


# ---------------------------------------------------------------------------
# 9. Inst-Cal — instant calibration from current observations
# ---------------------------------------------------------------------------

class InstCalAggregator(Aggregator):
    """Instant calibration: full two-stage correction + P2 with Q=0.

    Uses same zeta/p/q/beta pipeline as RAVEN but with zero debt (Q=0).
    Retains group/reference/variance/staleness penalties.
    No debt update — Q is always zero.
    """

    name = "inst_cal"

    def __init__(
        self,
        *,
        lambda_group: float = 1.0,
        lambda_beta: float = 1.0,
        lambda_variance: float = 0.1,
        lambda_staleness: float = 0.1,
        alpha_max: float = 0.5,
        e_min: float = 3.0,
        max_server_learning_rate: float = 1.0,
    ) -> None:
        self.lambda_group = lambda_group
        self.lambda_beta = lambda_beta
        self.lambda_variance = lambda_variance
        self.lambda_staleness = lambda_staleness
        self.alpha_max = alpha_max
        self.e_min = e_min
        self.max_server_learning_rate = max_server_learning_rate

    def compute_server_weights(self, payload: WindowAggregateInput) -> np.ndarray:
        if (
            payload.beta_hat is None
            or payload.compositions is None
            or payload.mu is None
        ):
            raise ValueError("Inst-Cal requires compositions, mu, beta_hat")

        n_active = len(payload.client_ids)
        variance = (
            payload.variance_diag
            if payload.variance_diag is not None
            else np.ones(n_active)
        )
        staleness = (
            payload.staleness if payload.staleness is not None else np.zeros(n_active)
        )
        # P2 with Q=0 (no debt)
        zero_debt = np.zeros(payload.mu.shape[0], dtype=np.float64)

        result = solve_p2(
            payload.compositions,
            payload.mu,
            payload.beta_hat,
            zero_debt,  # Q=0
            variance,
            staleness,
            lambda_group=self.lambda_group,
            lambda_beta=self.lambda_beta,
            lambda_variance=self.lambda_variance,
            lambda_staleness=self.lambda_staleness,
            alpha_max=self.alpha_max,
            e_min=min(self.e_min, n_active),
            max_server_learning_rate=self.max_server_learning_rate,
        )
        return _normalize(result.alpha)


# ---------------------------------------------------------------------------
# 10. Debt-Cal — debt-aware calibration
# ---------------------------------------------------------------------------

class DebtCalAggregator(Aggregator):
    """Debt calibration: uses raw local composition (no zeta/p/q) with
    P2 instantaneous group calibration and debt.

    Debt must ENCOURAGE covering under-debt groups. No reference correction.
    Does NOT use zeta/p/q or two-stage correction.
    """

    name = "debt_cal"

    def __init__(
        self,
        *,
        lambda_group: float = 1.0,
        lambda_variance: float = 0.1,
        lambda_staleness: float = 0.1,
        alpha_max: float = 0.5,
        e_min: float = 3.0,
        max_server_learning_rate: float = 1.0,
    ) -> None:
        self.lambda_group = lambda_group
        self.lambda_variance = lambda_variance
        self.lambda_staleness = lambda_staleness
        self.alpha_max = alpha_max
        self.e_min = e_min
        self.max_server_learning_rate = max_server_learning_rate

    def compute_server_weights(self, payload: WindowAggregateInput) -> np.ndarray:
        if (
            payload.compositions is None
            or payload.mu is None
            or payload.debt is None
        ):
            raise ValueError("Debt-Cal requires compositions, mu, debt")

        n_active = len(payload.client_ids)
        variance = (
            payload.variance_diag
            if payload.variance_diag is not None
            else np.ones(n_active)
        )
        staleness = (
            payload.staleness if payload.staleness is not None else np.zeros(n_active)
        )
        # Raw-count proportional beta (no zeta/p/q)
        raw = np.asarray(payload.raw_counts, dtype=np.float64)
        raw_total = float(raw.sum())
        beta_ref = raw / raw_total if raw_total > 0 else np.ones(n_active) / n_active

        result = solve_p2(
            payload.compositions,
            payload.mu,
            beta_ref,
            payload.debt,
            variance,
            staleness,
            lambda_group=self.lambda_group,
            lambda_beta=0.0,  # No reference penalty
            lambda_variance=self.lambda_variance,
            lambda_staleness=self.lambda_staleness,
            alpha_max=self.alpha_max,
            e_min=min(self.e_min, n_active),
            max_server_learning_rate=self.max_server_learning_rate,
        )
        return _normalize(result.alpha)


# ---------------------------------------------------------------------------
# 11. RAVEN-MCS — full P2 convex optimization
# ---------------------------------------------------------------------------

class RavenAggregator(Aggregator):
    name = "raven"

    def __init__(
        self,
        *,
        lambda_group: float = 1.0,
        lambda_beta: float = 1.0,
        lambda_variance: float = 0.1,
        lambda_staleness: float = 0.1,
        alpha_max: float = 0.5,
        e_min: float = 3.0,
        max_server_learning_rate: float = 1.0,
    ) -> None:
        self.lambda_group = lambda_group
        self.lambda_beta = lambda_beta
        self.lambda_variance = lambda_variance
        self.lambda_staleness = lambda_staleness
        self.alpha_max = alpha_max
        self.e_min = e_min
        self.max_server_learning_rate = max_server_learning_rate
        self.solve_results = []

    def compute_server_weights(self, payload: WindowAggregateInput) -> np.ndarray:
        if (
            payload.beta_hat is None
            or payload.compositions is None
            or payload.mu is None
            or payload.debt is None
        ):
            raise ValueError("RAVEN requires compositions, mu, debt, beta_hat")
        n_active = len(payload.client_ids)
        variance = (
            payload.variance_diag
            if payload.variance_diag is not None
            else np.ones(n_active)
        )
        staleness = (
            payload.staleness if payload.staleness is not None else np.zeros(n_active)
        )
        result = solve_p2(
            payload.compositions,
            payload.mu,
            payload.beta_hat,
            payload.debt,
            variance,
            staleness,
            lambda_group=self.lambda_group,
            lambda_beta=self.lambda_beta,
            lambda_variance=self.lambda_variance,
            lambda_staleness=self.lambda_staleness,
            alpha_max=self.alpha_max,
            e_min=min(self.e_min, n_active),
            max_server_learning_rate=self.max_server_learning_rate,
        )
        self.solve_results.append(result)
        return _normalize(result.alpha)


# ---------------------------------------------------------------------------
# 12. RAVEN-SimOracle — RAVEN with oracle q (true usable probabilities)
# ---------------------------------------------------------------------------

class RavenSimOracleAggregator(Aggregator):
    """RAVEN-SimOracle: identical P2 solve as RAVEN-MCS but uses ground-truth
    oracle q values instead of estimated propensities.  This is the
    performance upper-bound / identifiability diagnostic (G7).
    """

    name = "raven_simoracle"

    def __init__(
        self,
        *,
        lambda_group: float = 1.0,
        lambda_beta: float = 1.0,
        lambda_variance: float = 0.1,
        lambda_staleness: float = 0.1,
        alpha_max: float = 0.5,
        e_min: float = 3.0,
        max_server_learning_rate: float = 1.0,
    ) -> None:
        self.lambda_group = lambda_group
        self.lambda_beta = lambda_beta
        self.lambda_variance = lambda_variance
        self.lambda_staleness = lambda_staleness
        self.alpha_max = alpha_max
        self.e_min = e_min
        self.max_server_learning_rate = max_server_learning_rate

    def compute_server_weights(self, payload: WindowAggregateInput) -> np.ndarray:
        if (
            payload.beta_hat is None
            or payload.compositions is None
            or payload.mu is None
            or payload.debt is None
        ):
            raise ValueError("RAVEN-SimOracle requires compositions, mu, debt, beta_hat")
        n_active = len(payload.client_ids)
        variance = (
            payload.variance_diag
            if payload.variance_diag is not None
            else np.ones(n_active)
        )
        staleness = (
            payload.staleness if payload.staleness is not None else np.zeros(n_active)
        )
        result = solve_p2(
            payload.compositions,
            payload.mu,
            payload.beta_hat,
            payload.debt,
            variance,
            staleness,
            lambda_group=self.lambda_group,
            lambda_beta=self.lambda_beta,
            lambda_variance=self.lambda_variance,
            lambda_staleness=self.lambda_staleness,
            alpha_max=self.alpha_max,
            e_min=min(self.e_min, n_active),
            max_server_learning_rate=self.max_server_learning_rate,
        )
        return _normalize(result.alpha)


# ---------------------------------------------------------------------------
# Aggregator registry
# ---------------------------------------------------------------------------

def get_aggregator(name: str) -> Aggregator:
    normalized = name.strip().lower().replace("-", "_")
    mapping: dict[str, type[Aggregator] | Aggregator] = {
        # 1. Central-All
        "central_all": CentralAllAggregator,
        "centralall": CentralAllAggregator,
        # 2. Central-Delivered
        "central_delivered": CentralDeliveredAggregator,
        "centraldelivered": CentralDeliveredAggregator,
        # 3. FedAvg-Window
        "fedavg": FedAvgWindowAggregator,
        "fedavg_window": FedAvgWindowAggregator,
        # 4. FedAsync-Window
        "fedasync": FedAsyncWindowAggregator,
        "fedasync_window": FedAsyncWindowAggregator,
        # 5. TimeAlign-Agg
        "timealign_agg": TimeAlignAggregator,
        "timealign": TimeAlignAggregator,
        "time_align": TimeAlignAggregator,
        "time_align_agg": TimeAlignAggregator,
        # 6. FLAMF-Original
        "flamf_original": FLAMFOriginalAggregator,
        "flamf": FLAMFOriginalAggregator,
        # 7. Local-Hajek
        "local_hajek": LocalHajekAggregator,
        # 8. TwoStage-Hajek
        "twostage_hajek": TwoStageHajekAggregator,
        "two_stage_hajek": TwoStageHajekAggregator,
        # 9. Inst-Cal
        "inst_cal": InstCalAggregator,
        "instant_calibration": InstCalAggregator,
        # 10. Debt-Cal
        "debt_cal": DebtCalAggregator,
        "debt_calibration": DebtCalAggregator,
        # 11. RAVEN-MCS
        "raven": RavenAggregator,
        "raven_mcs": RavenAggregator,
        # 12. RAVEN-SimOracle
        "raven_simoracle": RavenSimOracleAggregator,
        "simoracle": RavenSimOracleAggregator,
    }
    if normalized not in mapping:
        raise KeyError(f"Unknown aggregator: {name} (available: {sorted(set(mapping.keys()))})")
    value = mapping[normalized]
    return value() if isinstance(value, type) else value

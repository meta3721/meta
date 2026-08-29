"""Auditable SAG certificates from completed-window history only (F_{r-}).

v1 models: empirical mean ± one-sided normal SE, and rolling quantiles.
No neural / RL Gate. Coverage target is frozen at 95% (delta_cal=0.05).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Sequence

import numpy as np

Z_ONE_SIDED_95 = 1.6448536269514722


@dataclass(frozen=True)
class FrozenSagThresholds:
    tau_cov: float = 0.05
    tau_ret: float = 0.05
    tau_ESS: float = 1.0
    tau_clip: float = 0.95
    tau_A: float = 0.35
    tau_safe: float = 4.0
    delta_cal: float = 0.05
    lookback_min: int = 8
    lookback_max: int = 32
    quantile_level: float = 0.95
    lambda_group: float = 1.0
    lambda_beta: float = 1.0
    lambda_variance: float = 0.1
    n_groups: int = 4

    def as_dict(self) -> dict[str, float]:
        return asdict(self)

    def gate_thresholds(self) -> dict[str, float]:
        return {
            "tau_cov": float(self.tau_cov),
            "tau_ret": float(self.tau_ret),
            "tau_ESS": float(self.tau_ESS),
            "tau_clip": float(self.tau_clip),
            "tau_A": float(self.tau_A),
            "tau_safe": float(self.tau_safe),
        }


@dataclass
class CertificateBundle:
    C_cov_LCB: float
    C_ret_LCB: float
    C_ESS_LCB: float
    C_clip_UCB: float
    delta_A_UCB: float
    Delta_beta_UCB: float
    Delta_M_UCB: float
    Delta_V_UCB: float
    B_M: float
    B_srv_UCB: float
    delta_cal: float
    B_tot_UCB: float
    n_completed: int
    lookback: int
    cold_start: bool
    missing_certificate: bool

    def as_gate_inputs(self) -> dict[str, Any]:
        return {
            "C_cov_LCB": self.C_cov_LCB,
            "C_ret_LCB": self.C_ret_LCB,
            "C_ESS_LCB": self.C_ESS_LCB,
            "C_clip_UCB": self.C_clip_UCB,
            "delta_A_UCB": self.delta_A_UCB,
            "Delta_beta_UCB": self.Delta_beta_UCB,
            "Delta_M_UCB": self.Delta_M_UCB,
            "Delta_V_UCB": self.Delta_V_UCB,
            "B_srv_UCB": self.B_srv_UCB,
            "delta_cal": self.delta_cal,
            "B_tot_UCB": self.B_tot_UCB,
            "n_completed": self.n_completed,
            "lookback": self.lookback,
            "cold_start": self.cold_start,
            "missing_certificate": self.missing_certificate,
        }


def _finite_list(values: Sequence[Any]) -> list[float]:
    out: list[float] = []
    for item in values:
        try:
            x = float(item)
        except (TypeError, ValueError):
            continue
        if np.isfinite(x):
            out.append(x)
    return out


def mean_lcb(values: Sequence[Any], z: float = Z_ONE_SIDED_95) -> float:
    xs = _finite_list(values)
    if not xs:
        return float("nan")
    arr = np.asarray(xs, dtype=np.float64)
    mean = float(arr.mean())
    if arr.size == 1:
        return mean
    se = float(arr.std(ddof=1) / np.sqrt(arr.size))
    return float(mean - z * se)


def mean_ucb(values: Sequence[Any], z: float = Z_ONE_SIDED_95) -> float:
    xs = _finite_list(values)
    if not xs:
        return float("nan")
    arr = np.asarray(xs, dtype=np.float64)
    mean = float(arr.mean())
    if arr.size == 1:
        return mean
    se = float(arr.std(ddof=1) / np.sqrt(arr.size))
    return float(mean + z * se)


def rolling_quantile(values: Sequence[Any], level: float) -> float:
    xs = _finite_list(values)
    if not xs:
        return float("nan")
    return float(np.quantile(np.asarray(xs, dtype=np.float64), float(level)))


def binary_ucb(values: Sequence[Any], z: float = Z_ONE_SIDED_95) -> float:
    xs = _finite_list(values)
    if not xs:
        return float("nan")
    arr = np.asarray(xs, dtype=np.float64)
    p = float(np.clip(arr.mean(), 0.0, 1.0))
    n = float(arr.size)
    se = float(np.sqrt(p * (1.0 - p) / n))
    return float(min(1.0, p + z * se + 1.0 / n))


def b_tot_from_parts(
    b_srv: float,
    delta_a: float,
    delta_cal: float,
) -> float:
    """B_tot = B_srv + 2 δ_A + 2 δ_cal (Spec v1.2)."""
    return float(b_srv) + 2.0 * float(delta_a) + 2.0 * float(delta_cal)


def compute_certificates(
    history: Sequence[Mapping[str, Any]],
    thresholds: FrozenSagThresholds,
) -> CertificateBundle:
    """Build F_{r-}-measurable certificates from completed windows only."""
    n = len(history)
    lookback = min(int(thresholds.lookback_max), n)
    recent = list(history[-lookback:]) if lookback else []
    cold = n < int(thresholds.lookback_min)
    delta_cal = float(thresholds.delta_cal)

    cov_lcb = mean_lcb([row.get("realized_C_cov") for row in recent])
    ret_lcb = mean_lcb([row.get("realized_C_ret") for row in recent])
    ess_lcb = mean_lcb([row.get("realized_C_ESS") for row in recent])
    clip_ucb = mean_ucb([row.get("realized_C_clip") for row in recent])
    delta_a_ucb = binary_ucb([row.get("active_set_mismatch") for row in recent])
    d_beta = rolling_quantile(
        [row.get("Delta_beta") for row in recent], thresholds.quantile_level,
    )
    d_m = rolling_quantile(
        [row.get("Delta_M") for row in recent], thresholds.quantile_level,
    )
    d_v = rolling_quantile(
        [row.get("Delta_V") for row in recent], thresholds.quantile_level,
    )
    a_sizes = _finite_list([row.get("A_common_size") for row in recent])
    lagged_k = float(np.mean(a_sizes)) if a_sizes else float("nan")
    b_m = float(np.sqrt(max(lagged_k, 1.0))) if np.isfinite(lagged_k) else float("nan")
    n_g = max(int(thresholds.n_groups), 1)
    b_srv = (
        float(np.sqrt(n_g)) * (float(d_m) + b_m * float(d_beta))
        if np.isfinite(d_m) and np.isfinite(d_beta) and np.isfinite(b_m)
        else float("nan")
    )
    b_tot = (
        b_tot_from_parts(b_srv, delta_a_ucb, delta_cal)
        if np.isfinite(b_srv) and np.isfinite(delta_a_ucb)
        else float("nan")
    )
    missing = cold or any(
        not np.isfinite(x)
        for x in (cov_lcb, ret_lcb, ess_lcb, clip_ucb, delta_a_ucb, b_tot)
    )
    return CertificateBundle(
        C_cov_LCB=float(cov_lcb),
        C_ret_LCB=float(ret_lcb),
        C_ESS_LCB=float(ess_lcb),
        C_clip_UCB=float(clip_ucb),
        delta_A_UCB=float(delta_a_ucb),
        Delta_beta_UCB=float(d_beta),
        Delta_M_UCB=float(d_m),
        Delta_V_UCB=float(d_v),
        B_M=float(b_m),
        B_srv_UCB=float(b_srv),
        delta_cal=delta_cal,
        B_tot_UCB=float(b_tot),
        n_completed=n,
        lookback=lookback,
        cold_start=cold,
        missing_certificate=bool(missing),
    )

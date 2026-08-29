"""Binary SAG Gate: fail-closed, no dataset identity, no current-window outcomes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np

FORBIDDEN_GATE_FEATURES = frozenset(
    {
        "dataset_id",
        "current_R",
        "current_O",
        "current_U",
        "Z",
        "label",
        "loss",
        "RMSE",
        "gradient",
        "update_vector",
        "future_state",
    }
)

LEGAL_GATE_FEATURES = (
    "C_cov_LCB",
    "C_ret_LCB",
    "C_ESS_LCB",
    "C_clip_UCB",
    "delta_A_UCB",
    "Delta_beta_UCB",
    "Delta_M_UCB",
    "Delta_V_UCB",
    "B_srv_UCB",
    "delta_cal",
    "B_tot_UCB",
    "n_completed",
    "lookback",
    "cold_start",
    "missing_certificate",
)

FALLBACK_COLD_START = "OFF_COLD_START"
FALLBACK_MISSING = "OFF_MISSING_CERTIFICATE"
FALLBACK_NAN = "OFF_NONFINITE"
FALLBACK_LOW_COVERAGE = "OFF_LOW_COVERAGE"
FALLBACK_LOW_RETENTION = "OFF_LOW_RETENTION"
FALLBACK_LOW_ESS = "OFF_LOW_ESS"
FALLBACK_HIGH_CLIP = "OFF_HIGH_CLIP"
FALLBACK_HIGH_DELTA_A = "OFF_HIGH_DELTA_A"
FALLBACK_HIGH_B_TOT = "OFF_HIGH_B_TOT"


@dataclass(frozen=True)
class GateDecision:
    G_r: int
    fallback_reason: str | None
    features: dict[str, Any]
    passed: dict[str, bool]


def _finite(value: Any) -> bool:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return False
    return bool(np.isfinite(x))


def zeta_tilde(zeta_hat_d: np.ndarray, g_r: int) -> np.ndarray:
    """ζ̃ = 1 + G_r (ζ̂^D − 1). G_r=0 ⇒ ones; G_r=1 ⇒ ζ̂^D."""
    zeta = np.asarray(zeta_hat_d, dtype=np.float64)
    g = int(g_r)
    if g not in (0, 1):
        raise ValueError("G_r must be binary in {0,1}")
    return 1.0 + float(g) * (zeta - 1.0)


def decide_gate(
    certificates: Mapping[str, Any],
    thresholds: Mapping[str, float],
    *,
    fail_closed: bool = True,
) -> GateDecision:
    """G_r=1 iff all six certificate inequalities hold; else 0.

    ``certificates`` must not contain forbidden keys. Dataset name is not an
    argument and must never be passed in.
    """
    illegal = set(certificates).intersection(FORBIDDEN_GATE_FEATURES)
    if illegal:
        raise ValueError(f"forbidden Gate features present: {sorted(illegal)}")

    features = {k: certificates.get(k) for k in LEGAL_GATE_FEATURES if k in certificates}
    cold = bool(certificates.get("cold_start", False))
    missing = bool(certificates.get("missing_certificate", False))
    required = (
        "C_cov_LCB",
        "C_ret_LCB",
        "C_ESS_LCB",
        "C_clip_UCB",
        "delta_A_UCB",
        "B_tot_UCB",
    )
    passed = {name: False for name in required}

    if cold:
        return GateDecision(0, FALLBACK_COLD_START, features, passed)
    if missing:
        return GateDecision(0, FALLBACK_MISSING, features, passed)
    if any(not _finite(certificates.get(name)) for name in required):
        return GateDecision(0, FALLBACK_NAN, features, passed)

    tau_cov = float(thresholds["tau_cov"])
    tau_ret = float(thresholds["tau_ret"])
    tau_ess = float(thresholds["tau_ESS"])
    tau_clip = float(thresholds["tau_clip"])
    tau_a = float(thresholds["tau_A"])
    tau_safe = float(thresholds["tau_safe"])

    cov = float(certificates["C_cov_LCB"])
    ret = float(certificates["C_ret_LCB"])
    ess = float(certificates["C_ESS_LCB"])
    clip = float(certificates["C_clip_UCB"])
    delta_a = float(certificates["delta_A_UCB"])
    b_tot = float(certificates["B_tot_UCB"])

    passed["C_cov_LCB"] = cov >= tau_cov
    passed["C_ret_LCB"] = ret >= tau_ret
    passed["C_ESS_LCB"] = ess >= tau_ess
    passed["C_clip_UCB"] = clip <= tau_clip
    passed["delta_A_UCB"] = delta_a <= tau_a
    passed["B_tot_UCB"] = b_tot <= tau_safe

    if all(passed.values()):
        return GateDecision(1, None, features, passed)
    if not fail_closed:
        return GateDecision(0, FALLBACK_NAN, features, passed)

    if not passed["C_cov_LCB"]:
        reason = FALLBACK_LOW_COVERAGE
    elif not passed["C_ret_LCB"]:
        reason = FALLBACK_LOW_RETENTION
    elif not passed["C_ESS_LCB"]:
        reason = FALLBACK_LOW_ESS
    elif not passed["C_clip_UCB"]:
        reason = FALLBACK_HIGH_CLIP
    elif not passed["delta_A_UCB"]:
        reason = FALLBACK_HIGH_DELTA_A
    else:
        reason = FALLBACK_HIGH_B_TOT
    return GateDecision(0, reason, features, passed)

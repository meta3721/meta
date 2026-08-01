"""Design-ratio ζ̂ (paper F3.1–F3.2)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class ZetaResult:
    zeta_hat: np.ndarray
    pi_hat_opp: np.ndarray
    pi_tar: np.ndarray
    support_flag: np.ndarray  # True where pi_hat_opp > 0
    drift_l1: float  # L1 drift from previous estimate (0 if first estimate)


def zeta_hat_stratum(
    pi_tar: np.ndarray,
    pi_hat_opp: np.ndarray,
    *,
    pi_min: float = 1e-8,
) -> np.ndarray:
    """
    Main within-stratum exchangeable design ratio.

    ζ̂_{k,r,s} = π^tar_{k,s} / max(π̂^opp_{k,s,r}, π_min)
    """
    if pi_min <= 0:
        raise ValueError("pi_min must be positive")
    tar = np.asarray(pi_tar, dtype=np.float64)
    opp = np.asarray(pi_hat_opp, dtype=np.float64)
    if tar.shape != opp.shape:
        raise ValueError("pi_tar and pi_hat_opp must share shape")
    if np.any(tar < 0) or np.any(opp < 0):
        raise ValueError("design-ratio masses must be nonnegative")
    return tar / np.maximum(opp, float(pi_min))


def compute_zeta_with_diagnostics(
    pi_tar: np.ndarray,
    pi_hat_opp: np.ndarray,
    pi_hat_opp_previous: np.ndarray | None = None,
    *,
    pi_min: float = 1e-8,
) -> ZetaResult:
    """Compute zeta_hat with support flags and drift diagnostics.

    Args:
        pi_tar: Target opportunity distribution.
        pi_hat_opp: Current (lagged) estimated opportunity distribution.
        pi_hat_opp_previous: Previous estimate for drift computation.
        pi_min: Minimum denominator value.

    Returns:
        ZetaResult with zeta_hat, support flags, and drift.
    """
    tar = np.asarray(pi_tar, dtype=np.float64)
    opp = np.asarray(pi_hat_opp, dtype=np.float64)

    zeta = tar / np.maximum(opp, float(pi_min))
    support = opp > 0

    drift_l1 = 0.0
    if pi_hat_opp_previous is not None:
        prev = np.asarray(pi_hat_opp_previous, dtype=np.float64)
        drift_l1 = float(np.sum(np.abs(opp - prev)))

    return ZetaResult(
        zeta_hat=zeta,
        pi_hat_opp=opp,
        pi_tar=tar,
        support_flag=support,
        drift_l1=drift_l1,
    )

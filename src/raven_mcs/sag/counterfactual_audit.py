"""Post-window Full-Design vs No-Design audit on a recorded R/O/U window.

Deltas are defined only when A^D = A^0 ≠ ∅.
Both-empty: service_diff = 0 and Delta_beta/M/V = NA (not 0).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from raven_mcs.correction.effective_sample_size import effective_sample_size
from raven_mcs.correction.hajek import (
    composition,
    group_mass,
    raw_weights,
    total_mass,
)
from raven_mcs.correction.second_stage import beta_hat, d_weight, two_stage_mass
from raven_mcs.sag.gate import zeta_tilde


NA = None


@dataclass
class CounterfactualAudit:
    A_D: tuple[str, ...]
    A_0: tuple[str, ...]
    B_D: tuple[str, ...]
    B_0: tuple[str, ...]
    A_D_size: int
    A_0_size: int
    active_set_mismatch: int
    both_empty: int
    service_diff: float | None
    Delta_beta: float | None
    Delta_M: float | None
    Delta_V: float | None
    realized_C_cov: float
    realized_C_ret: float
    realized_C_ESS: float
    realized_C_clip: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "A_D_size": self.A_D_size,
            "A_0_size": self.A_0_size,
            "active_set_mismatch": int(self.active_set_mismatch),
            "both_empty": int(self.both_empty),
            "service_diff": self.service_diff,
            "Delta_beta": self.Delta_beta,
            "Delta_M": self.Delta_M,
            "Delta_V": self.Delta_V,
            "A_common_size": (
                self.A_D_size
                if (not self.active_set_mismatch and not self.both_empty)
                else (0 if self.both_empty else float("nan"))
            ),
            "realized_C_cov": self.realized_C_cov,
            "realized_C_ret": self.realized_C_ret,
            "realized_C_ESS": self.realized_C_ESS,
            "realized_C_clip": self.realized_C_clip,
        }


def _l1_half(a: np.ndarray, b: np.ndarray) -> float:
    x = np.asarray(a, dtype=np.float64).ravel()
    y = np.asarray(b, dtype=np.float64).ravel()
    if x.shape != y.shape:
        n = max(x.size, y.size)
        x = np.pad(x, (0, n - x.size))
        y = np.pad(y, (0, n - y.size))
    return float(0.5 * np.abs(x - y).sum())


def _masses(
    *,
    O: np.ndarray,
    groups: np.ndarray,
    zeta: np.ndarray,
    p_hat: np.ndarray,
    a_max: float,
    p_min: float,
    num_groups: int,
) -> tuple[float, np.ndarray, float, float]:
    a_raw = raw_weights(zeta, p_hat, a_max=a_max, p_min=p_min)
    m_g = group_mass(O, a_raw, groups, n_groups=num_groups)
    m_total = float(total_mass(m_g))
    c_g = composition(m_g, m_total)
    n_eff = float(effective_sample_size(O, a_raw, total_mass=m_total))
    clip = float(np.mean(np.abs(a_raw) >= a_max)) if a_raw.size else 0.0
    return m_total, c_g, n_eff, clip


def _stage2(
    clients: list[str],
    masses: dict[str, float],
    compositions: dict[str, np.ndarray],
    q_hat: dict[str, float],
    variance: dict[str, float],
    *,
    d_max: float,
    q_min: float,
    num_groups: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    n = len(clients)
    if n == 0:
        empty_m = np.zeros(num_groups, dtype=np.float64)
        return np.zeros(0), empty_m, np.zeros(0)
    m = np.array([masses[c] for c in clients], dtype=np.float64)
    q = np.array([q_hat.get(c, 0.5) for c in clients], dtype=np.float64)
    d = d_weight(q, d_max=d_max, q_min=q_min)
    b = two_stage_mass(m, d)
    beta = beta_hat(b)
    mix = np.zeros(num_groups, dtype=np.float64)
    for i, cid in enumerate(clients):
        mix = mix + float(beta[i]) * np.asarray(compositions[cid], dtype=np.float64)
    v = np.array([variance.get(c, 1.0) for c in clients], dtype=np.float64)
    return beta, mix, v


def audit_design_vs_nodesign(
    *,
    registered: list[str],
    attempted: list[str],
    usable: dict[str, int],
    O: dict[str, np.ndarray],
    groups: dict[str, np.ndarray],
    zeta_d: dict[str, np.ndarray],
    p_hat: dict[str, np.ndarray],
    q_hat: dict[str, float],
    variance: dict[str, float],
    target_positive_count: int,
    target_covered_count: int,
    a_max: float,
    p_min: float,
    d_max: float,
    q_min: float,
    num_groups: int,
) -> CounterfactualAudit:
    """Reconstruct B/A and (when defined) Δβ/M/V on frozen p̂, q̂, O, U."""
    b_d: list[str] = []
    b_0: list[str] = []
    masses_d: dict[str, float] = {}
    masses_0: dict[str, float] = {}
    comp_d: dict[str, np.ndarray] = {}
    comp_0: dict[str, np.ndarray] = {}
    n_effs: list[float] = []
    clips: list[float] = []

    for cid in registered:
        if cid not in attempted:
            continue
        rec_o = np.asarray(O[cid], dtype=np.float64)
        rec_g = np.asarray(groups[cid], dtype=np.int64)
        zd = np.asarray(zeta_d[cid], dtype=np.float64)
        ph = np.asarray(p_hat[cid], dtype=np.float64)
        z0 = zeta_tilde(zd, 0)
        m_d, c_d, n_d, clip_d = _masses(
            O=rec_o, groups=rec_g, zeta=zd, p_hat=ph,
            a_max=a_max, p_min=p_min, num_groups=num_groups,
        )
        m_0, c_0, n_0, clip_0 = _masses(
            O=rec_o, groups=rec_g, zeta=z0, p_hat=ph,
            a_max=a_max, p_min=p_min, num_groups=num_groups,
        )
        masses_d[cid] = m_d
        masses_0[cid] = m_0
        comp_d[cid] = c_d
        comp_0[cid] = c_0
        n_effs.extend([n_d, n_0])
        clips.extend([clip_d, clip_0])
        if m_d > 0:
            b_d.append(cid)
        if m_0 > 0:
            b_0.append(cid)

    u_set = {cid for cid, u in usable.items() if int(u) == 1}
    a_d = tuple(sorted(cid for cid in b_d if cid in u_set))
    a_0 = tuple(sorted(cid for cid in b_0 if cid in u_set))
    mismatch = int(a_d != a_0)
    both_empty = int(len(a_d) == 0 and len(a_0) == 0)

    delta_beta: float | None = NA
    delta_m: float | None = NA
    delta_v: float | None = NA
    service_diff: float | None
    if both_empty:
        service_diff = 0.0
    elif mismatch:
        service_diff = NA
    else:
        beta_d, mix_d, v_d = _stage2(
            list(a_d), masses_d, comp_d, q_hat, variance,
            d_max=d_max, q_min=q_min, num_groups=num_groups,
        )
        beta_0, mix_0, v_0 = _stage2(
            list(a_0), masses_0, comp_0, q_hat, variance,
            d_max=d_max, q_min=q_min, num_groups=num_groups,
        )
        delta_beta = _l1_half(beta_d, beta_0)
        delta_m = _l1_half(mix_d, mix_0)
        delta_v = _l1_half(v_d, v_0)
        service_diff = float(delta_m)

    denom = max(int(target_positive_count), 1)
    realized_cov = float(target_covered_count) / float(denom)
    b_union = set(b_d) | set(b_0)
    if b_union:
        realized_ret = float(len(set(a_d) | set(a_0))) / float(len(b_union))
    else:
        realized_ret = 0.0
    realized_ess = float(np.mean(n_effs)) if n_effs else 0.0
    realized_clip = float(np.mean(clips)) if clips else 0.0

    return CounterfactualAudit(
        A_D=a_d,
        A_0=a_0,
        B_D=tuple(sorted(b_d)),
        B_0=tuple(sorted(b_0)),
        A_D_size=len(a_d),
        A_0_size=len(a_0),
        active_set_mismatch=mismatch,
        both_empty=both_empty,
        service_diff=service_diff,
        Delta_beta=delta_beta,
        Delta_M=delta_m,
        Delta_V=delta_v,
        realized_C_cov=realized_cov,
        realized_C_ret=realized_ret,
        realized_C_ESS=realized_ess,
        realized_C_clip=realized_clip,
    )

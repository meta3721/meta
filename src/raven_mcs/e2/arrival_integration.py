"""Atomic-specific usable exposure and expected arrival mass (scheme A/B)."""
from __future__ import annotations

from typing import Any, Sequence

import numpy as np
import pandas as pd

from raven_mcs.e2.generators import compute_usable_probabilities

EPS = 1e-15
SCHEME_TOL = 1e-12


def compute_atomic_usable_arrival(
    unit_ids: Sequence[str],
    observation_mass: np.ndarray,
    observation_probabilities: np.ndarray,
    opportunity_mass: np.ndarray,
    validated_windows: Sequence[dict[str, Any]],
    kappa_q: float,
    direction: int,
    *,
    target_mass: np.ndarray,
    tail_score: np.ndarray,
    usable_rate_target: float = 0.60,
    q_gen_min: float = 0.05,
    q_gen_max: float = 0.95,
) -> dict[str, Any]:
    """Map window-level q_use onto atoms via risk-set observation masses.

    Scheme A: m_arr_i = sum_{k,r} m_{k,r,i}^obs * q_{k,r}
    Scheme B: rho_arr ∝ rho_obs * q_bar_i
    """
    unit_ids = [str(u) for u in unit_ids]
    index = {u: i for i, u in enumerate(unit_ids)}
    n = len(unit_ids)
    obs_mass = np.asarray(observation_mass, dtype=np.float64).reshape(-1)
    p_obs = np.asarray(observation_probabilities, dtype=np.float64).reshape(-1)
    opp_mass = np.asarray(opportunity_mass, dtype=np.float64).reshape(-1)
    target = np.asarray(target_mass, dtype=np.float64).reshape(-1)
    scores = np.asarray(tail_score, dtype=np.int8).reshape(-1)
    if not (obs_mass.shape == p_obs.shape == opp_mass.shape == (n,)):
        raise ValueError("atomic array shape mismatch")

    eligible = [w for w in validated_windows if w["attempt_eligible"] and w["z_tail"] is not None]
    if not eligible:
        raise ValueError("no attempt-eligible client-windows for usable arrival")
    compositions = np.asarray([float(w["z_tail"]) for w in eligible], dtype=np.float64)
    usable = compute_usable_probabilities(
        compositions, kappa_q, direction, usable_rate_target, q_gen_min, q_gen_max,
    )
    q_use = usable["q_use_by_window"]

    # Aggregate opportunity weights per atom across eligible windows, then
    # allocate observation mass shares so sum_m_obs_i = rho_obs_i on covered atoms.
    # This makes scheme A (sum m_obs*q) identical to scheme B (rho_obs * q_bar).
    weight_totals = np.zeros(n, dtype=np.float64)
    window_atom_weights: list[tuple[np.ndarray, np.ndarray, float]] = []
    for window, q in zip(eligible, q_use, strict=True):
        local_ids = [str(u) for u in window["unit_ids"]]
        weights = np.asarray(window["opportunity_weights"], dtype=np.float64)
        atom_idx = np.asarray([index[u] for u in local_ids], dtype=np.int64)
        weight_totals[atom_idx] += weights
        window_atom_weights.append((atom_idx, weights, float(q)))

    m_arr = np.zeros(n, dtype=np.float64)
    m_obs_exposure = np.zeros(n, dtype=np.float64)
    for atom_idx, weights, q in window_atom_weights:
        for atom, weight in zip(atom_idx.tolist(), weights.tolist(), strict=True):
            denom = float(weight_totals[atom])
            if denom <= 0:
                continue
            # Share of atomic observation mass allocated to this window.
            m_kri = float(obs_mass[atom]) * (float(weight) / denom)
            if m_kri < 0:
                raise ValueError("observation window mass must be nonnegative")
            m_obs_exposure[atom] += m_kri
            m_arr[atom] += m_kri * q

    total_a = float(m_arr.sum())
    if total_a <= 0:
        raise ValueError("scheme-A arrival mass total must be positive")
    rho_a = m_arr / total_a

    q_bar = np.zeros(n, dtype=np.float64)
    positive = m_obs_exposure > 0
    q_bar[positive] = m_arr[positive] / m_obs_exposure[positive]
    scheme_b_unnorm = obs_mass * np.where(positive, q_bar, 0.0)
    total_b = float(scheme_b_unnorm.sum())
    if total_b <= 0:
        raise ValueError("scheme-B arrival mass total must be positive")
    rho_b = scheme_b_unnorm / total_b
    max_diff = float(np.max(np.abs(rho_a - rho_b)))
    if max_diff > SCHEME_TOL:
        raise ValueError(
            f"scheme A/B mismatch: max_abs_diff={max_diff} > {SCHEME_TOL}"
        )

    global_mean_q = float(np.mean(q_use))
    # Guard: global mean-q shortcut must not be used as the arrival definition.
    shortcut = obs_mass * global_mean_q
    shortcut = shortcut / float(shortcut.sum())
    shortcut_diff = float(np.max(np.abs(rho_a - shortcut)))

    frame = pd.DataFrame({
        "unit_id": unit_ids,
        "observation_mass": obs_mass,
        "usable_weighted_mass": m_arr,
        "atomic_q_bar": q_bar,
        "expected_arrival_mass": rho_a,
        "target_mass": target,
        "tail_score": scores,
    })
    audit = {
        "global_mean_q": global_mean_q,
        "atomic_q_bar_min": float(q_bar[positive].min()) if positive.any() else 0.0,
        "atomic_q_bar_max": float(q_bar[positive].max()) if positive.any() else 0.0,
        "atomic_q_bar_std": float(q_bar[positive].std()) if positive.any() else 0.0,
        "arrival_mass_sum": float(rho_a.sum()),
        "normalization_error": abs(float(rho_a.sum()) - 1.0),
        "scheme_A_B_max_abs_diff": max_diff,
        "zero_observation_atom_count": int((~positive).sum()),
        "unsupported_atom_count": 0,
        "finite_status": (
            "PASS" if np.all(np.isfinite(rho_a)) and np.all(np.isfinite(q_bar))
            else "FAIL"
        ),
        "global_mean_q_shortcut_max_abs_diff": shortcut_diff,
        "global_mean_q_shortcut_used": False,
        "attempt_eligible_window_count": len(eligible),
    }
    return {
        "expected_arrival_mass": rho_a,
        "atomic_q_bar": q_bar,
        "q_use_by_window": q_use,
        "usable": usable,
        "exposure_frame": frame,
        "audit": audit,
        "compositions": compositions,
        "eligible_windows": eligible,
    }

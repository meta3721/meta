"""Opportunity, observation, and usable numeric generators for E2."""
from __future__ import annotations

from typing import Any, Mapping

import numpy as np

EPS = 1e-15
ROOT_TOL = 1e-12
RATE_TOL = 1e-10
MAX_ROOT_ITERS = 80


def _as_vector(values: np.ndarray | list[float], name: str) -> np.ndarray:
    arr = np.asarray(values, dtype=np.float64).reshape(-1)
    if arr.size == 0:
        raise ValueError(f"{name} must be nonempty")
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"{name} contains non-finite values")
    return arr


def _sigmoid(x: np.ndarray | float) -> np.ndarray:
    z = np.asarray(x, dtype=np.float64)
    return 1.0 / (1.0 + np.exp(-np.clip(z, -60.0, 60.0)))


def _tv(a: np.ndarray, b: np.ndarray) -> float:
    return float(0.5 * np.sum(np.abs(a - b)))


def _mass_ratios(
    mass: np.ndarray,
    tail_score: np.ndarray,
) -> tuple[float, float]:
    head = float(mass[tail_score == -1].sum())
    tail = float(mass[tail_score == 1].sum())
    return head, tail


def build_atomic_tail_score(
    head_tail_mapping: Mapping[str, Any] | np.ndarray,
    supported_units: np.ndarray | None = None,
) -> np.ndarray:
    if isinstance(head_tail_mapping, np.ndarray):
        scores = np.asarray(head_tail_mapping, dtype=np.int8).reshape(-1)
    else:
        frame = head_tail_mapping  # pandas-like
        scores = np.asarray(frame["tail_score"], dtype=np.int8)
        if supported_units is not None:
            order = {str(u): i for i, u in enumerate(frame["unit_id"].astype(str))}
            scores = np.asarray(
                [scores[order[str(u)]] for u in supported_units], dtype=np.int8
            )
    if set(np.unique(scores)) - {-1, 0, 1}:
        raise ValueError("tail scores must be in {-1,0,+1}")
    return scores


def compute_opportunity_mass(
    target_mass: np.ndarray,
    tail_score: np.ndarray,
    kappa_opp: float,
    direction: int,
) -> dict[str, Any]:
    target = _as_vector(target_mass, "target_mass")
    scores = np.asarray(tail_score, dtype=np.float64).reshape(-1)
    if target.shape != scores.shape:
        raise ValueError("target_mass and tail_score shape mismatch")
    if float(kappa_opp) < 0:
        raise ValueError("kappa_opp must be nonnegative")
    if int(direction) not in {-1, 0, 1}:
        raise ValueError("direction must be in {-1,0,+1}")
    if abs(float(target.sum()) - 1.0) > 1e-12:
        raise ValueError("target_mass must sum to one")
    if np.any(target < 0):
        raise ValueError("target_mass must be nonnegative")

    factor = np.exp(float(direction) * float(kappa_opp) * scores)
    unnormalized = target * factor
    normalizer = float(unnormalized.sum())
    if normalizer <= 0:
        raise ValueError("opportunity normalization constant must be positive")
    mass = unnormalized / normalizer
    if abs(float(mass.sum()) - 1.0) > 1e-12:
        raise ValueError("opportunity mass failed normalization")
    if np.any(mass[target > 0] <= 0):
        raise ValueError("supported atoms must remain strictly positive")
    head_ratio = float(mass[scores == -1].sum() / max(target[scores == -1].sum(), EPS))
    tail_ratio = float(mass[scores == 1].sum() / max(target[scores == 1].sum(), EPS))
    return {
        "opportunity_mass": mass,
        "opportunity_factor": factor,
        "normalization_constant": normalizer,
        "total_variation_to_target": _tv(mass, target),
        "head_mass_ratio": head_ratio,
        "tail_mass_ratio": tail_ratio,
    }


def solve_observation_intercept(
    opportunity_mass: np.ndarray,
    tail_score: np.ndarray,
    kappa_p: float,
    direction: int,
    observation_rate_target: float = 0.20,
    p_gen_min: float = 0.05,
    p_gen_max: float = 0.95,
) -> float:
    mass = _as_vector(opportunity_mass, "opportunity_mass")
    scores = np.asarray(tail_score, dtype=np.float64).reshape(-1)
    if mass.shape != scores.shape:
        raise ValueError("opportunity_mass/tail_score mismatch")
    if not (0.0 < observation_rate_target < 1.0):
        raise ValueError("observation_rate_target out of range")
    if not (0.0 < p_gen_min < p_gen_max < 1.0):
        raise ValueError("invalid observation probability bounds")

    def expected_rate(intercept: float) -> float:
        logits = intercept + float(direction) * float(kappa_p) * scores
        probs = np.clip(_sigmoid(logits), p_gen_min, p_gen_max)
        return float(np.sum(mass * probs))

    lo, hi = -40.0, 40.0
    f_lo, f_hi = expected_rate(lo), expected_rate(hi)
    if not (f_lo <= observation_rate_target <= f_hi):
        raise ValueError(
            f"infeasible observation_rate_target={observation_rate_target}; "
            f"attainable=[{f_lo:.12f},{f_hi:.12f}]"
        )
    for _ in range(MAX_ROOT_ITERS):
        mid = 0.5 * (lo + hi)
        value = expected_rate(mid)
        if abs(value - observation_rate_target) <= ROOT_TOL:
            return float(mid)
        if value < observation_rate_target:
            lo = mid
        else:
            hi = mid
    mid = 0.5 * (lo + hi)
    if abs(expected_rate(mid) - observation_rate_target) > RATE_TOL:
        raise ValueError("observation intercept root failed tolerance")
    return float(mid)


def compute_observation_probabilities(
    opportunity_mass: np.ndarray,
    tail_score: np.ndarray,
    kappa_p: float,
    direction: int,
    observation_rate_target: float = 0.20,
    p_gen_min: float = 0.05,
    p_gen_max: float = 0.95,
) -> dict[str, Any]:
    mass = _as_vector(opportunity_mass, "opportunity_mass")
    scores = np.asarray(tail_score, dtype=np.float64).reshape(-1)
    intercept = solve_observation_intercept(
        mass, scores, kappa_p, direction,
        observation_rate_target, p_gen_min, p_gen_max,
    )
    logits = intercept + float(direction) * float(kappa_p) * scores
    p_obs = np.clip(_sigmoid(logits), p_gen_min, p_gen_max)
    realized = float(np.sum(mass * p_obs))
    if abs(realized - observation_rate_target) > RATE_TOL:
        raise ValueError(
            f"observation rate miss: realized={realized}, target={observation_rate_target}"
        )
    obs_unnorm = mass * p_obs
    obs_total = float(obs_unnorm.sum())
    if obs_total <= 0:
        raise ValueError("observation mass total must be positive")
    obs_mass = obs_unnorm / obs_total
    target_like = mass  # diagnostics relative to opportunity mass when needed
    head_ratio = float(obs_mass[scores == -1].sum() / max(mass[scores == -1].sum(), EPS))
    tail_ratio = float(obs_mass[scores == 1].sum() / max(mass[scores == 1].sum(), EPS))
    return {
        "p_obs_by_atom": p_obs,
        "observation_intercept": intercept,
        "realized_expected_observation_rate": realized,
        "observation_mass": obs_mass,
        "total_variation_to_target": _tv(obs_mass, target_like),
        "head_mass_ratio": head_ratio,
        "tail_mass_ratio": tail_ratio,
    }


def compute_client_window_tail_composition(
    risk_set_weights: np.ndarray,
    tail_score: np.ndarray,
) -> float:
    """risk_set_weights are nu^opp over atoms in the risk set; must sum to 1."""
    weights = _as_vector(risk_set_weights, "risk_set_weights")
    scores = np.asarray(tail_score, dtype=np.float64).reshape(-1)
    if weights.shape != scores.shape:
        raise ValueError("risk_set_weights/tail_score mismatch")
    if weights.size == 0:
        return 0.0
    if abs(float(weights.sum()) - 1.0) > 1e-12:
        raise ValueError("risk-set opportunity weights must sum to one")
    if np.any(weights < 0):
        raise ValueError("risk-set weights must be nonnegative")
    z = float(np.sum(weights * (scores == 1)) - np.sum(weights * (scores == -1)))
    if z < -1.0 - 1e-12 or z > 1.0 + 1e-12:
        raise ValueError("tail composition outside [-1,1]")
    return float(np.clip(z, -1.0, 1.0))


def solve_usable_intercept(
    compositions: np.ndarray,
    kappa_q: float,
    direction: int,
    usable_rate_target: float = 0.60,
    q_gen_min: float = 0.05,
    q_gen_max: float = 0.95,
) -> float:
    z = _as_vector(compositions, "compositions")
    if z.size == 0:
        raise ValueError("no attempt-eligible client-windows for usable intercept")
    if not (0.0 < usable_rate_target < 1.0):
        raise ValueError("usable_rate_target out of range")

    def expected_rate(intercept: float) -> float:
        logits = intercept + float(direction) * float(kappa_q) * z
        probs = np.clip(_sigmoid(logits), q_gen_min, q_gen_max)
        return float(np.mean(probs))

    lo, hi = -40.0, 40.0
    f_lo, f_hi = expected_rate(lo), expected_rate(hi)
    if not (f_lo <= usable_rate_target <= f_hi):
        raise ValueError(
            f"infeasible usable_rate_target={usable_rate_target}; "
            f"attainable=[{f_lo:.12f},{f_hi:.12f}]"
        )
    for _ in range(MAX_ROOT_ITERS):
        mid = 0.5 * (lo + hi)
        value = expected_rate(mid)
        if abs(value - usable_rate_target) <= ROOT_TOL:
            return float(mid)
        if value < usable_rate_target:
            lo = mid
        else:
            hi = mid
    mid = 0.5 * (lo + hi)
    if abs(expected_rate(mid) - usable_rate_target) > RATE_TOL:
        raise ValueError("usable intercept root failed tolerance")
    return float(mid)


def compute_usable_probabilities(
    compositions: np.ndarray,
    kappa_q: float,
    direction: int,
    usable_rate_target: float = 0.60,
    q_gen_min: float = 0.05,
    q_gen_max: float = 0.95,
) -> dict[str, Any]:
    z = _as_vector(compositions, "compositions")
    intercept = solve_usable_intercept(
        z, kappa_q, direction, usable_rate_target, q_gen_min, q_gen_max,
    )
    logits = intercept + float(direction) * float(kappa_q) * z
    q_use = np.clip(_sigmoid(logits), q_gen_min, q_gen_max)
    realized = float(np.mean(q_use))
    if abs(realized - usable_rate_target) > RATE_TOL:
        raise ValueError(
            f"usable rate miss: realized={realized}, target={usable_rate_target}"
        )
    return {
        "q_use_by_window": q_use,
        "usable_intercept": intercept,
        "realized_expected_usable_rate": realized,
        "feature_names": ["pre_outcome_tail_composition_z"],
        "forbidden_features_used": [],
    }

"""Static mass diagnostics for E2 numeric scenarios (no seed execution)."""
from __future__ import annotations

from typing import Any, Mapping

import numpy as np


def compute_e2_mass_diagnostics(
    target_mass: np.ndarray,
    opportunity_mass: np.ndarray,
    observation_mass: np.ndarray,
    expected_arrival_mass: np.ndarray,
    tail_score: np.ndarray,
    expected_observation_rate: float,
    expected_usable_rate: float,
) -> dict[str, Any]:
    target = np.asarray(target_mass, dtype=np.float64)
    opp = np.asarray(opportunity_mass, dtype=np.float64)
    obs = np.asarray(observation_mass, dtype=np.float64)
    arr = np.asarray(expected_arrival_mass, dtype=np.float64)
    scores = np.asarray(tail_score, dtype=np.int8)

    def tv(a: np.ndarray, b: np.ndarray) -> float:
        return float(0.5 * np.sum(np.abs(a - b)))

    arrays = [target, opp, obs, arr]
    finite = all(np.all(np.isfinite(a)) for a in arrays)
    support = bool(np.all(arr[target > 0] > 0) and np.all(target >= 0))
    return {
        "D_TV_opp": tv(opp, target),
        "D_TV_obs": tv(obs, target),
        "D_TV_arr_expected": tv(arr, target),
        "head_mass_target": float(target[scores == -1].sum()),
        "tail_mass_target": float(target[scores == 1].sum()),
        "head_mass_opp": float(opp[scores == -1].sum()),
        "tail_mass_opp": float(opp[scores == 1].sum()),
        "head_mass_obs": float(obs[scores == -1].sum()),
        "tail_mass_obs": float(obs[scores == 1].sum()),
        "expected_observation_rate": float(expected_observation_rate),
        "expected_usable_rate": float(expected_usable_rate),
        "min_supported_mass": float(arr[target > 0].min()) if support else 0.0,
        "max_supported_mass": float(arr.max()),
        "finite_status": "PASS" if finite else "FAIL",
        "support_status": "PASS" if support else "FAIL",
    }

"""Unified E2 numeric scenario generator."""
from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import yaml

from raven_mcs.e2.generators import (
    compute_client_window_tail_composition,
    compute_observation_probabilities,
    compute_opportunity_mass,
    compute_usable_probabilities,
)
from raven_mcs.e2.identity import (
    load_e1_atomic_target_weights,
    load_e1_head_tail_mapping,
    load_e1_target_identity,
    reject_uniform_target_fallback,
)
from raven_mcs.utils.hashing import sha256_json

ROOT = Path(__file__).resolve().parents[3]
FORBIDDEN_KWARGS = {
    "labels", "predictions", "errors", "model", "formal_outcomes",
    "y_true", "y_pred", "test_error",
}


def load_scenario_direction_registry(root: Path | None = None) -> dict[str, Any]:
    root = Path(root or ROOT)
    path = root / "configs/e2_numeric/scenario_direction_registry.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return payload


def load_strength_profile_registry(root: Path | None = None) -> dict[str, Any]:
    root = Path(root or ROOT)
    path = root / "configs/e2_numeric/strength_profile_registry.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def generate_e2_numeric_scenario(
    target_identity: Mapping[str, Any] | None = None,
    scenario_id: str = "balanced",
    strength_profile: str | Mapping[str, float] = "PROFILE-S2",
    client_window_risk_sets: Sequence[Mapping[str, Any]] | None = None,
    *,
    root: Path | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Generate deterministic numeric scenario masses/probabilities.

    Signature intentionally excludes outcome/model inputs.
    """
    bad = FORBIDDEN_KWARGS.intersection(kwargs)
    if bad:
        raise TypeError(f"outcome/model inputs are forbidden: {sorted(bad)}")
    if kwargs:
        raise TypeError(f"unexpected keyword arguments: {sorted(kwargs)}")

    root = Path(root or ROOT)
    identity = dict(target_identity or load_e1_target_identity(root))
    if identity.get("uniform_target_fallback") != "FORBIDDEN":
        raise RuntimeError("uniform target fallback must remain FORBIDDEN")
    # Reject only if a caller tries to activate the deprecated uniform placeholder.
    reject_uniform_target_fallback(identity.get("target_distribution"))
    reject_uniform_target_fallback(identity.get("active_target_distribution"))

    atomic = load_e1_atomic_target_weights(root)
    head_tail = load_e1_head_tail_mapping(root)
    unit_ids = atomic["unit_id"].astype(str).tolist()
    target_mass = atomic["target_weight"].to_numpy(dtype=np.float64)
    tail_score = (
        head_tail.set_index("unit_id").loc[unit_ids, "tail_score"].to_numpy(dtype=np.int8)
    )

    directions = load_scenario_direction_registry(root)["scenarios"]
    if scenario_id not in directions:
        raise KeyError(f"unknown scenario_id: {scenario_id}")
    scenario = directions[scenario_id]
    d_opp = int(scenario["d_opp"])
    d_p = int(scenario["d_p"])
    d_q = int(scenario["d_q"])

    if isinstance(strength_profile, str):
        profiles = load_strength_profile_registry(root)["profiles"]
        if strength_profile not in profiles:
            raise KeyError(f"unknown strength profile: {strength_profile}")
        profile = profiles[strength_profile]
        profile_id = strength_profile
    else:
        profile = dict(strength_profile)
        profile_id = "inline"
    kappa_opp = float(profile["kappa_opp"])
    kappa_p = float(profile["kappa_p"])
    kappa_q = float(profile["kappa_q"])

    opp = compute_opportunity_mass(target_mass, tail_score, kappa_opp, d_opp)
    # Single-stage semantics: inactive stages use zero strength.
    kappa_p_eff = kappa_p if "observation" in scenario["enabled_stages"] or d_p != 0 else 0.0
    kappa_q_eff = kappa_q if "usable" in scenario["enabled_stages"] or d_q != 0 else 0.0
    # For opportunity-only, observation/usable directions are zero so kappa is irrelevant.
    obs = compute_observation_probabilities(
        opp["opportunity_mass"], tail_score, kappa_p_eff, d_p,
    )

    if client_window_risk_sets is None:
        # Deterministic synthetic attempt-eligible windows for generator tests:
        # one uniform risk set over all atoms; no training/outcomes.
        compositions = np.asarray([
            compute_client_window_tail_composition(
                opp["opportunity_mass"], tail_score,
            )
        ], dtype=np.float64)
    else:
        compositions = []
        for item in client_window_risk_sets:
            weights = np.asarray(item["nu_opp"], dtype=np.float64)
            scores = np.asarray(item.get("tail_score", tail_score), dtype=np.float64)
            compositions.append(
                compute_client_window_tail_composition(weights, scores)
            )
        compositions = np.asarray(compositions, dtype=np.float64)

    usable = compute_usable_probabilities(compositions, kappa_q_eff, d_q)
    # Expected arrival mass ≈ observation mass reweighted by mean usable propensity
    # conditional on atom appearance. Without client topology, use global mean q.
    mean_q = float(np.mean(usable["q_use_by_window"]))
    arr_unnorm = obs["observation_mass"] * mean_q
    arr_total = float(arr_unnorm.sum())
    expected_arrival = arr_unnorm / arr_total

    payload = {
        "scenario_id": scenario_id,
        "strength_profile_id": profile_id,
        "directions": {"d_opp": d_opp, "d_p": d_p, "d_q": d_q},
        "kappas": {
            "kappa_opp": kappa_opp, "kappa_p": kappa_p_eff, "kappa_q": kappa_q_eff,
        },
        "unit_ids": unit_ids,
        "target_mass": target_mass,
        "tail_score": tail_score,
        "opportunity_mass": opp["opportunity_mass"],
        "observation_probabilities": obs["p_obs_by_atom"],
        "observation_mass": obs["observation_mass"],
        "client_window_tail_composition": compositions,
        "usable_probabilities": usable["q_use_by_window"],
        "expected_arrival_mass": expected_arrival,
        "diagnostics": {
            "opportunity": {
                "total_variation_to_target": opp["total_variation_to_target"],
                "head_mass_ratio": opp["head_mass_ratio"],
                "tail_mass_ratio": opp["tail_mass_ratio"],
            },
            "observation": {
                "realized_expected_observation_rate": obs[
                    "realized_expected_observation_rate"
                ],
                "observation_intercept": obs["observation_intercept"],
                "total_variation_to_opportunity": obs["total_variation_to_target"],
                "head_mass_ratio": obs["head_mass_ratio"],
                "tail_mass_ratio": obs["tail_mass_ratio"],
            },
            "usable": {
                "realized_expected_usable_rate": usable[
                    "realized_expected_usable_rate"
                ],
                "usable_intercept": usable["usable_intercept"],
                "feature_names": usable["feature_names"],
            },
        },
        "provenance": {
            "atomic_target_weight_hash": identity["atomic_target_weight_hash"],
            "head_tail_mapping_hash": identity["head_tail_mapping_hash"],
            "supported_test_unit_hash": identity["supported_test_unit_hash"],
            "generator": "raven_mcs.e2.scenario_generator.generate_e2_numeric_scenario",
            "signature": str(inspect.signature(generate_e2_numeric_scenario)),
        },
    }
    hashable = {
        "scenario_id": scenario_id,
        "profile_id": profile_id,
        "directions": payload["directions"],
        "kappas": payload["kappas"],
        "target_mass": target_mass.tolist(),
        "opportunity_mass": payload["opportunity_mass"].tolist(),
        "observation_probabilities": payload["observation_probabilities"].tolist(),
        "expected_arrival_mass": expected_arrival.tolist(),
        "compositions": compositions.tolist(),
        "usable_probabilities": payload["usable_probabilities"].tolist(),
    }
    payload["payload_sha256"] = sha256_json(hashable)
    return payload

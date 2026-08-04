"""Unified E2 numeric scenario generator with atomic usable arrival wiring."""
from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import yaml

from raven_mcs.e2.arrival_integration import compute_atomic_usable_arrival
from raven_mcs.e2.client_windows import build_client_window_compositions
from raven_mcs.e2.diagnostics import compute_e2_mass_diagnostics
from raven_mcs.e2.generators import (
    compute_observation_probabilities,
    compute_opportunity_mass,
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
    "y_true", "y_pred", "test_error", "tail_score", "tail_scores",
}
TOPOLOGY_PATH = ROOT / "tests/fixtures/e2_usable_topology.json"


def load_scenario_direction_registry(root: Path | None = None) -> dict[str, Any]:
    root = Path(root or ROOT)
    path = root / "configs/e2_numeric/scenario_direction_registry.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_strength_profile_registry(root: Path | None = None) -> dict[str, Any]:
    root = Path(root or ROOT)
    path = root / "configs/e2_numeric/strength_profile_registry.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_usable_topology(root: Path | None = None) -> list[dict[str, Any]]:
    root = Path(root or ROOT)
    path = root / "tests/fixtures/e2_usable_topology.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return list(payload["windows"])


def _mass_ratios(mass: np.ndarray, scores: np.ndarray) -> tuple[float, float]:
    head = float(mass[scores == -1].sum())
    tail = float(mass[scores == 1].sum())
    return head, tail


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

    Signature intentionally excludes outcome/model inputs and caller tail scores.
    """
    bad = FORBIDDEN_KWARGS.intersection(kwargs)
    if bad:
        raise TypeError(f"forbidden keyword arguments: {sorted(bad)}")
    if kwargs:
        raise TypeError(f"unexpected keyword arguments: {sorted(kwargs)}")

    root = Path(root or ROOT)
    identity = dict(target_identity or load_e1_target_identity(root))
    if identity.get("uniform_target_fallback") != "FORBIDDEN":
        raise RuntimeError("uniform target fallback must remain FORBIDDEN")
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
    kappa_p_eff = kappa_p if ("observation" in scenario["enabled_stages"] or d_p != 0) else 0.0
    kappa_q_eff = kappa_q if ("usable" in scenario["enabled_stages"] or d_q != 0) else 0.0
    obs = compute_observation_probabilities(
        opp["opportunity_mass"], tail_score, kappa_p_eff, d_p,
    )

    records = (
        list(client_window_risk_sets)
        if client_window_risk_sets is not None
        else load_usable_topology(root)
    )
    validated, composition_frame = build_client_window_compositions(records, root=root)
    arrival = compute_atomic_usable_arrival(
        unit_ids=unit_ids,
        observation_mass=obs["observation_mass"],
        observation_probabilities=obs["p_obs_by_atom"],
        opportunity_mass=opp["opportunity_mass"],
        validated_windows=validated,
        kappa_q=kappa_q_eff,
        direction=d_q,
        target_mass=target_mass,
        tail_score=tail_score,
    )
    expected_arrival = arrival["expected_arrival_mass"]
    head_arr, tail_arr = _mass_ratios(expected_arrival, tail_score)
    head_obs, tail_obs = _mass_ratios(obs["observation_mass"], tail_score)
    head_tgt = float(target_mass[tail_score == -1].sum())
    tail_tgt = float(target_mass[tail_score == 1].sum())

    mass_diag = compute_e2_mass_diagnostics(
        target_mass,
        opp["opportunity_mass"],
        obs["observation_mass"],
        expected_arrival,
        tail_score,
        obs["realized_expected_observation_rate"],
        arrival["usable"]["realized_expected_usable_rate"],
    )

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
        "client_window_tail_composition": arrival["compositions"],
        "client_window_composition_frame": composition_frame,
        "usable_probabilities": arrival["q_use_by_window"],
        "atomic_q_bar": arrival["atomic_q_bar"],
        "expected_arrival_mass": expected_arrival,
        "usable_arrival_audit": arrival["audit"],
        "atomic_usable_exposure": arrival["exposure_frame"],
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
                "head_mass": head_obs,
                "tail_mass": tail_obs,
            },
            "usable": {
                "realized_expected_usable_rate": arrival["usable"][
                    "realized_expected_usable_rate"
                ],
                "usable_intercept": arrival["usable"]["usable_intercept"],
                "feature_names": arrival["usable"]["feature_names"],
                "head_mass_ratio": head_arr / max(head_tgt, 1e-15),
                "tail_mass_ratio": tail_arr / max(tail_tgt, 1e-15),
                "head_mass": head_arr,
                "tail_mass": tail_arr,
                "tail_ratio_vs_obs": tail_arr / max(tail_obs, 1e-15),
            },
            "mass": mass_diag,
        },
        "provenance": {
            "atomic_target_weight_hash": identity["atomic_target_weight_hash"],
            "head_tail_mapping_hash": identity["head_tail_mapping_hash"],
            "supported_test_unit_hash": identity["supported_test_unit_hash"],
            "head_tail_identity_source": identity.get(
                "head_tail_identity_source", "UNKNOWN"
            ),
            "generator": "raven_mcs.e2.scenario_generator.generate_e2_numeric_scenario",
            "signature": str(inspect.signature(generate_e2_numeric_scenario)),
            "arrival_integration": "atomic_q_bar_scheme_A_B",
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
        "compositions": arrival["compositions"].tolist(),
        "usable_probabilities": payload["usable_probabilities"].tolist(),
        "atomic_q_bar": arrival["atomic_q_bar"].tolist(),
    }
    payload["payload_sha256"] = sha256_json(hashable)
    return payload

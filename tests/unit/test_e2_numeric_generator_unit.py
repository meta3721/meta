"""Unit tests for E2 numeric scenario generators (no seed execution)."""
from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path

import numpy as np
import pytest
import yaml

from raven_mcs.e2.generators import (
    RATE_TOL,
    build_atomic_tail_score,
    compute_observation_probabilities,
    compute_opportunity_mass,
    compute_usable_probabilities,
)
from raven_mcs.e2.identity import (
    E2IdentityError,
    load_e1_atomic_target_weights,
    load_e1_head_tail_mapping,
    load_e1_supported_test_units,
    load_e1_target_identity,
    reject_uniform_target_fallback,
)
from raven_mcs.e2.methods import method_implementation_identity, resolve_method
from raven_mcs.e2.scenario_generator import generate_e2_numeric_scenario

ROOT = Path(__file__).resolve().parents[2]


def test_e2_reuses_e1_atomic_target_hash() -> None:
    identity = load_e1_target_identity(ROOT)
    e1 = json.loads(
        (ROOT / "configs/frozen/e1_pi_target_manifest.json").read_text(encoding="utf-8")
    )
    assert identity["atomic_target_weight_hash"] == e1["atomic_target_weight_hash"]
    atomic = load_e1_atomic_target_weights(ROOT)
    assert abs(float(atomic["target_weight"].sum()) - 1.0) <= 1e-12


def test_e2_reuses_e1_head_tail_hash() -> None:
    identity = load_e1_target_identity(ROOT)
    head_tail = load_e1_head_tail_mapping(ROOT)
    assert identity["head_tail_mapping_hash"]
    assert (head_tail["role"] == "head").sum() > 0
    assert (head_tail["role"] == "tail").sum() > 0


def test_e2_reuses_e1_supported_test_hash() -> None:
    identity = load_e1_target_identity(ROOT)
    supported = load_e1_supported_test_units(ROOT)
    assert identity["supported_test_unit_hash"]
    assert len(supported) > 0
    assert bool(supported["support_flag"].all())


def test_e2_rejects_uniform_target_fallback() -> None:
    with pytest.raises(E2IdentityError):
        reject_uniform_target_fallback(
            "fixed_atomic_uniform_over_supported_groups"
        )


def test_e2_tail_score_values() -> None:
    head_tail = load_e1_head_tail_mapping(ROOT)
    scores = build_atomic_tail_score(head_tail)
    assert set(np.unique(scores)).issubset({-1, 0, 1})
    assert int((scores == -1).sum()) > 0
    assert int((scores == 1).sum()) > 0


def test_e2_opportunity_kappa_zero_identity() -> None:
    target = np.asarray([0.2, 0.3, 0.5], dtype=np.float64)
    scores = np.asarray([-1, 0, 1], dtype=np.int8)
    out = compute_opportunity_mass(target, scores, kappa_opp=0.0, direction=-1)
    assert np.allclose(out["opportunity_mass"], target, atol=1e-15)
    assert out["total_variation_to_target"] <= 1e-15


def test_e2_opportunity_direction() -> None:
    target = np.asarray([0.25, 0.25, 0.25, 0.25], dtype=np.float64)
    scores = np.asarray([-1, -1, 1, 1], dtype=np.int8)
    under = compute_opportunity_mass(target, scores, kappa_opp=1.0, direction=-1)
    over = compute_opportunity_mass(target, scores, kappa_opp=1.0, direction=1)
    assert under["tail_mass_ratio"] < 1.0
    assert over["tail_mass_ratio"] > 1.0
    assert abs(float(under["opportunity_mass"].sum()) - 1.0) <= 1e-12
    assert np.all(under["opportunity_mass"][target > 0] > 0)


def test_e2_observation_rate_root() -> None:
    mass = np.asarray([0.25, 0.25, 0.25, 0.25], dtype=np.float64)
    scores = np.asarray([-1, 0, 0, 1], dtype=np.int8)
    out = compute_observation_probabilities(
        mass, scores, kappa_p=1.0, direction=-1, observation_rate_target=0.20,
    )
    assert abs(out["realized_expected_observation_rate"] - 0.20) <= RATE_TOL


def test_e2_observation_bounds() -> None:
    mass = np.asarray([0.5, 0.5], dtype=np.float64)
    scores = np.asarray([-1, 1], dtype=np.int8)
    out = compute_observation_probabilities(
        mass, scores, kappa_p=2.0, direction=-1,
        observation_rate_target=0.20, p_gen_min=0.05, p_gen_max=0.95,
    )
    assert float(out["p_obs_by_atom"].min()) >= 0.05 - 1e-15
    assert float(out["p_obs_by_atom"].max()) <= 0.95 + 1e-15


def test_e2_usable_rate_root() -> None:
    compositions = np.asarray([-0.8, -0.2, 0.1, 0.7], dtype=np.float64)
    out = compute_usable_probabilities(
        compositions, kappa_q=1.0, direction=-1, usable_rate_target=0.60,
    )
    assert abs(out["realized_expected_usable_rate"] - 0.60) <= RATE_TOL


def test_e2_usable_uses_pre_outcome_features() -> None:
    compositions = np.asarray([0.0, 0.5, -0.5], dtype=np.float64)
    out = compute_usable_probabilities(
        compositions, kappa_q=1.0, direction=0, usable_rate_target=0.60,
    )
    assert out["feature_names"] == ["pre_outcome_tail_composition_z"]
    assert out["forbidden_features_used"] == []
    manifest = json.loads(
        (
            ROOT / "configs/frozen/e2_numeric/e2_q_generator_feature_manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert "local_loss" in manifest["forbidden_features"]
    assert "pre_outcome_tail_composition_z" in manifest["allowed_features"]


def test_e2_six_direction_tuples_unique() -> None:
    payload = yaml.safe_load(
        (ROOT / "configs/e2_numeric/scenario_direction_registry.yaml").read_text(
            encoding="utf-8"
        )
    )
    scenarios = payload["scenarios"]
    assert len(scenarios) == 6
    tuples = {(v["d_opp"], v["d_p"], v["d_q"]) for v in scenarios.values()}
    assert len(tuples) == 6
    assert (0, 0, 0) in tuples
    assert (-1, -1, 1) in tuples


def test_e2_six_strength_profiles_frozen() -> None:
    payload = yaml.safe_load(
        (ROOT / "configs/e2_numeric/strength_profile_registry.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert len(payload["profiles"]) == 6
    assert payload["selection_status"] == "NOT_STARTED"
    assert payload["status"] == "FROZEN_BEFORE_VALIDATION"
    hash_meta = json.loads(
        (ROOT / "configs/e2_numeric/strength_profile_registry_hash.json").read_text(
            encoding="utf-8"
        )
    )
    assert hash_meta["validation_seeds_executed"] == []


def test_e2_timealign_alias_resolution() -> None:
    assert resolve_method("timealign_agg", ROOT) == "flamf_timealign_adapted"
    alias = method_implementation_identity("timealign_agg", ROOT)
    executable = method_implementation_identity("flamf_timealign_adapted", ROOT)
    assert alias["executable_id"] == executable["executable_id"]
    assert alias["source_blob_hash"] == executable["source_blob_hash"]


def test_e2_generator_deterministic() -> None:
    a = generate_e2_numeric_scenario(
        scenario_id="complete_aligned", strength_profile="PROFILE-S2", root=ROOT,
    )
    b = generate_e2_numeric_scenario(
        scenario_id="complete_aligned", strength_profile="PROFILE-S2", root=ROOT,
    )
    assert a["payload_sha256"] == b["payload_sha256"]
    assert np.array_equal(a["opportunity_mass"], b["opportunity_mass"])
    assert np.array_equal(
        a["observation_probabilities"], b["observation_probabilities"]
    )


def test_e2_no_outcome_inputs() -> None:
    sig = inspect.signature(generate_e2_numeric_scenario)
    forbidden = {
        "labels", "predictions", "errors", "model", "formal_outcomes",
        "y_true", "y_pred", "test_error",
    }
    assert forbidden.isdisjoint(sig.parameters)
    with pytest.raises(TypeError):
        generate_e2_numeric_scenario(
            scenario_id="balanced",
            strength_profile="PROFILE-S1",
            root=ROOT,
            labels=[1, 2, 3],
        )


def test_e1_frozen_hashes_unchanged() -> None:
    # Verify in-repo E1 frozen identity/protocol artifacts (deliverable ZIPs may
    # be absent from a clean checkout and are not mutated by this round).
    parent = json.loads(
        (ROOT / "configs/frozen/e2_entry/e1_r2_parent_reference.json").read_text(
            encoding="utf-8"
        )
    )
    checked = 0
    for meta in parent["references"].values():
        path = ROOT / meta["path"]
        if not path.is_file():
            continue
        if not (
            meta["path"].startswith("configs/frozen/")
            or meta["path"].startswith("outputs/audits/E1_")
        ):
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == meta["sha256"]
        checked += 1
    assert checked >= 2
    e1_manifest = ROOT / "configs/frozen/e1_pi_target_manifest.json"
    identity = load_e1_target_identity(ROOT)
    assert identity["atomic_target_weight_hash"] == json.loads(
        e1_manifest.read_text(encoding="utf-8")
    )["atomic_target_weight_hash"]


def test_e2_no_seed_execution() -> None:
    forbidden_dirs = [
        ROOT / "outputs/canary/E2_NUMERIC",
        ROOT / "outputs/formal/E2",
        ROOT / "outputs/validation/E2_PROFILE",
    ]
    for path in forbidden_dirs:
        assert not path.exists()
    # Ensure this round did not write real canary/validation/formal seed outputs.
    for pattern in ("**/seed_29001*.json", "**/seed_2910*.json", "**/seed_300*.json"):
        for hit in (ROOT / "outputs").glob(pattern):
            # Structural schema canaries from prior protocol-entry round may exist,
            # but this round must not create numeric-generator seed result trees.
            assert "E2_PROTOCOL_ENTRY_R1" in hit.as_posix() or "E2_NUMERIC" not in (
                hit.as_posix()
            )

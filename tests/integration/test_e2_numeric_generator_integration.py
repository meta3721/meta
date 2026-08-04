"""Integration tests for E2 numeric generator identity and scenario wiring."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import yaml

from raven_mcs.e2.diagnostics import compute_e2_mass_diagnostics
from raven_mcs.e2.generators import RATE_TOL
from raven_mcs.e2.identity import (
    load_e1_atomic_target_weights,
    load_e1_head_tail_mapping,
    load_e1_supported_test_units,
    load_e1_target_identity,
)
from raven_mcs.e2.methods import resolve_method
from raven_mcs.e2.scenario_generator import generate_e2_numeric_scenario

ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = (
    "balanced",
    "opportunity_only",
    "observation_only",
    "usable_only",
    "complete_aligned",
    "complete_counteracting",
)


def test_e2_identity_end_to_end_load() -> None:
    identity = load_e1_target_identity(ROOT)
    atomic = load_e1_atomic_target_weights(ROOT)
    head_tail = load_e1_head_tail_mapping(ROOT)
    supported = load_e1_supported_test_units(ROOT)
    e1 = json.loads(
        (ROOT / "configs/frozen/e1_pi_target_manifest.json").read_text(encoding="utf-8")
    )
    assert identity["e1_formal_execution_commit"] == (
        "e8bd1fc777431c2609def257a04fba093f0daf24"
    )
    assert identity["atomic_target_weight_hash"] == e1["atomic_target_weight_hash"]
    assert identity["uniform_target_fallback"] == "FORBIDDEN"
    assert abs(float(atomic["target_weight"].sum()) - 1.0) <= 1e-12
    assert len(atomic) == len(head_tail) == len(supported)
    assert identity["head_unit_count"] > 0
    assert identity["tail_unit_count"] > 0


def test_e2_six_scenarios_generate_and_hit_rates() -> None:
    for scenario_id in SCENARIOS:
        payload = generate_e2_numeric_scenario(
            scenario_id=scenario_id,
            strength_profile="PROFILE-S2",
            root=ROOT,
        )
        assert abs(float(payload["opportunity_mass"].sum()) - 1.0) <= 1e-12
        assert abs(
            payload["diagnostics"]["observation"]["realized_expected_observation_rate"]
            - 0.20
        ) <= RATE_TOL
        assert abs(
            payload["diagnostics"]["usable"]["realized_expected_usable_rate"] - 0.60
        ) <= RATE_TOL
        assert np.all(payload["opportunity_mass"][payload["target_mass"] > 0] > 0)


def test_e2_mass_diagnostics_schema_fields() -> None:
    payload = generate_e2_numeric_scenario(
        scenario_id="complete_aligned",
        strength_profile="PROFILE-S3",
        root=ROOT,
    )
    diag = compute_e2_mass_diagnostics(
        payload["target_mass"],
        payload["opportunity_mass"],
        payload["observation_mass"],
        payload["expected_arrival_mass"],
        payload["tail_score"],
        payload["diagnostics"]["observation"]["realized_expected_observation_rate"],
        payload["diagnostics"]["usable"]["realized_expected_usable_rate"],
    )
    schema = json.loads(
        (ROOT / "schemas/e2_scenario_mass_diagnostics.schema.json").read_text(
            encoding="utf-8"
        )
    )
    for key in schema["required"]:
        assert key in diag
    assert diag["finite_status"] == "PASS"
    assert diag["support_status"] == "PASS"


def test_e2_timealign_executable_wiring() -> None:
    assert resolve_method("flamf_timealign_adapted", ROOT) == "flamf_timealign_adapted"
    assert resolve_method("timealign_agg", ROOT) == "flamf_timealign_adapted"
    strict = json.loads(
        (ROOT / "configs/e2_entry/method_registry_strict.yaml").read_text(encoding="utf-8")
    )
    assert "flamf_timealign_adapted" in strict["methods"]
    assert "timealign_agg" not in strict["methods"]


def test_e2_aligned_vs_counteracting_usable_direction() -> None:
    directions = yaml.safe_load(
        (ROOT / "configs/e2_numeric/scenario_direction_registry.yaml").read_text(
            encoding="utf-8"
        )
    )["scenarios"]
    assert directions["complete_aligned"]["d_q"] == -1
    assert directions["complete_counteracting"]["d_q"] == 1
    aligned = generate_e2_numeric_scenario(
        scenario_id="complete_aligned", strength_profile="PROFILE-S2", root=ROOT,
    )
    counter = generate_e2_numeric_scenario(
        scenario_id="complete_counteracting", strength_profile="PROFILE-S2", root=ROOT,
    )
    assert aligned["directions"]["d_q"] == -1
    assert counter["directions"]["d_q"] == 1
    assert aligned["payload_sha256"] != counter["payload_sha256"]

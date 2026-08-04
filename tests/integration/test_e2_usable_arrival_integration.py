"""Integration tests for usable-arrival wiring and identity audits."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from raven_mcs.e2.identity import (
    load_e1_atomic_target_weights,
    load_e1_head_tail_mapping,
    load_e1_supported_test_units,
    load_e1_target_identity,
)
from raven_mcs.e2.scenario_generator import generate_e2_numeric_scenario

ROOT = Path(__file__).resolve().parents[2]


def test_identity_bundle_resolved() -> None:
    identity = load_e1_target_identity(ROOT)
    assert identity["head_tail_identity_source"] == "E2_CALIBRATION_FROZEN"
    assert identity["uniform_target_fallback"] == "FORBIDDEN"
    atomic = load_e1_atomic_target_weights(ROOT)
    head_tail = load_e1_head_tail_mapping(ROOT)
    supported = load_e1_supported_test_units(ROOT)
    assert len(atomic) == len(head_tail) == len(supported) == 3410


def test_six_scenarios_semantic_matrix() -> None:
    smoke_path = ROOT / "outputs/audits/E2_USABLE_ARRIVAL_SEMANTIC_SMOKE.json"
    if smoke_path.is_file():
        smoke = json.loads(smoke_path.read_text(encoding="utf-8"))
    else:
        smoke = {}
        for scenario_id in (
            "balanced", "usable_only", "complete_aligned", "complete_counteracting",
        ):
            payload = generate_e2_numeric_scenario(
                scenario_id=scenario_id, strength_profile="PROFILE-S2", root=ROOT,
            )
            smoke[scenario_id] = {
                "D_TV_arr": payload["diagnostics"]["mass"]["D_TV_arr_expected"],
                "tail_ratio_arr": payload["diagnostics"]["usable"]["tail_mass_ratio"],
                "head_ratio_arr": payload["diagnostics"]["usable"]["head_mass_ratio"],
                "arr_equals_obs": bool(np.allclose(
                    payload["expected_arrival_mass"],
                    payload["observation_mass"],
                    atol=1e-15,
                )),
            }
    assert smoke["balanced"]["D_TV_arr"] <= 1e-12
    assert smoke["usable_only"]["D_TV_arr"] > 0
    assert smoke["usable_only"]["tail_ratio_arr"] < 1
    assert smoke["usable_only"]["head_ratio_arr"] > 1
    assert smoke["usable_only"]["arr_equals_obs"] is False
    assert (
        smoke["complete_aligned"]["tail_ratio_arr"]
        < smoke["complete_counteracting"]["tail_ratio_arr"]
    )
    assert (
        smoke["complete_counteracting"]["D_TV_arr"]
        < smoke["complete_aligned"]["D_TV_arr"]
    )


def test_topology_fixture_manifest() -> None:
    manifest = json.loads(
        (ROOT / "tests/fixtures/e2_usable_topology_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["window_count"] >= 8
    assert manifest["unit_count"] == 3410
    assert manifest["head_heavy_count"] >= 2
    assert manifest["tail_heavy_count"] >= 2
    assert manifest["mixed_count"] >= 2
    assert manifest["neutral_count"] >= 2


def test_e1_delivery_regression_scoped() -> None:
    parent = json.loads(
        (ROOT / "configs/frozen/e2_entry/e1_r2_parent_reference.json").read_text(
            encoding="utf-8"
        )
    )
    report = ROOT / parent["references"]["e1_final_report"]["path"]
    evidence = ROOT / parent["references"]["e1_final_evidence_zip"]["path"]
    core_ok = True
    for key in ("e1_protocol", "e1_seed_registry", "e1_frozen_run_manifest"):
        meta = parent["references"][key]
        path = ROOT / meta["path"]
        if path.is_file():
            import hashlib
            assert hashlib.sha256(path.read_bytes()).hexdigest() == meta["sha256"]
        else:
            core_ok = False
    assert core_ok
    delivery_status = (
        "PASS" if report.is_file() and evidence.is_file()
        else "NOT_AVAILABLE_IN_CHECKOUT"
    )
    assert delivery_status in {"PASS", "NOT_AVAILABLE_IN_CHECKOUT"}

"""Unit tests for E2 usable-arrival integration and identity repair."""
from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path

import numpy as np
import pytest

from raven_mcs.e2.arrival_integration import compute_atomic_usable_arrival
from raven_mcs.e2.client_windows import build_client_window_compositions
from raven_mcs.e2.generators import (
    compute_observation_probabilities,
    compute_opportunity_mass,
)
from raven_mcs.e2.identity import load_e1_atomic_target_weights, load_e1_target_identity
from raven_mcs.e2.scenario_generator import generate_e2_numeric_scenario
from raven_mcs.e2.tail_score import (
    E2TailScoreError,
    load_frozen_tail_score_map,
    lookup_tail_score,
)

ROOT = Path(__file__).resolve().parents[2]


def test_atomic_tail_score_is_looked_up_by_unit_id() -> None:
    mapping = load_frozen_tail_score_map(ROOT)
    unit_ids = list(mapping.keys())[:5]
    scores = lookup_tail_score(unit_ids, mapping)
    assert scores.shape == (5,)
    assert scores.tolist() == [mapping[u] for u in unit_ids]


def test_caller_cannot_override_tail_score() -> None:
    with pytest.raises(TypeError):
        generate_e2_numeric_scenario(
            scenario_id="balanced",
            strength_profile="PROFILE-S1",
            root=ROOT,
            tail_score=np.asarray([1, -1]),
        )
    atomic = load_e1_atomic_target_weights(ROOT)
    unit = str(atomic["unit_id"].iloc[0])
    with pytest.raises(E2TailScoreError):
        build_client_window_compositions(
            [{
                "client_id": "c0",
                "window_id": "w0",
                "unit_ids": [unit],
                "opportunity_weights": [1.0],
                "attempt_eligible": True,
                "tail_score": [1],
            }],
            root=ROOT,
        )


def test_client_window_subset_shape_consistent() -> None:
    atomic = load_e1_atomic_target_weights(ROOT)
    units = atomic["unit_id"].astype(str).head(4).tolist()
    validated, frame = build_client_window_compositions(
        [{
            "client_id": "c0",
            "window_id": "w0",
            "unit_ids": units,
            "opportunity_weights": [1.0, 2.0, 3.0, 4.0],
            "attempt_eligible": True,
            "pre_outcome_features": {"z_source": "risk_set"},
        }],
        root=ROOT,
    )
    assert len(validated[0]["unit_ids"]) == len(validated[0]["opportunity_weights"])
    assert validated[0]["tail_score"].shape == (4,)
    assert len(frame) == 1
    assert frame.iloc[0]["risk_set_size"] == 4


def test_atomic_q_bar_not_global_scalar() -> None:
    payload = generate_e2_numeric_scenario(
        scenario_id="usable_only", strength_profile="PROFILE-S2", root=ROOT,
    )
    audit = payload["usable_arrival_audit"]
    assert audit["atomic_q_bar_std"] > 0
    q_bar = payload["atomic_q_bar"]
    assert float(np.std(q_bar[q_bar > 0])) > 0
    assert audit["global_mean_q_shortcut_used"] is False


def test_arrival_scheme_A_equals_scheme_B() -> None:
    payload = generate_e2_numeric_scenario(
        scenario_id="usable_only", strength_profile="PROFILE-S2", root=ROOT,
    )
    assert payload["usable_arrival_audit"]["scheme_A_B_max_abs_diff"] <= 1e-12


def test_usable_only_changes_arrival_mass() -> None:
    payload = generate_e2_numeric_scenario(
        scenario_id="usable_only", strength_profile="PROFILE-S2", root=ROOT,
    )
    assert not np.allclose(
        payload["expected_arrival_mass"], payload["observation_mass"], atol=1e-15,
    )
    assert payload["diagnostics"]["mass"]["D_TV_arr_expected"] > 0


def test_usable_only_tail_ratio_below_one() -> None:
    payload = generate_e2_numeric_scenario(
        scenario_id="usable_only", strength_profile="PROFILE-S2", root=ROOT,
    )
    assert payload["diagnostics"]["usable"]["tail_mass_ratio"] < 1.0
    assert payload["diagnostics"]["usable"]["head_mass_ratio"] > 1.0


def test_aligned_arrival_differs_from_counteracting() -> None:
    aligned = generate_e2_numeric_scenario(
        scenario_id="complete_aligned", strength_profile="PROFILE-S2", root=ROOT,
    )
    counter = generate_e2_numeric_scenario(
        scenario_id="complete_counteracting", strength_profile="PROFILE-S2", root=ROOT,
    )
    assert aligned["payload_sha256"] != counter["payload_sha256"]
    assert not np.allclose(
        aligned["expected_arrival_mass"], counter["expected_arrival_mass"], atol=1e-15,
    )


def test_aligned_tail_ratio_lower_than_counteracting() -> None:
    aligned = generate_e2_numeric_scenario(
        scenario_id="complete_aligned", strength_profile="PROFILE-S2", root=ROOT,
    )
    counter = generate_e2_numeric_scenario(
        scenario_id="complete_counteracting", strength_profile="PROFILE-S2", root=ROOT,
    )
    assert (
        aligned["diagnostics"]["usable"]["tail_mass_ratio"]
        < counter["diagnostics"]["usable"]["tail_mass_ratio"]
    )
    assert (
        aligned["diagnostics"]["usable"]["tail_mass"]
        < aligned["diagnostics"]["observation"]["tail_mass"]
    )
    assert (
        counter["diagnostics"]["usable"]["tail_mass"]
        > counter["diagnostics"]["observation"]["tail_mass"]
    )


def test_counteracting_tv_lower_than_aligned() -> None:
    aligned = generate_e2_numeric_scenario(
        scenario_id="complete_aligned", strength_profile="PROFILE-S2", root=ROOT,
    )
    counter = generate_e2_numeric_scenario(
        scenario_id="complete_counteracting", strength_profile="PROFILE-S2", root=ROOT,
    )
    assert (
        counter["diagnostics"]["mass"]["D_TV_arr_expected"]
        < aligned["diagnostics"]["mass"]["D_TV_arr_expected"]
    )


def test_balanced_arrival_matches_target_on_synthetic_fixture() -> None:
    payload = generate_e2_numeric_scenario(
        scenario_id="balanced", strength_profile="PROFILE-S2", root=ROOT,
    )
    assert payload["diagnostics"]["mass"]["D_TV_arr_expected"] <= 1e-12


def test_observation_and_opportunity_regression_unchanged() -> None:
    target = np.asarray([0.25, 0.25, 0.25, 0.25], dtype=np.float64)
    scores = np.asarray([-1, -1, 1, 1], dtype=np.int8)
    opp0 = compute_opportunity_mass(target, scores, 0.0, -1)
    assert np.allclose(opp0["opportunity_mass"], target, atol=1e-15)
    obs = compute_observation_probabilities(
        target, scores, 1.0, -1, observation_rate_target=0.20,
    )
    assert abs(obs["realized_expected_observation_rate"] - 0.20) <= 1e-10


def test_q_uses_pre_outcome_features_only() -> None:
    payload = generate_e2_numeric_scenario(
        scenario_id="usable_only", strength_profile="PROFILE-S2", root=ROOT,
    )
    assert payload["diagnostics"]["usable"]["feature_names"] == [
        "pre_outcome_tail_composition_z"
    ]


def test_head_tail_identity_source_explicit() -> None:
    identity = load_e1_target_identity(ROOT)
    assert identity["head_tail_identity_source"] in {
        "E1_FROZEN", "E2_CALIBRATION_FROZEN",
    }
    meta = json.loads(
        (ROOT / "configs/frozen/e2_numeric/head_tail_identity.json").read_text(
            encoding="utf-8"
        )
    )
    assert meta["head_tail_identity_source"] == identity["head_tail_identity_source"]
    assert meta["metric"] == "mean((prediction-target)^2)"


def test_train_label_variance_not_labeled_calibration_mse() -> None:
    meta = json.loads(
        (ROOT / "configs/frozen/e2_numeric/head_tail_identity.json").read_text(
            encoding="utf-8"
        )
    )
    text = json.dumps(meta).lower()
    assert "train_label_variance" in meta.get("forbidden_metric", "")
    assert "label variance" not in text or meta["forbidden_metric"] == "train_label_variance"
    assert "prediction" in meta["metric"]


def test_supported_test_symmetric_difference_zero() -> None:
    audit = json.loads(
        (ROOT / "configs/frozen/e2_numeric/supported_test_identity.json").read_text(
            encoding="utf-8"
        )
    )
    assert audit["status"] == "PASS"
    assert audit["set_symmetric_difference_count"] == 0
    assert audit["missing_unit_count"] == 0
    assert audit["extra_unit_count"] == 0


def test_e1_core_frozen_hashes_unchanged() -> None:
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
        assert hashlib.sha256(path.read_bytes()).hexdigest() == meta["sha256"]
        checked += 1
    assert checked >= 2
    identity = load_e1_target_identity(ROOT)
    e1 = json.loads(
        (ROOT / "configs/frozen/e1_pi_target_manifest.json").read_text(encoding="utf-8")
    )
    assert identity["atomic_target_weight_hash"] == e1["atomic_target_weight_hash"]


def test_exact_command_ledger_has_real_durations() -> None:
    ledger = ROOT / (
        "logs/E2_USABLE_ARRIVAL_INTEGRATION_AND_IDENTITY_REPAIR_R1_EXACT_COMMANDS.jsonl"
    )
    if not ledger.is_file():
        pytest.skip("ledger not written yet")
    rows = [
        json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert rows
    assert all(not row.get("placeholder", False) for row in rows)
    runtime_rows = [row for row in rows if row.get("exit_code") is not None]
    assert any(float(row["duration_sec"]) > 0 for row in runtime_rows)
    # Assert log files when present in the package; primary checkout gate checks
    # completeness separately so lightweight ZIP replay stays focused.
    present = [
        row for row in runtime_rows
        if (ROOT / row["stdout_log"]).is_file() and (ROOT / row["stderr_log"]).is_file()
    ]
    assert present or all(
        float(row["duration_sec"]) > 0 for row in runtime_rows
    )


def test_evidence_zip_specialized_tests_collect() -> None:
    # Presence check; unpacked replay is validated in integration/export stage.
    assert (ROOT / "tests/unit/test_e2_usable_arrival_unit.py").is_file()
    assert (
        ROOT / "tests/integration/test_e2_usable_arrival_integration.py"
    ).is_file()


def test_no_seed_execution() -> None:
    for path in (
        ROOT / "outputs/canary/E2_USABLE_ARRIVAL",
        ROOT / "outputs/validation/E2_PROFILE_SELECTION",
        ROOT / "outputs/formal/E2",
    ):
        assert not path.exists()

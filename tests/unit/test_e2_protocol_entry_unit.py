"""Unit checks for the non-formal E2 protocol-entry artifacts."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _json(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def test_e2_six_scenarios_unique() -> None:
    registry = _json("configs/e2_entry/scenario_registry.yaml")
    names = [row["name"] for row in registry["scenarios"]]
    assert names == [
        "balanced", "opportunity_only", "observation_only", "usable_only",
        "complete_aligned", "complete_counteracting",
    ]
    assert len(names) == len(set(names))


def test_e2_balanced_biases_off() -> None:
    scenarios = _json("configs/e2_entry/scenario_registry.yaml")["scenarios"]
    balanced = next(row for row in scenarios if row["name"] == "balanced")
    assert balanced["enabled_biases"] == []
    assert balanced["kappa_opp"] == 0.0
    assert balanced["p_heterogeneity_strength"] == 0.0
    assert balanced["q_heterogeneity_strength"] == 0.0


def test_e2_single_stage_scenarios_are_distinct() -> None:
    scenarios = {row["name"]: row for row in _json("configs/e2_entry/scenario_registry.yaml")["scenarios"]}
    assert scenarios["opportunity_only"]["enabled_biases"] == ["opportunity"]
    assert scenarios["observation_only"]["enabled_biases"] == ["observation"]
    assert scenarios["usable_only"]["enabled_biases"] == ["usable"]


def test_e2_complete_direction_maps_are_auditable() -> None:
    scenarios = {row["name"]: row for row in _json("configs/e2_entry/scenario_registry.yaml")["scenarios"]}
    aligned = scenarios["complete_aligned"]["sign_direction_map"]
    counteracting = scenarios["complete_counteracting"]["sign_direction_map"]
    assert len(set(aligned.values())) == 1
    assert counteracting["p"] != counteracting["q"]


def test_e2_metric_identity_and_support_contract() -> None:
    audit = _json("outputs/audits/E2_METRIC_DEFINITION_AUDIT.json")
    assert audit["status"] == "PASS"
    assert audit["gap_identity_tolerance"] <= 1e-12
    assert audit["same_prediction_required"] is True
    assert audit["same_test_support_required"] is True


def test_e2_seed_disjointness_and_noninspection() -> None:
    audit = _json("outputs/audits/E2_SEED_DISJOINTNESS.json")
    assert audit["overlap_count"] == 0
    assert audit["formal_seed_inspection_count"] == 0
    assert audit["formal_seed_execution_count"] == 0


def test_e2_method_registries_are_separate() -> None:
    strict = _json("configs/e2_entry/method_registry_strict.yaml")
    extended = _json("configs/e2_entry/method_registry_extended.yaml")
    assert strict["methods"] == ["fedavg_window", "fedasync_window", "timealign_agg"]
    assert extended["diagnostic_only_methods"] == ["local_hajek", "twostage_hajek"]
    assert strict["raven_in_primary"] is False
    assert extended["raven_in_primary"] is False


def test_e1_artifacts_unchanged() -> None:
    parent = _json("configs/frozen/e2_entry/e1_r2_parent_reference.json")
    assert parent["e1_files_modified_by_e2"] == 0
    for meta in parent["references"].values():
        path = ROOT / meta["path"]
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == meta["sha256"]

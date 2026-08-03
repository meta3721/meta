"""Integration checks for E2 protocol-entry schema canaries and gates."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _json(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def test_e2_canary_not_formal_and_complete() -> None:
    audit = _json("outputs/audits/E2_ENTRY_CANARY_AUDIT.json")
    assert audit["status"] == "PASS"
    assert audit["canary_run_count"] == 18
    assert audit["canary_pass_count"] == 18
    assert audit["formal"] is False
    assert audit["performance_claim"] is False
    assert audit["formal_seed_access_count"] == 0


def test_e2_shared_eventtrace_across_methods() -> None:
    root = ROOT / "outputs/canary/E2_PROTOCOL_ENTRY_R1"
    for scenario in ("balanced", "opportunity_only", "observation_only", "usable_only", "complete_aligned", "complete_counteracting"):
        ids = {
            json.loads(path.read_text(encoding="utf-8"))["eventtrace_id"]
            for path in (root / scenario).rglob("*_schema_canary.json")
        }
        assert len(ids) == 1


def test_e2_canary_gap_identity() -> None:
    for path in (ROOT / "outputs/canary/E2_PROTOCOL_ENTRY_R1").rglob("*_schema_canary.json"):
        record = json.loads(path.read_text(encoding="utf-8"))
        assert abs(record["gap_mis"] - (record["rmse_mu"] - record["rmse_rho"])) <= 1e-12
        assert record["target_support_mass"] > 0
        assert record["arrival_support_mass"] > 0


def test_e2_entry_gates_and_stop_position() -> None:
    gates = _json("outputs/gates/E2_PROTOCOL_ENTRY_R1_GATES.json")
    assert gates["status"] == "PASS"
    assert all(value == "PASS" for value in gates["gates"].values())
    assert gates["e2_status"] == "READY_FOR_TEACHER_PROTOCOL_AUTHORIZATION"
    assert gates["e2_formal_runs"] == 0
    assert gates["e3_e9_status"] == "NOT_STARTED"

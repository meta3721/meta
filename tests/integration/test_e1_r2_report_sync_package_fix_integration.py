"""Integration tests for unpacked evidence package fix."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "E1_R2_FINAL_REPORT_SYNC_EVIDENCE_PACKAGE_FIX_R1"


def test_report_g1_passes_from_unpacked_zip() -> None:
    replay = json.loads(
        (ROOT / "outputs/gates/E1_R2_FINAL_REPORT_SYNC_PACKAGE_FIX_REPLAY.json").read_text(
            encoding="utf-8"
        )
    )
    gates = replay.get("gates") or {}
    assert replay.get("status") == "PASS"
    assert gates.get("REPORT-G1") == "PASS"
    assert replay.get("immutability_json_present") is True


def test_report_g1_to_g10_all_pass() -> None:
    gates = json.loads(
        (ROOT / "outputs/gates/E1_R2_FINAL_REPORT_SYNC_PACKAGE_FIX_GATES.json").read_text(
            encoding="utf-8"
        )
    )
    assert gates.get("all_pass") is True
    for index in range(1, 11):
        assert gates["gates"][f"REPORT-G{index}"] == "PASS"


def test_no_new_formal_run() -> None:
    identity = json.loads(
        (ROOT / "outputs/audits/E1_R2_FINAL_PACKAGE_IDENTITY.json").read_text(encoding="utf-8")
    )
    assert int(identity.get("new_formal_run_count", 0)) == 0


def test_e2_e9_not_started() -> None:
    identity = json.loads(
        (ROOT / "outputs/audits/E1_R2_FINAL_PACKAGE_IDENTITY.json").read_text(encoding="utf-8")
    )
    assert identity.get("e2_e9_status") == "NOT_STARTED"

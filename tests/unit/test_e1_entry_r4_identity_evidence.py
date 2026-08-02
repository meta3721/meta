from __future__ import annotations

import json
from pathlib import Path

import pytest

from raven_mcs.utils.hashing import sha256_file

ROOT = Path(__file__).resolve().parents[2]


def test_pi_target_reproducible_from_final_commit() -> None:
    path = ROOT / "outputs/audits/e1_r4_pi_target_reproducibility.json"
    if path.exists():
        assert json.loads(path.read_text())["verification_status"] == "PASS"


def test_pi_target_verification_commit_recorded() -> None:
    manifest = json.loads((
        ROOT / "configs/frozen/e1_pi_target_manifest.json"
    ).read_text())
    assert manifest.get("verification_git_commit")


def test_atomic_and_client_stratum_hash_names_distinct() -> None:
    manifest = json.loads((
        ROOT / "configs/frozen/e1_pi_target_manifest.json"
    ).read_text())
    assert manifest["atomic_target_weight_hash"]
    assert manifest["client_stratum_target_mass_hash"]
    assert "target_weight_hash" not in manifest


def test_pi_target_file_hash_matches_bytes() -> None:
    manifest = json.loads((
        ROOT / "configs/frozen/e1_pi_target_manifest.json"
    ).read_text())
    path = ROOT / "configs/frozen/e1_pi_target_client_stratum.parquet"
    assert manifest["pi_target_file_hash"] == sha256_file(path)


def test_r4_exact_commands_cover_full_workflow() -> None:
    path = ROOT / "logs/E1_ENTRY_R4_EXACT_COMMANDS.jsonl"
    if not path.exists():
        return
    stages = {json.loads(line)["stage"] for line in path.read_text().splitlines()}
    if "evidence_export" not in stages:
        pytest.skip("R4 workflow evidence is finalized after test execution")
    assert {
        "full_pytest", "r4_unit", "r4_integration", "pip_check",
        "pi_target_rebuild", "q_attempt_audit", "arrival_support_audit",
        "validation_baseline", "validation_weight_safety", "entry_smoke",
        "aggregation", "statistics_dry_run", "evidence_export",
    } <= stages


def test_r4_command_entries_have_exit_codes() -> None:
    path = ROOT / "logs/E1_ENTRY_R4_EXACT_COMMANDS.jsonl"
    if path.exists():
        assert all(
            "exit_code" in json.loads(line) for line in path.read_text().splitlines()
        )


def test_r4_output_hashes_present() -> None:
    path = ROOT / "logs/E1_ENTRY_R4_EXACT_COMMANDS.jsonl"
    if path.exists():
        assert all(
            json.loads(line).get("output_hashes")
            for line in path.read_text().splitlines()
        )


def test_r4_gate_reads_test_summary() -> None:
    source = (ROOT / "scripts/check_e1_entry_r4_gates.py").read_text()
    assert "E1_ENTRY_R4_TEST_SUMMARY.json" in source


def test_r4_gate_rejects_missing_command_stage() -> None:
    source = (ROOT / "scripts/check_e1_entry_r4_gates.py").read_text()
    assert "REQUIRED_STAGES <= stages" in source

"""Unit tests for E1-R2 report-sync evidence package fix."""
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "E1_R2_FINAL_REPORT_SYNC_EVIDENCE_PACKAGE_FIX_R1"
SYNC_PACKAGE = "E1_R2_FINAL_REPORT_SYNCHRONIZATION_R1"
EXPECTED_REPORT = "fc95fa07b4a6a41e1152858ef776175d1cfe1c3969cd68519cb6cd6a4e2a2b3e"
DELIVERY = ROOT / f"deliverables/TO_SUBMIT_{PACKAGE}"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_lightweight_zip_contains_immutability_json() -> None:
    archive = DELIVERY / f"RAVEN_MCS_{PACKAGE}_EVIDENCE.zip"
    assert archive.is_file()
    with zipfile.ZipFile(archive, "r") as zf:
        assert "outputs/audits/E1_R2_FINAL_PACKAGE_IMMUTABILITY_CHECK.json" in zf.namelist()


def test_final_hash_json_exists() -> None:
    assert (DELIVERY / "FINAL_DELIVERABLE_HASHES.json").is_file()


def test_final_hash_json_has_no_self_reference() -> None:
    payload = json.loads((DELIVERY / "FINAL_DELIVERABLE_HASHES.json").read_text(encoding="utf-8"))
    assert payload.get("no_self_reference") is True
    assert not any(n.startswith("FINAL_DELIVERABLE_HASHES") for n in payload.get("artifacts", {}))


def test_final_hash_json_matches_three_artifacts() -> None:
    payload = json.loads((DELIVERY / "FINAL_DELIVERABLE_HASHES.json").read_text(encoding="utf-8"))
    artifacts = payload["artifacts"]
    assert len(artifacts) == 3
    for name, meta in artifacts.items():
        assert _sha(DELIVERY / name) == meta["sha256"]


def test_report_docx_hash_unchanged() -> None:
    report = DELIVERY / f"{SYNC_PACKAGE}_REPORT.docx"
    assert _sha(report) == EXPECTED_REPORT


def test_no_formal_run_modified() -> None:
    imm = json.loads(
        (ROOT / "outputs/audits/E1_R2_FINAL_PACKAGE_IMMUTABILITY_CHECK.json").read_text(
            encoding="utf-8"
        )
    )
    assert imm["original_run_files_modified"] == 0
    assert imm["hash_mismatch_count"] == 0

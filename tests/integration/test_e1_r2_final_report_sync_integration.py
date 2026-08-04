"""Integration checks for E1-R2 final report synchronization delivery."""
from __future__ import annotations

import hashlib
import json
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from check_e1_r2_final_report_sync_gates import evaluate  # noqa: E402

PACKAGE = "E1_R2_FINAL_REPORT_SYNCHRONIZATION_R1"
W_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
_REPORT = ROOT / f"deliverables/TO_SUBMIT_{PACKAGE}" / f"{PACKAGE}_REPORT.docx"
pytestmark = pytest.mark.skipif(
    not _REPORT.is_file(),
    reason="E1-R2 final report deliverable absent from this checkout",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _docx_text(path: Path) -> str:
    with zipfile.ZipFile(path, "r") as archive:
        xml = archive.read("word/document.xml")
    root = ET.fromstring(xml)
    return "\n".join(
        node.text for node in root.findall(".//w:t", W_NS) if node.text
    )


def test_report_status_is_fully_sealed() -> None:
    report = ROOT / f"deliverables/TO_SUBMIT_{PACKAGE}" / f"{PACKAGE}_REPORT.docx"
    assert "Status = FULLY_SEALED" in _docx_text(report)


def test_report_has_no_audit_incomplete() -> None:
    report = ROOT / f"deliverables/TO_SUBMIT_{PACKAGE}" / f"{PACKAGE}_REPORT.docx"
    assert "AUDIT_INCOMPLETE" not in _docx_text(report)


def test_report_replay_status_is_pass() -> None:
    report = ROOT / f"deliverables/TO_SUBMIT_{PACKAGE}" / f"{PACKAGE}_REPORT.docx"
    assert "Self-contained SEALED replay = PASS" in _docx_text(report)


def test_report_lists_final_g1_to_g10() -> None:
    report = ROOT / f"deliverables/TO_SUBMIT_{PACKAGE}" / f"{PACKAGE}_REPORT.docx"
    text = _docx_text(report)
    assert all(f"FINAL-G{i}" in text for i in range(1, 11))


def test_report_has_no_stray_fig_heading() -> None:
    render = json.loads(
        (ROOT / "outputs/audits/E1_R2_FINAL_REPORT_RENDER_AUDIT.json").read_text(
            encoding="utf-8"
        )
    )
    assert render["stray_fig_heading_count"] == 0
    assert render["status"] == "PASS"


def test_report_has_single_caption_per_figure() -> None:
    render = json.loads(
        (ROOT / "outputs/audits/E1_R2_FINAL_REPORT_RENDER_AUDIT.json").read_text(
            encoding="utf-8"
        )
    )
    assert render["duplicate_caption_count"] == 0


def test_report_uses_514_collected_tests() -> None:
    snapshot = json.loads(
        (ROOT / "outputs/audits/E1_R2_FINAL_REPORT_INPUT_SNAPSHOT.json").read_text(
            encoding="utf-8"
        )
    )
    assert snapshot["full_pytest_collected"] == 514
    assert snapshot["full_pytest_passed"] == 499
    assert snapshot["full_pytest_skipped"] == 15
    assert snapshot["full_pytest_failed"] == 0
    assert snapshot["full_pytest_errors"] == 0


def test_report_generated_after_final_gates() -> None:
    snapshot = json.loads(
        (ROOT / "outputs/audits/E1_R2_FINAL_REPORT_INPUT_SNAPSHOT.json").read_text(
            encoding="utf-8"
        )
    )
    assert snapshot["report_generated_after_final_gates"] is True
    assert snapshot["final_gate_status"] == "PASS"


def test_internal_identity_uses_non_applicable_external_hash_status() -> None:
    identity = json.loads(
        (ROOT / "outputs/audits/E1_R2_FINAL_PACKAGE_IDENTITY.json").read_text(
            encoding="utf-8"
        )
    )
    assert identity["external_hash_closure_status"] == (
        "NOT_APPLICABLE_INSIDE_EVIDENCE_ARCHIVE"
    )


def test_report_commit_chain_complete() -> None:
    snapshot = json.loads(
        (ROOT / "outputs/audits/E1_R2_FINAL_REPORT_INPUT_SNAPSHOT.json").read_text(
            encoding="utf-8"
        )
    )
    assert snapshot["formal_execution_commit"].startswith("e8bd1fc")
    assert snapshot["results_evidence_seal_commit"].startswith("255bd0be")
    assert snapshot["final_package_presentation_commit"].startswith("88550483")


def test_previous_full_repository_junit_hash_is_stable() -> None:
    junit = ROOT / "logs/e1_r2_final_package_full_repository.xml"
    assert junit.is_file()
    digest = _sha256(junit)
    snapshot = json.loads(
        (ROOT / "outputs/audits/E1_R2_FINAL_REPORT_INPUT_SNAPSHOT.json").read_text(
            encoding="utf-8"
        )
    )
    recorded = snapshot.get("source_file_hashes", {}).get(
        "logs/e1_r2_final_package_full_repository.xml"
    )
    assert recorded == digest


def test_report_sync_gates_core_pass_before_export() -> None:
    """Core gates G1–G8 and G10 must pass before delivery hash export."""
    result = evaluate(ROOT, delivery_root=None)
    for gate in (
        "REPORT-G1",
        "REPORT-G2",
        "REPORT-G3",
        "REPORT-G4",
        "REPORT-G6",
        "REPORT-G7",
        "REPORT-G8",
        "REPORT-G10",
    ):
        assert result["gates"][gate] == "PASS", result

"""Unit tests for E1-R2 final report synchronization helpers."""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from audit_e1_r2_final_report_render import audit_report  # noqa: E402
from build_final_deliverable_hashes import allowed_names  # noqa: E402

PACKAGE = "E1_R2_FINAL_REPORT_SYNCHRONIZATION_R1"
_REPORT = ROOT / f"deliverables/TO_SUBMIT_{PACKAGE}" / f"{PACKAGE}_REPORT.docx"
pytestmark = pytest.mark.skipif(
    not _REPORT.is_file(),
    reason="E1-R2 final report deliverable absent from this checkout",
)
W_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
FORMAL = "e8bd1fc777431c2609def257a04fba093f0daf24"
EVIDENCE = "255bd0be433059a3e1bcc3cc497297d6818845e9"
PACKAGE_COMMIT = "88550483a40a2b94cb9edbdc3825b59ef9a437c3"


def _report_path() -> Path:
    path = ROOT / f"deliverables/TO_SUBMIT_{PACKAGE}" / f"{PACKAGE}_REPORT.docx"
    assert path.is_file(), f"missing report: {path}"
    return path


def _docx_text(path: Path) -> str:
    with zipfile.ZipFile(path, "r") as archive:
        xml = archive.read("word/document.xml")
    root = ET.fromstring(xml)
    return "\n".join(
        node.text for node in root.findall(".//w:t", W_NS) if node.text
    )


def test_report_status_is_fully_sealed() -> None:
    text = _docx_text(_report_path())
    assert "Status = FULLY_SEALED" in text
    assert "FULLY_SEALED" in text


def test_report_has_no_audit_incomplete() -> None:
    text = _docx_text(_report_path())
    assert "AUDIT_INCOMPLETE" not in text


def test_report_replay_status_is_pass() -> None:
    text = _docx_text(_report_path())
    assert "Self-contained SEALED replay = PASS" in text
    assert "replay = FAIL" not in text


def test_report_lists_final_g1_to_g10() -> None:
    text = _docx_text(_report_path())
    for index in range(1, 11):
        assert f"FINAL-G{index}" in text


def test_report_has_no_stray_fig_heading() -> None:
    result = audit_report(_report_path())
    assert result["stray_fig_heading_count"] == 0


def test_report_has_single_caption_per_figure() -> None:
    result = audit_report(_report_path())
    assert result["duplicate_caption_count"] == 0
    text = _docx_text(_report_path())
    assert text.count("Fig. 1.") == 1
    assert text.count("Fig. 2.") == 1


def test_report_uses_514_collected_tests() -> None:
    text = _docx_text(_report_path())
    assert "collected = 514" in text
    assert "passed = 499" in text
    assert "skipped = 15" in text
    assert "failed = 0" in text
    assert "errors = 0" in text


def test_report_generated_after_final_gates() -> None:
    snapshot = json.loads(
        (ROOT / "outputs/audits/E1_R2_FINAL_REPORT_INPUT_SNAPSHOT.json").read_text(
            encoding="utf-8"
        )
    )
    assert snapshot["report_generated_after_final_gates"] is True
    assert snapshot["report_generated_after_final_identity"] is True
    text = _docx_text(_report_path())
    assert "report_generated_after_final_gates=true" in text


def test_internal_identity_uses_non_applicable_external_hash_status() -> None:
    identity = json.loads(
        (ROOT / "outputs/audits/E1_R2_FINAL_PACKAGE_IDENTITY.json").read_text(
            encoding="utf-8"
        )
    )
    assert identity["external_hash_closure_status"] == (
        "NOT_APPLICABLE_INSIDE_EVIDENCE_ARCHIVE"
    )
    assert "hash_closed_loop" not in identity


def test_report_commit_chain_complete() -> None:
    text = _docx_text(_report_path())
    assert FORMAL[:12] in text
    assert EVIDENCE[:12] in text
    assert PACKAGE_COMMIT[:12] in text
    assert "Final report synchronization" in text
    snapshot = json.loads(
        (ROOT / "outputs/audits/E1_R2_FINAL_REPORT_INPUT_SNAPSHOT.json").read_text(
            encoding="utf-8"
        )
    )
    sync = snapshot.get("final_report_synchronization_commit", "PENDING")
    assert sync != "PENDING" or "PENDING" in text
    names = allowed_names(PACKAGE)
    assert f"{PACKAGE}_REPORT.docx" in names
    assert "FINAL_DELIVERABLE_HASHES.json" not in names

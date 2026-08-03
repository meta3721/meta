"""Focused tests for the E1-R2 formal freeze-seal evidence exporter."""
from __future__ import annotations

import hashlib
import json
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from export_e1_r2_formal_freeze_seal_evidence import (  # noqa: E402
    HASH_JSON_NAME,
    HASH_TEXT_NAME,
    README_NAME,
    REPORT_NAME,
    REPORT_SECTIONS,
    ZIP_NAME,
    export_evidence,
)


def _write(path: Path, content: str = "{}\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _heading_two_text(path: Path) -> list[str]:
    namespace = {
        "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    }
    with zipfile.ZipFile(path) as archive:
        tree = ElementTree.fromstring(archive.read("word/document.xml"))
    headings = []
    for paragraph in tree.findall(".//w:p", namespace):
        style = paragraph.find("./w:pPr/w:pStyle", namespace)
        if style is None:
            continue
        style_name = style.get(f"{{{namespace['w']}}}val")
        if style_name not in {"Heading2", "Heading 2"}:
            continue
        headings.append(
            "".join(
                node.text or ""
                for node in paragraph.findall(".//w:t", namespace)
            )
        )
    return headings


def _complete_fixture(root: Path) -> None:
    files = {
        "outputs/audits/E1_R2_SOURCE_IDENTITY.json": "{}\n",
        "outputs/audits/E1_R2_SOURCE_EQUIVALENCE.json": "{}\n",
        "outputs/audits/E1_R2_PROVENANCE.json": "{}\n",
        "outputs/audits/E1_R2_PRE_EXPORT_HASHES.json": "{}\n",
        "outputs/audits/E1_R2_POST_EXPORT_HASHES.json": "{}\n",
        "configs/frozen/e1_r2_protocol.yaml": "formal_runs: 0\n",
        "configs/frozen/E1_R2_FROZEN_CONFIG_MANIFEST.json": "{}\n",
        "scripts/run_e1_r2_formal.py": "raise SystemExit('must not run')\n",
        "scripts/check_e1_r2_formal_freeze_seal_gates.py": "# source\n",
        "outputs/audits/E1_R2_SMOKE.json": '{"status": "PASS"}\n',
        "outputs/audits/E1_R2_AGGREGATE_REJECTION.json": "{}\n",
        "logs/E1_R2_JUNIT.xml": "<testsuite/>\n",
        "logs/E1_R2_FORMAL_FREEZE.log": "export only\n",
        "outputs/preflight/E1_R2_PREFLIGHT.json": '{"status": "PASS"}\n',
        "outputs/audits/E1_R2_FORMAL_SEED_NONINSPECTION.json": (
            '{"status": "PASS", "formal_seed_training_records": 0}\n'
        ),
        "data/frozen/e1_r2/formal/ROLE_MANIFEST.json": "{}\n",
        "outputs/audits/E1_R2_R2FS_GATE_REPORT.json": '{"status": "PASS"}\n',
        "outputs/audits/E1_R2_SOURCE_SNAPSHOT.zip": "snapshot\n",
        "outputs/audits/E1_R2_SOURCE_BUNDLE.zip": "bundle\n",
        "outputs/audits/E1_R2_SOURCE_DIFF.patch": "diff\n",
    }
    for relative, content in files.items():
        _write(root / relative, content)


def test_partial_export_before_prerequisites_creates_all_uploads(
    tmp_path: Path,
) -> None:
    deliverables = tmp_path / "deliverables"

    result = export_evidence(tmp_path, deliverables)

    assert result["status"] == "PARTIAL"
    assert result["formal_runs_completed"] == 0
    assert result["missing_prerequisites"]
    for name in (
        ZIP_NAME,
        REPORT_NAME,
        README_NAME,
        HASH_JSON_NAME,
        HASH_TEXT_NAME,
    ):
        assert (deliverables / name).is_file()
    assert "status=PARTIAL" in (
        deliverables / README_NAME
    ).read_text(encoding="utf-8")


def test_complete_export_has_23_sections_and_packages_required_evidence(
    tmp_path: Path,
) -> None:
    _complete_fixture(tmp_path)
    deliverables = tmp_path / "upload"

    result = export_evidence(tmp_path, deliverables)

    assert result["status"] == "COMPLETE"
    headings = _heading_two_text(deliverables / REPORT_NAME)
    assert headings == list(REPORT_SECTIONS)
    assert len(headings) == 23

    with zipfile.ZipFile(deliverables / ZIP_NAME) as archive:
        names = set(archive.namelist())
    assert REPORT_NAME in names
    assert README_NAME in names
    assert HASH_JSON_NAME not in names
    assert HASH_TEXT_NAME not in names
    assert "outputs/audits/E1_R2_SOURCE_SNAPSHOT.zip" in names
    assert "outputs/audits/E1_R2_SOURCE_BUNDLE.zip" in names
    assert "outputs/audits/E1_R2_SOURCE_DIFF.patch" in names
    assert "scripts/run_e1_r2_formal.py" in names
    assert "outputs/audits/E1_R2_R2FS_GATE_REPORT.json" in names


def test_final_hash_manifest_matches_exact_upload_artifacts(
    tmp_path: Path,
) -> None:
    _complete_fixture(tmp_path)
    deliverables = tmp_path / "upload"

    export_evidence(tmp_path, deliverables)

    payload = json.loads(
        (deliverables / HASH_JSON_NAME).read_text(encoding="utf-8")
    )
    expected_names = {ZIP_NAME, REPORT_NAME, README_NAME}
    assert set(payload["artifacts"]) == expected_names
    for name in expected_names:
        artifact = deliverables / name
        assert payload["artifacts"][name]["sha256"] == _sha256(artifact)
        assert payload["artifacts"][name]["size_bytes"] == artifact.stat().st_size

    text_lines = (
        deliverables / HASH_TEXT_NAME
    ).read_text(encoding="utf-8").splitlines()
    assert {
        line.split("  ", 1)[1] for line in text_lines
    } == expected_names

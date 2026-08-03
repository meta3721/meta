"""Unit tests for two-layer final package hash design."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from build_e1_r2_internal_evidence_manifest import EXCLUDE_NAMES  # noqa: E402
from build_final_deliverable_hashes import allowed_names  # noqa: E402


def test_internal_manifest_excludes_self_and_external_hashes() -> None:
    assert "INTERNAL_EVIDENCE_MANIFEST.json" in EXCLUDE_NAMES
    assert "FINAL_DELIVERABLE_HASHES.json" in EXCLUDE_NAMES


def test_external_hashes_do_not_include_self() -> None:
    names = allowed_names("E1_R2_FINAL_PACKAGE_AND_PRESENTATION_FIX_R1")
    assert "FINAL_DELIVERABLE_HASHES.json" not in names
    assert "FINAL_DELIVERABLE_HASHES.txt" not in names
    assert any(n.endswith("_EVIDENCE.zip") for n in names)

"""Integration tests for E1-R2 results evidence seal fix."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))


@pytest.mark.skipif(
    not (ROOT / "outputs/audits/E1_R2_RESULTS_EVIDENCE_FIX_IMMUTABILITY_CHECK.json").is_file(),
    reason="immutability fix check not generated",
)
def test_immutability_fix_pass() -> None:
    payload = json.loads(
        (ROOT / "outputs/audits/E1_R2_RESULTS_EVIDENCE_FIX_IMMUTABILITY_CHECK.json").read_text(
            encoding="utf-8",
        )
    )
    assert payload["status"] == "PASS"
    assert payload["hash_mismatch_count"] == 0
    assert payload["formal_run_count"] == 25


@pytest.mark.skipif(
    not (ROOT / "outputs/statistics/E1_R2_FINAL_SEALED/holm_family_registry.json").is_file(),
    reason="holm family registry missing",
)
def test_holm_family_registry_metric_mode() -> None:
    payload = json.loads(
        (ROOT / "outputs/statistics/E1_R2_FINAL_SEALED/holm_family_registry.json").read_text(
            encoding="utf-8",
        )
    )
    assert payload["family_mode"] == "metric"
    assert payload["n_families"] == 5


def test_final_deliverable_hashes_no_self_reference_helper() -> None:
    from build_final_deliverable_hashes import ALLOWED_PREFIXES

    assert "FINAL_DELIVERABLE_HASHES.json" not in ALLOWED_PREFIXES
    assert "FINAL_DELIVERABLE_HASHES.txt" not in ALLOWED_PREFIXES

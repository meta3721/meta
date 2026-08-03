"""Integration checks for final package artifacts."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(
    not (ROOT / "outputs/audits/E1_R2_FINAL_PACKAGE_IMMUTABILITY_CHECK.json").is_file(),
    reason="final package immutability check missing",
)
def test_final_package_immutability_pass() -> None:
    payload = json.loads(
        (ROOT / "outputs/audits/E1_R2_FINAL_PACKAGE_IMMUTABILITY_CHECK.json").read_text(encoding="utf-8")
    )
    assert payload["status"] == "PASS"
    assert payload["hash_mismatch_count"] == 0


@pytest.mark.skipif(
    not (ROOT / "outputs/paper/E1_R2_CAMERA_READY/tables/table_e1_main_metrics.csv").is_file(),
    reason="camera-ready tables missing",
)
def test_camera_ready_main_table_uses_short_names() -> None:
    text = (ROOT / "outputs/paper/E1_R2_CAMERA_READY/tables/table_e1_main_metrics.csv").read_text(encoding="utf-8")
    assert "flamf_timealign_adapted" not in text
    assert "TimeAlign" in text
    assert "RAVEN" in text

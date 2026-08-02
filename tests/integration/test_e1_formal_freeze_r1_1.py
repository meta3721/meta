from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_r1_1_preflight_artifact_if_present() -> None:
    path = ROOT / "outputs/preflight/E1_FORMAL_FREEZE_R1_1_PREFLIGHT.json"
    if not path.exists():
        return
    report = json.loads(path.read_text(encoding="utf-8"))
    assert report["execution_candidate_commit"].startswith("bb597a1")
    assert report["formal_25_runs_started"] is False


def test_no_formal_runs_started() -> None:
    runs = ROOT / "outputs/runs"
    formal = list(runs.glob("E1_FORMAL_*")) if runs.exists() else []
    assert formal == []


def test_eventtrace_and_validation_raw_evidence_present() -> None:
    assert (
        ROOT / "evidence/eventtrace/EVENTTRACE_RECOMPUTE_SUMMARY.json"
    ).exists()
    assert (
        ROOT / "evidence/validation/VALIDATION_RECOMPUTE_SUMMARY.json"
    ).exists()

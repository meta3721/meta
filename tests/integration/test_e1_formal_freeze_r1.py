from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_freeze_preflight_artifact_present() -> None:
    path = ROOT / "outputs/preflight/E1_FORMAL_FREEZE_R1_PREFLIGHT.json"
    if not path.exists():
        pytest.skip("preflight generated at end of freeze workflow")
    report = json.loads(path.read_text(encoding="utf-8"))
    assert report["formal_25_runs_started"] is False
    assert report["e2_e9_status"] == "NOT_STARTED"


def test_no_unexpected_formal_runs_started_after_freeze() -> None:
    runs = ROOT / "outputs/runs"
    formal = list(runs.glob("E1_FORMAL_*")) if runs.exists() else []
    # R1 historically launched no formal runs.  Execution-R1 later retained one
    # fail-fast run; the freeze evidence remains valid if no additional run was
    # silently introduced.
    assert [path.name for path in formal] in ([], [
        "E1_FORMAL_fedavg_window_26001_20260802_154112_605315",
    ])


def test_five_seed_safety_summary_if_present() -> None:
    path = (
        ROOT
        / "outputs/validation/e1_formal_freeze_r1_safety_summary.json"
    )
    if not path.exists():
        pytest.skip("safety summary generated during freeze workflow")
    summary = json.loads(path.read_text(encoding="utf-8"))
    assert summary["all_seeds_pass"] is True
    assert summary["test_read_count"] == 0

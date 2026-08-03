"""Regression checks for read-only E1 weight-safety diagnostics."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs/diagnostics"


def test_current_clip_rate_reproduces_failed_run() -> None:
    audit = json.loads((OUT / "E1_WEIGHT_SAFETY_RECONSTRUCTION_AUDIT.json").read_text())
    assert audit["reproduction_match"] is True
    assert abs(audit["recomputed_production_at_or_above_macro"] - 0.06371428571428571) <= 1e-12


def test_true_exceed_excludes_exact_boundary() -> None:
    records = pd.read_parquet(OUT / "E1_WEIGHT_SAFETY_RECORD_LEVEL.parquet")
    assert not (records["true_exceed"] & records["exact_boundary"]).any()


def test_at_or_above_includes_boundary() -> None:
    records = pd.read_parquet(OUT / "E1_WEIGHT_SAFETY_RECORD_LEVEL.parquet")
    assert records.loc[records["exact_boundary"], "at_or_above"].all()
    assert records.loc[records["true_exceed"], "at_or_above"].all()


def test_hash_semantics_atomic_vs_client_stratum() -> None:
    semantics = json.loads((OUT / "E1_TARGET_HASH_SEMANTICS.json").read_text())
    assert semantics["field_names_are_distinct"] is True
    assert semantics["atomic_target_weight_hash"]["object_definition"] != semantics[
        "client_stratum_target_mass_hash"
    ]["object_definition"]


def test_diag_keeps_formal_status_honest() -> None:
    gates = json.loads((OUT / "E1_WEIGHT_SAFETY_DIAG_GATE_REPORT.json").read_text())
    assert gates["formal_runs_completed"] == 1
    assert gates["formal_runs_admitted"] == 0
    assert gates["E2_E9"] == "NOT_STARTED"

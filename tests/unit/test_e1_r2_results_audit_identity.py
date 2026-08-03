"""Unit tests for E1-R2 results audit identity and semantics."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))


def _load(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_sealed_statistics_uses_five_paired_seeds() -> None:
    stats_dir = ROOT / "outputs/statistics/E1_R2_SEALED"
    if not stats_dir.is_dir():
        stats_dir = ROOT / "outputs/statistics/E1_R2"
    wilcoxon = stats_dir / "wilcoxon_results.csv"
    if not wilcoxon.is_file():
        pytest.skip("wilcoxon results missing")
    frame = pd.read_csv(wilcoxon)
    assert int(frame["n"].max()) == 5


def test_holm_results_nonempty() -> None:
    stats_dir = ROOT / "outputs/statistics/E1_R2_SEALED"
    if not stats_dir.is_dir():
        stats_dir = ROOT / "outputs/statistics/E1_R2"
    holm = stats_dir / "holm_results.csv"
    if not holm.is_file():
        pytest.skip("holm results missing")
    frame = pd.read_csv(holm)
    assert not frame.empty
    assert "holm_adjusted_p" in frame.columns


def test_no_seed_removal() -> None:
    aggregate = ROOT / "outputs/aggregate/E1_R2/per_seed_metrics.parquet"
    if not aggregate.is_file():
        pytest.skip("aggregate missing")
    frame = pd.read_parquet(aggregate)
    assert set(frame["seed"].astype(int)) == {28001, 28002, 28003, 28004, 28005}
    assert len(frame) == 25


def test_immutable_run_hashes() -> None:
    manifest = ROOT / "outputs/audits/E1_R2_25_RUNS_FROZEN_HASH_MANIFEST.json"
    if not manifest.is_file():
        pytest.skip("frozen hash manifest not generated")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload.get("run_count") == 25
    assert payload.get("status") == "PASS"


def test_original_run_directories_unchanged() -> None:
    summary = ROOT / "outputs/audits/E1_R2_FORMAL_RUN_IMMUTABILITY_SUMMARY.json"
    if not summary.is_file():
        pytest.skip("immutability summary not generated")
    payload = json.loads(summary.read_text(encoding="utf-8"))
    assert payload.get("original_run_files_modified") == 0


def test_solver_fallback_summary_matches_raw_rows() -> None:
    run_root = ROOT / "outputs/runs/E1_R2"
    if not run_root.is_dir():
        pytest.skip("formal runs missing")
    solver_mod = _load("audit_e1_r2_solver_fallback")
    result = solver_mod.audit(run_root, root=ROOT)
    summary = pd.read_csv(ROOT / "outputs/audits/E1_R2_RAVEN_SOLVER_SUMMARY.csv")
    for row in summary.itertuples(index=False):
        run_dir = Path(row.run_dir)
        raw = pd.read_parquet(run_dir / "solver_diagnostics.parquet")
        assert int(raw["fallback_used"].astype(bool).sum()) == int(row.fallback_invoked_count)
    assert result["status"] == "PASS"


def test_communication_metric_named_updates() -> None:
    comm_mod = _load("audit_e1_r2_communication_metric")
    run_root = ROOT / "outputs/runs/E1_R2"
    if not run_root.is_dir():
        pytest.skip("formal runs missing")
    payload = comm_mod.audit(run_root, root=ROOT)
    assert payload["is_byte_count"] is False
    assert payload["semantic"] == "number_of_received_client_updates"


def test_report_rejects_significance_overclaim() -> None:
    text_mod = _load("build_e1_r2_results_text")
    recompute = ROOT / "outputs/audits/E1_R2_FORMAL_RESULTS_INDEPENDENT_RECOMPUTE.json"
    if not recompute.is_file():
        pytest.skip("recompute audit missing")
    result = text_mod.build_text(ROOT)
    tex = (ROOT / "outputs/paper/E1_R2/E1_R2_RESULTS_TEXT.tex").read_text(encoding="utf-8")
    assert "significantly outperforms all baselines" not in tex.lower()
    assert result["status"] == "PASS"


def test_report_rejects_best_rmse_overclaim() -> None:
    tex = ROOT / "outputs/paper/E1_R2/E1_R2_RESULTS_TEXT.tex"
    if not tex.is_file():
        pytest.skip("results text missing")
    content = tex.read_text(encoding="utf-8").lower()
    assert "best rmse" not in content
    assert "second-lowest" in content

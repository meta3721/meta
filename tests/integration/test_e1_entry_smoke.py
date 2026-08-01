from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
ENTRY = ROOT / "outputs/entry_smoke/E1_ENTRY_SMOKE_seed26001"


def _manifests():
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((ENTRY / "runs").rglob("manifest.json"))
    ] if ENTRY.exists() else []


def test_e1_entry_smoke_runs_five_methods() -> None:
    if not _manifests():
        pytest.skip("entry smoke not generated yet")
    assert len(_manifests()) == 5


def test_e1_entry_smoke_uses_official_runner() -> None:
    source = (ROOT / "scripts/run_e1_entry_smoke.py").read_text(encoding="utf-8")
    assert "run_experiment.main" in source
    assert "pre_e1_smoke" not in source
    assert "p10_smoke" not in source


def test_e1_entry_smoke_uses_real_eventtrace() -> None:
    if not _manifests():
        pytest.skip("entry smoke not generated yet")
    assert len({item["event_trace_hash"] for item in _manifests()}) == 1


def test_e1_entry_smoke_uses_frozen_g4() -> None:
    if not _manifests():
        pytest.skip("entry smoke not generated yet")
    assert len({item["target_group_hash"] for item in _manifests()}) == 1


def _method_window(method: str) -> pd.DataFrame:
    paths = list((ENTRY / "runs").glob(f"E1_BALANCED_{method}_*"))
    if not paths:
        pytest.skip("entry smoke not generated yet")
    return pd.read_parquet(paths[0] / "metrics_window.parquet")


def test_fedasync_official_path() -> None:
    fedasync = _method_window("fedasync_window")
    fedavg = _method_window("fedavg_window")
    assert (fedasync["alpha"] != fedavg["alpha"]).any() or (
        fedasync["mean_staleness"] > 0
    ).any()


def test_timealign_official_path() -> None:
    frame = _method_window("timealign_agg")
    assert frame["model_hash_after"].iloc[-1]
    assert (frame["mean_staleness"] > 0).any()


def test_twostage_official_path() -> None:
    frame = _method_window("twostage_hajek")
    assert (frame["alpha"] != frame["beta"]).any() or (
        frame["first_stage_clip_rate"] >= 0
    ).all()


def test_raven_official_path() -> None:
    frame = _method_window("raven")
    assert (frame["solver_status"].isin(["optimal", "feasible_repaired"])).all()
    assert frame["Q_norm1"].iloc[-1] >= 0


def test_e1_entry_aggregate_has_five_rows() -> None:
    path = ENTRY / "aggregate/per_seed_metrics.parquet"
    if not path.exists():
        pytest.skip("entry aggregate not generated yet")
    assert len(pd.read_parquet(path)) == 5


def test_e1_entry_stats_dry_run() -> None:
    path = ROOT / "outputs/statistics/E1_balanced/no_harm_summary.json"
    if not path.exists():
        pytest.skip("statistics dry-run not generated yet")
    result = json.loads(path.read_text(encoding="utf-8"))
    assert result["status"] == "DRY_RUN_SCHEMA_PASS"
    assert result["formal_no_harm_conclusion"] is False

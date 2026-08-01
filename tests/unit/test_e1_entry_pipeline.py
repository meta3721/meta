from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load_script(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


aggregate_results = _load_script("aggregate_results")
select_baseline = _load_script("select_e1_baseline")
statistical_tests = _load_script("statistical_tests")


def _entry_root() -> Path:
    return ROOT / "outputs/entry_smoke/E1_ENTRY_SMOKE_seed26001"


def _run_dirs() -> list[Path]:
    root = _entry_root() / "runs"
    return sorted(path.parent for path in root.rglob("manifest.json")) if root.exists() else []


def test_aggregate_produces_per_seed_metrics() -> None:
    path = _entry_root() / "aggregate/per_seed_metrics.parquet"
    if not path.exists():
        pytest.skip("official entry smoke not generated yet")
    frame = pd.read_parquet(path)
    assert len(frame) == 5


def test_aggregate_rejects_duplicate_method_seed() -> None:
    frame = pd.DataFrame([
        {"seed": 26001, "method": method, "status": "completed",
         "run_id": method, "git_commit": "a", "config_hash": "b",
         "target_group_hash": "b", "event_trace_hash": "c",
         **{column: 1.0 for column in aggregate_results.PER_SEED_COLUMNS
            if column not in {"seed", "method", "status", "run_id",
                              "git_commit", "config_hash", "event_trace_hash"}}}
        for method in aggregate_results.E1_METHODS
    ])
    frame = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
    with pytest.raises(RuntimeError, match="duplicate"):
        aggregate_results.validate_rows(frame, mode="entry-smoke")


def test_aggregate_rejects_missing_method() -> None:
    frame = pd.DataFrame({
        "seed": [26001] * 4,
        "method": list(aggregate_results.E1_METHODS[:4]),
    })
    with pytest.raises(RuntimeError, match="method set"):
        aggregate_results.validate_rows(frame, mode="entry-smoke")


def test_aggregate_rejects_hash_mismatch() -> None:
    path = _entry_root() / "aggregate/per_seed_metrics.parquet"
    if not path.exists():
        pytest.skip("official entry smoke not generated yet")
    frame = pd.read_parquet(path)
    frame["target_group_hash"] = "same"
    frame.loc[frame.index[0], "config_hash"] = "different"
    with pytest.raises(RuntimeError, match="config_hash"):
        aggregate_results.validate_rows(frame, mode="entry-smoke")


def test_aggregate_aligns_methods_by_seed() -> None:
    path = _entry_root() / "aggregate/per_seed_metrics.parquet"
    if not path.exists():
        pytest.skip("official entry smoke not generated yet")
    frame = pd.read_parquet(path)
    assert set(frame["method"]) == set(aggregate_results.E1_METHODS)
    assert set(frame["seed"]) == {26001}


def test_aggregate_records_failed_runs() -> None:
    path = _entry_root() / "aggregate/failed_runs.csv"
    if not path.exists():
        pytest.skip("official entry smoke not generated yet")
    assert list(pd.read_csv(path).columns) == ["run_dir", "error"]


def test_e1_baseline_selected_from_validation_only() -> None:
    frame = pd.DataFrame({
        "method": list(select_baseline.CANDIDATES),
        "split": ["validation"] * 3,
        "RMSE_mu": [2.0, 1.5, 1.8],
    })
    assert select_baseline.choose_baseline(frame) == "fedasync_window"


def test_e1_baseline_selection_ignores_test() -> None:
    frame = pd.DataFrame({
        "method": list(select_baseline.CANDIDATES),
        "split": ["test"] * 3,
        "RMSE_mu": [1.0, 2.0, 3.0],
    })
    with pytest.raises(RuntimeError, match="validation only"):
        select_baseline.choose_baseline(frame)


def test_e1_baseline_selection_frozen() -> None:
    path = ROOT / "configs/frozen/e1_selected_baseline.yaml"
    if not path.exists():
        pytest.skip("validation selection not generated yet")
    text = path.read_text(encoding="utf-8")
    assert "selected_baseline:" in text
    assert "validation_split_only: true" in text


def test_statistical_tests_read_selected_baseline() -> None:
    source = (ROOT / "scripts/statistical_tests.py").read_text(encoding="utf-8")
    assert "e1_selected_baseline.yaml" in source
    assert "baseline_method = args.baseline or selected.get" in source


def test_test_stage_cannot_change_selected_baseline() -> None:
    frame = pd.DataFrame({
        "method": list(select_baseline.CANDIDATES),
        "split": ["test"] * 3,
        "RMSE_mu": [1.0, 2.0, 3.0],
    })
    with pytest.raises(RuntimeError):
        select_baseline.choose_baseline(frame)


def test_no_harm_uses_selected_baseline() -> None:
    path = ROOT / "outputs/statistics/E1_balanced/no_harm_summary.json"
    if not path.exists():
        pytest.skip("statistics dry-run not generated yet")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["baseline_source"].endswith("e1_selected_baseline.yaml")


def test_no_harm_uses_paired_seed_values() -> None:
    with pytest.raises(ValueError, match="Seed count mismatch"):
        statistical_tests._no_harm_test([1.0], [1.0, 2.0])


def test_no_harm_relative_degradation_formula() -> None:
    result = statistical_tests._no_harm_test([10.0], [10.2])
    assert result["relative_degradation_mean"] == pytest.approx(0.02)


def test_no_harm_single_seed_is_dry_run_only() -> None:
    path = ROOT / "outputs/statistics/E1_balanced/no_harm_summary.json"
    if not path.exists():
        pytest.skip("statistics dry-run not generated yet")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["status"] == "DRY_RUN_SCHEMA_PASS"
    assert data["formal_no_harm_conclusion"] is False


def test_no_harm_rejects_missing_seed() -> None:
    frame = pd.DataFrame({
        "seed": [1, 2, 1],
        "method": ["fedavg_window", "fedavg_window", "raven"],
        "RMSE_mu": [1.0, 1.1, 1.0],
    })
    result = statistical_tests.compute_all_statistics(
        frame, baseline_method="fedavg_window", methods=["raven"],
        metric="RMSE_mu",
    )
    assert "seed_mismatch_raven" in result


def test_no_harm_rejects_seed_exclusion() -> None:
    baseline = [1.0, 1.1]
    raven = [1.0]
    with pytest.raises(ValueError):
        statistical_tests._no_harm_test(baseline, raven)


def test_official_e1_run_outputs_predictions() -> None:
    if not _run_dirs():
        pytest.skip("official entry smoke not generated yet")
    assert all((run / "predictions_test.parquet").exists() for run in _run_dirs())


def test_official_e1_run_outputs_metrics_run() -> None:
    if not _run_dirs():
        pytest.skip("official entry smoke not generated yet")
    assert all((run / "metrics_run.json").exists() for run in _run_dirs())


def test_official_e1_run_outputs_window_metrics() -> None:
    if not _run_dirs():
        pytest.skip("official entry smoke not generated yet")
    assert all((run / "metrics_window.parquet").exists() for run in _run_dirs())


def test_official_e1_gap_identity() -> None:
    if not _run_dirs():
        pytest.skip("official entry smoke not generated yet")
    for run in _run_dirs():
        metric = json.loads((run / "metrics_run.json").read_text())
        assert metric["Gap_mis"] == pytest.approx(
            metric["RMSE_mu"] - metric["RMSE_rho"], abs=1e-12,
        )


def test_official_e1_arrival_weights_atomic() -> None:
    if not _run_dirs():
        pytest.skip("official entry smoke not generated yet")
    for run in _run_dirs():
        frame = pd.read_parquet(run / "arrival_weights_test.parquet")
        assert frame["unit_id"].is_unique
        assert frame["arrival_weight"].sum() == pytest.approx(1.0)


def test_official_e1_artifact_completeness() -> None:
    if not _run_dirs():
        pytest.skip("official entry smoke not generated yet")
    required = {
        "manifest.json", "resolved_config.yaml", "event_trace_ref.json",
        "metrics_window.parquet", "metrics_run.json",
        "predictions_test.parquet", "arrival_weights_test.parquet",
        "propensity_diagnostics.parquet", "solver_diagnostics.parquet",
        "system_metrics.json", "method_diagnostics.parquet", "checkpoints",
        "stdout.log", "stderr.log",
    }
    assert all(all((run / item).exists() for item in required) for run in _run_dirs())


def test_official_e1_manifest_hashes() -> None:
    if not _run_dirs():
        pytest.skip("official entry smoke not generated yet")
    manifests = [json.loads((run / "manifest.json").read_text()) for run in _run_dirs()]
    assert len({item["event_trace_hash"] for item in manifests}) == 1
    assert len({item["target_group_hash"] for item in manifests}) == 1


def test_official_e1_solver_diagnostics() -> None:
    if not _run_dirs():
        pytest.skip("official entry smoke not generated yet")
    raven = [run for run in _run_dirs() if "_raven_" in run.name]
    assert len(raven) == 1
    frame = pd.read_parquet(raven[0] / "solver_diagnostics.parquet")
    assert len(frame) == 20
    assert frame["accepted_status"].isin(["optimal", "feasible_repaired"]).all()

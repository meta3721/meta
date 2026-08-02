from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
ENTRY = ROOT / "outputs/entry_r2_smoke"


def _r2_artifacts_frozen() -> bool:
    protocol = yaml.safe_load(
        (ROOT / "configs/frozen/e1_sensorscope_balanced.yaml").read_text(),
    )
    return protocol.get("semantic_seal_status") == "PASS"


def _runs() -> dict[str, Path]:
    result = {}
    for manifest_path in (ENTRY / "runs").rglob("manifest.json"):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        result[manifest["method"]] = manifest_path.parent
    return result


def test_r2_smoke_five_methods_and_shared_identities() -> None:
    runs = _runs()
    if not runs:
        pytest.skip("R2 smoke generated after formal commit")
    assert set(runs) == {
        "fedavg_window", "fedasync_window", "flamf_timealign_adapted",
        "twostage_hajek", "raven",
    }
    manifests = [
        json.loads((path / "manifest.json").read_text()) for path in runs.values()
    ]
    for field in (
        "data_hash", "target_group_hash", "client_mapping_hash",
        "pi_target_hash", "event_trace_hash", "initial_model_hash",
        "protocol_config_hash",
    ):
        assert len({item[field] for item in manifests}) == 1


def test_r2_timealign_official_difference() -> None:
    path = ENTRY / "timealign_fedasync_comparison.json"
    if not path.exists():
        pytest.skip("R2 smoke generated after formal commit")
    result = json.loads(path.read_text())
    assert result["max_l1_alpha_difference"] > 1e-10
    assert result["prediction_max_absolute_difference"] > 0


def test_r2_complete_artifacts_and_record_history() -> None:
    runs = _runs()
    if not runs:
        pytest.skip("R2 smoke generated after formal commit")
    required = {
        "manifest.json", "resolved_config.yaml", "event_trace_ref.json",
        "metrics_window.parquet", "metrics_run.json", "predictions_test.parquet",
        "arrival_weights_test.parquet", "propensity_diagnostics.parquet",
        "p_propensity_history.parquet", "solver_diagnostics.parquet",
        "method_diagnostics.parquet", "system_metrics.json", "checkpoints",
        "stdout.log", "stderr.log",
    }
    for run_dir in runs.values():
        assert all((run_dir / name).exists() for name in required)
        history = pd.read_parquet(run_dir / "p_propensity_history.parquet")
        assert len(history) > 0
        assert set(history["O"].unique()) == {0, 1}
        assert set(history["source_split"]) == {"train"}


def test_r2_aggregate_exactly_five_rows() -> None:
    path = ROOT / "outputs/aggregate/E1_balanced_entry_r2/per_seed_metrics.parquet"
    if not path.exists():
        pytest.skip("R2 aggregate generated after smoke")
    assert len(pd.read_parquet(path)) == 5


def test_trace_generation_commit_matches_final_commit() -> None:
    if not _r2_artifacts_frozen():
        pytest.skip("R2 traces generated only after formal clean commit")
    import subprocess

    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    manifests = [
        json.loads(
            (
                ROOT
                / f"outputs/event_traces/e1_balanced_seed{seed}"
                / "event_trace_manifest.json"
            ).read_text(),
        )
        for seed in range(26001, 26006)
    ]
    assert {item["generation_git_commit"] for item in manifests} == {commit}
    assert all(item["git_clean"] for item in manifests)
    assert all(item["clients"] == 8 for item in manifests)

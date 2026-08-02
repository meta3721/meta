from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]


def _commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
        capture_output=True, text=True,
    ).stdout.strip()


def _runs() -> dict[str, Path]:
    result = {}
    root = ROOT / f"outputs/entry_r3_smoke/runs_{_commit()[:12]}"
    for path in root.rglob("manifest.json"):
        manifest = json.loads(path.read_text())
        result[manifest["method"]] = path.parent
    return result


def test_r3_five_method_smoke_complete() -> None:
    runs = _runs()
    if not runs:
        pytest.skip("R3 smoke runs after formal clean commit")
    assert set(runs) == {
        "fedavg_window", "fedasync_window", "flamf_timealign_adapted",
        "twostage_hajek", "raven",
    }


def test_manifest_required_identity_fields() -> None:
    runs = _runs()
    if not runs:
        pytest.skip("R3 smoke runs after formal clean commit")
    required = {
        "git_commit", "protocol_config_hash", "resolved_run_config_hash",
        "data_hash", "target_group_payload_hash", "target_group_file_hash",
        "client_mapping_payload_hash", "client_mapping_file_hash",
        "pi_target_hash", "event_trace_hash", "initial_model_hash",
        "environment_hash",
    }
    for run in runs.values():
        manifest = json.loads((run / "manifest.json").read_text())
        assert required <= set(manifest)
        assert manifest["config_hash"] == manifest["resolved_run_config_hash"]


def test_trace_and_run_share_mapping_hashes() -> None:
    runs = _runs()
    if not runs:
        pytest.skip("R3 smoke runs after formal clean commit")
    trace = json.loads((
        ROOT / "outputs/event_traces/e1_balanced_seed26001"
        / "event_trace_manifest.json"
    ).read_text())
    for run in runs.values():
        manifest = json.loads((run / "manifest.json").read_text())
        assert manifest["client_mapping_payload_hash"] == (
            trace["client_mapping_payload_hash"]
        )
        assert manifest["client_mapping_file_hash"] == (
            trace["client_mapping_file_hash"]
        )


def test_r3_opportunity_and_support_artifacts_complete() -> None:
    runs = _runs()
    if not runs:
        pytest.skip("R3 smoke runs after formal clean commit")
    for run in runs.values():
        opportunity = pd.read_parquet(
            run / "opportunity_ema_diagnostics.parquet",
        )
        assert float(opportunity["formula_error"].max()) <= 1e-12
        support = json.loads(
            (run / "support_crosscheck_ref.json").read_text(),
        )["summary"]
        assert support["unsupported_positive_target_pairs"] == 0
        assert (run / "calibration_summary.json").exists()
        assert (run / "feature_encoding_manifest.json").exists()


def test_r3_aggregate_exactly_five_rows() -> None:
    path = (
        ROOT
        / "outputs/aggregate/E1_balanced_entry_r3/per_seed_metrics.parquet"
    )
    if not path.exists():
        pytest.skip("R3 aggregate generated after smoke")
    frame = pd.read_parquet(path)
    assert len(frame) == 5
    assert (
        frame["config_hash"] == frame["resolved_run_config_hash"]
    ).all()

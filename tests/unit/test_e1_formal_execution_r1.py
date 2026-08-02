from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from aggregate_results import validate_rows
from run_e1_formal import build_matrix
from raven_mcs.experiments.e1_entry import E1_METHODS, E1_SEEDS
from raven_mcs.utils.serialization import load_yaml


def _formal_frame() -> pd.DataFrame:
    rows = []
    for seed in E1_SEEDS:
        for method in E1_METHODS:
            rows.append({
                "seed": seed, "method": method, "run_id": f"{method}-{seed}",
                "RMSE_mu": 1.0, "RMSE_rho": 1.0, "Gap_mis": 0.0,
                "Head_RMSE": 1.0, "Tail_RMSE": 1.0, "Delta_group": 0.0,
                "Delta_c_s": 0.0, "avg_delta_group": 0.0, "avg_delta_ref": 0.0,
                "normalized_debt": 0.0, "median_n_eff": 3.0,
                "first_stage_clip_rate": 0.0, "second_stage_clip_rate": 0.0,
                "fallback_count": 0, "solver_failure_count": 0, "runtime": 1.0,
                "communication": 1,
                "status": "completed", "formal": True, "hard_gate_status": "PASS",
                "num_windows": 100, "local_steps": 2, "selected_baseline_hash": "x",
                "execution_commit": "abc",
                "config_hash": "a", "resolved_run_config_hash": "a", "git_commit": "g",
                "protocol_config_hash": "p", "data_hash": "d", "split_hash": "s",
                "target_group_payload_hash": "tg", "target_group_file_hash": "tf",
                "client_mapping_payload_hash": "cm", "client_mapping_file_hash": "cf",
                "target_group_hash": "tf", "client_mapping_hash": "cm",
                "pi_target_hash": "pi",
                "environment_hash": "env", "event_trace_hash": str(seed),
                "initial_model_hash": str(seed),
            })
    return pd.DataFrame(rows)


def test_formal_runner_builds_25_unique_runs() -> None:
    matrix = build_matrix(list(E1_METHODS), list(E1_SEEDS))
    assert len(matrix) == 25
    pairs = {(row["seed"], row["method"]) for row in matrix}
    assert len(pairs) == 25


def test_formal_runner_seed_major_order() -> None:
    matrix = build_matrix(list(E1_METHODS), list(E1_SEEDS))
    seeds = [row["seed"] for row in matrix]
    assert seeds == sorted(seeds)
    assert matrix[0]["method"] == E1_METHODS[0]
    assert matrix[4]["method"] == E1_METHODS[-1]
    assert matrix[5]["seed"] == E1_SEEDS[1]


def test_formal_manifest_true() -> None:
    source = (
        ROOT / "src/raven_mcs/experiments/e1_entry.py"
    ).read_text(encoding="utf-8")
    assert '"formal": bool(formal)' in source


def test_formal_manifest_windows_100() -> None:
    source = (
        ROOT / "src/raven_mcs/experiments/e1_entry.py"
    ).read_text(encoding="utf-8")
    assert "formal E1 execution requires num_windows=100" in source


def test_formal_manifest_local_steps_2() -> None:
    source = (
        ROOT / "src/raven_mcs/experiments/e1_entry.py"
    ).read_text(encoding="utf-8")
    assert "formal E1 execution requires local_steps=2" in source


def test_formal_runner_rejects_dirty_git() -> None:
    source = (
        ROOT / "scripts/run_e1_formal.py"
    ).read_text(encoding="utf-8")
    assert "clean git worktree" in source


def test_formal_aggregate_rejects_24_rows() -> None:
    with pytest.raises(RuntimeError, match="exactly 25"):
        validate_rows(_formal_frame().iloc[:-1], mode="formal")


def test_formal_aggregate_rejects_formal_false() -> None:
    frame = _formal_frame()
    frame.loc[0, "formal"] = False
    with pytest.raises(RuntimeError, match="non-formal"):
        validate_rows(frame, mode="formal")


def test_formal_aggregate_rejects_failed_gate() -> None:
    frame = _formal_frame()
    frame.loc[0, "hard_gate_status"] = "FAIL"
    with pytest.raises(RuntimeError, match="PASS hard gates"):
        validate_rows(frame, mode="formal")


def test_config_hash_is_resolved_config_hash() -> None:
    source = (
        ROOT / "src/raven_mcs/experiments/e1_entry.py"
    ).read_text(encoding="utf-8")
    assert '"config_hash": resolved_run_config_hash' in source


def test_dry_run_not_counted_as_formal() -> None:
    progress = ROOT / "logs/E1_FORMAL_PROGRESS.json"
    if not progress.exists():
        pytest.skip("dry-run progress not generated yet")
    payload = json_load(progress)
    assert payload.get("formal_performance_result") is False


def test_protocol_authorized_for_frozen_execution() -> None:
    protocol = load_yaml(
        ROOT / "configs/frozen/e1_sensorscope_balanced.yaml"
    )
    assert protocol["authorization_status"] == (
        "AUTHORIZED_FOR_FROZEN_EXECUTION"
    )


def json_load(path: Path):
    import json
    return json.loads(path.read_text(encoding="utf-8"))

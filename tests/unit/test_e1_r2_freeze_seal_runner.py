from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from aggregate_results import validate_rows
from e1_r2_common import (
    FORMAL_SEEDS,
    R2_SELECTED_A_MAX,
    R2_SELECTED_BASELINE,
    R2_SELECTED_CANDIDATE,
    validate_frozen_r2_selection,
)
from run_e1_formal import build_matrix
from raven_mcs.experiments.e1_entry import E1_METHODS


def _formal_frame() -> pd.DataFrame:
    rows = []
    for seed in FORMAL_SEEDS:
        for method in E1_METHODS:
            rows.append({
                "seed": seed,
                "method": method,
                "run_id": f"{method}-{seed}",
                "RMSE_mu": 1.0,
                "RMSE_rho": 1.0,
                "Gap_mis": 0.0,
                "Head_RMSE": 1.0,
                "Tail_RMSE": 1.0,
                "Delta_group": 0.0,
                "Delta_c_s": 0.0,
                "avg_delta_group": 0.0,
                "avg_delta_ref": 0.0,
                "normalized_debt": 0.0,
                "median_n_eff": 1.0,
                "first_stage_clip_rate": 0.99,
                "second_stage_clip_rate": 0.99,
                "fallback_count": 0,
                "solver_failure_count": 0,
                "runtime": 1.0,
                "communication": 1,
                "status": "completed",
                "formal": True,
                "hard_gate_status": "PASS",
                "num_windows": 100,
                "local_steps": 2,
                "selected_baseline_hash": "baseline-hash",
                "execution_commit": "head",
                "config_hash": "config",
                "resolved_run_config_hash": "config",
                "git_commit": "head",
                "protocol_config_hash": "protocol",
                "data_hash": "data",
                "split_hash": "split",
                "target_group_payload_hash": "target-payload",
                "target_group_file_hash": "target-file",
                "client_mapping_payload_hash": "client-payload",
                "client_mapping_file_hash": "client-file",
                "target_group_hash": "target-file",
                "client_mapping_hash": "client-payload",
                "pi_target_hash": "pi",
                "environment_hash": "environment",
                "event_trace_hash": str(seed),
                "initial_model_hash": str(seed),
                "protocol_version": "E1-R2",
                "seed_role": "formal",
                "smoke": False,
                "selected_candidate": "C2",
                "selected_baseline": "flamf_timealign_adapted",
                "a_max": 40.0,
                "opportunity_forgetting": 0.95,
                "c_clip_obs": 0.05,
                "first_stage_clip_observed_micro_true_exceed": 0.05,
                "clip_population": "observed_records",
                "clip_aggregation": "global_micro_per_seed",
                "clip_comparison": "u > a_max + 1e-12",
            })
    return pd.DataFrame(rows)


def test_frozen_r2_execution_selection_is_exact() -> None:
    frozen = validate_frozen_r2_selection(ROOT)
    assert frozen["selected_candidate"] == R2_SELECTED_CANDIDATE
    assert frozen["selected_baseline"] == R2_SELECTED_BASELINE
    assert frozen["parameters"]["a_max"] == R2_SELECTED_A_MAX
    assert frozen["parameters"]["opportunity_forgetting"] == 0.95


def test_r2_formal_matrix_is_seed_major_25() -> None:
    matrix = build_matrix(list(E1_METHODS), list(FORMAL_SEEDS))
    assert len(matrix) == 25
    assert [row["seed"] for row in matrix[:5]] == [28001] * 5
    assert matrix[-1] == {"seed": 28005, "method": E1_METHODS[-1]}


def test_r2_formal_aggregate_accepts_new_gate_despite_legacy_diagnostics() -> None:
    validate_rows(_formal_frame(), mode="formal")


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("protocol_version", "E1-R1", "R1/wrong protocol"),
        ("seed_role", "calibration", "calibration/validation"),
        ("smoke", True, "smoke"),
        ("formal", False, "non-formal"),
        ("num_windows", 2, "100 windows"),
        ("local_steps", 1, "two local steps"),
        ("a_max", 20.0, "a_max=40"),
        ("selected_baseline", "fedavg_window", "baseline"),
        ("c_clip_obs", None, "legacy-only"),
        ("hard_gate_status", "FAIL", "PASS hard gates"),
    ],
)
def test_r2_formal_aggregate_rejects_wrong_identity(
    column: str, value: object, message: str,
) -> None:
    frame = _formal_frame()
    frame.loc[0, column] = value
    with pytest.raises(RuntimeError, match=message):
        validate_rows(frame, mode="formal")


def test_r2_formal_aggregate_rejects_strict_exceed_failure() -> None:
    frame = _formal_frame()
    frame.loc[0, "c_clip_obs"] = 0.0500001
    frame.loc[
        0, "first_stage_clip_observed_micro_true_exceed"
    ] = 0.0500001
    with pytest.raises(RuntimeError, match="hard gate failed"):
        validate_rows(frame, mode="formal")

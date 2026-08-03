"""Focused tests for E1-R2 calibration/validation orchestration."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from check_e1_r2_calibration_gates import evaluate_calibration
from e1_r2_common import (
    CALIBRATION_SEEDS,
    FORMAL_SEEDS,
    R1_SEEDS,
    VALIDATION_SEEDS,
    compute_clip_metrics,
    reject_any_seed,
    run_r2_method,
    validate_seed_role,
)
from select_e1_r2_final_candidate import select_final_candidate
from select_e1_r2_validation_baseline import select_baseline


def _clip_fixture() -> tuple[pd.DataFrame, pd.DataFrame]:
    diagnostics = pd.DataFrame([
        {
            "window_id": 0,
            "client_id": "a",
            "zeta_hat": [2.0000000000002],
            "p_hat": [0.1],
        },
        {
            "window_id": 0,
            "client_id": "b",
            "zeta_hat": [1.0, 1.0, 1.0],
            "p_hat": [0.1, 0.1, 0.1],
        },
    ])
    history = pd.DataFrame([
        {"window_id": 0, "client_id": "a", "unit_id": "a1", "O": 1},
        {"window_id": 0, "client_id": "b", "unit_id": "b1", "O": 1},
        {"window_id": 0, "client_id": "b", "unit_id": "b2", "O": 1},
        {"window_id": 0, "client_id": "b", "unit_id": "b3", "O": 1},
    ])
    return diagnostics, history


def test_r2_clip_population_is_observed_global_micro() -> None:
    diagnostics, history = _clip_fixture()
    result = compute_clip_metrics(
        diagnostics, history, a_max=20.0, p_min=0.05,
    )
    assert result["clip_population"] == "observed_records"
    assert result["clip_aggregation"] == "global_micro_per_seed"
    assert result["observed_record_count"] == 4
    assert result["observed_exceed_count"] == 1
    assert result["c_clip_obs"] == pytest.approx(0.25)


def test_r2_true_exceed_is_strict_and_boundary_is_not_clipped() -> None:
    diagnostics = pd.DataFrame([{
        "window_id": 0,
        "client_id": "a",
        "zeta_hat": [2.0, 2.00000000000005, 2.0000000000002],
        "p_hat": [0.1, 0.1, 0.1],
    }])
    history = pd.DataFrame([
        {"window_id": 0, "client_id": "a", "unit_id": f"u{i}", "O": 1}
        for i in range(3)
    ])
    result = compute_clip_metrics(
        diagnostics, history, a_max=20.0, p_min=0.05,
    )
    assert result["observed_exceed_count"] == 1
    assert result["exact_boundary_rate"] == pytest.approx(2 / 3)
    assert result["clip_comparison"] == "u > a_max + 1e-12"


def test_r2_seed_roles_are_disjoint_and_exclude_r1() -> None:
    roles = [set(CALIBRATION_SEEDS), set(VALIDATION_SEEDS), set(FORMAL_SEEDS)]
    assert not roles[0] & roles[1]
    assert not roles[0] & roles[2]
    assert not roles[1] & roles[2]
    assert not set().union(*roles) & set(R1_SEEDS)
    assert validate_seed_role("calibration", CALIBRATION_SEEDS) == CALIBRATION_SEEDS
    with pytest.raises(ValueError):
        validate_seed_role("calibration", VALIDATION_SEEDS)


def test_r2_runner_rejects_formal_role_before_training(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="only for calibration/validation"):
        run_r2_method(
            ROOT,
            role="formal",
            method="raven",
            seed=FORMAL_SEEDS[0],
            custom_trace_dir=tmp_path,
            output_root=tmp_path / "runs",
        )


def test_calibration_rejects_any_seed_over_five_percent() -> None:
    rows = [
        {"seed": seed, "all_gates_pass": seed != CALIBRATION_SEEDS[-1]}
        for seed in CALIBRATION_SEEDS
    ]
    assert reject_any_seed(
        pd.DataFrame(rows), expected_seeds=CALIBRATION_SEEDS,
    ) is False
    rows[-1]["all_gates_pass"] = True
    assert reject_any_seed(
        pd.DataFrame(rows), expected_seeds=CALIBRATION_SEEDS,
    ) is True


def test_deterministic_baseline_selection_uses_registered_ties() -> None:
    rows = []
    for method in (
        "fedavg_window", "fedasync_window", "flamf_timealign_adapted",
    ):
        for seed in VALIDATION_SEEDS:
            rows.append({
                "method": method,
                "seed": seed,
                "RMSE_mu": 1.0,
                "Tail_RMSE": 2.0,
                "total_runtime": 3.0,
            })
    selected, _ = select_baseline(pd.DataFrame(rows))
    assert selected == "fedavg_window"


def test_deterministic_final_selection_applies_a_max_tie_break() -> None:
    rows = []
    for candidate, a_max in (("C1", 30.0), ("C2", 40.0)):
        for seed in VALIDATION_SEEDS:
            rows.append({
                "candidate": candidate,
                "seed": seed,
                "RMSE_mu": 1.0,
                "a_max": a_max,
                "c_clip_obs": 0.01,
                "median_n_eff": 3.0,
            })
    selected, _ = select_final_candidate(pd.DataFrame(rows), ["C2", "C1"])
    assert selected == "C1"


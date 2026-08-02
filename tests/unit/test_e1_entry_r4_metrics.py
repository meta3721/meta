from __future__ import annotations

import numpy as np

from raven_mcs.metrics.accuracy import gap_mis, rmse_rho, tail_head_rmse


def test_r4_rmse_rho_recomputed_after_support_fix() -> None:
    predicted = np.array([0.0, 2.0])
    truth = np.array([0.0, 0.0])
    fixed_arrival = np.array([0.75, 0.25])
    assert rmse_rho(predicted, truth, fixed_arrival) == 1.0


def test_r4_gap_identity() -> None:
    assert gap_mis(2.5, 1.25) == 2.5 - 1.25


def test_r4_tail_head_positive_support() -> None:
    result = tail_head_rmse(
        np.array([1.0, 2.0]), np.array([0.0, 0.0]),
        np.array([0.5, 0.5]), np.array([0.5, 2.0]),
        np.array([0, 1]), np.array([0.5, 0.5]),
    )
    assert np.isfinite(result["tail_rmse"])
    assert np.isfinite(result["head_rmse"])


def test_r4_empty_tail_fails() -> None:
    result = tail_head_rmse(
        np.array([]), np.array([]), np.array([]), np.array([]),
        np.array([], dtype=int), np.array([]),
    )
    assert np.isnan(result["tail_rmse"])


def test_r4_target_arrival_l1_recomputed() -> None:
    target = np.array([0.5, 0.5])
    arrival = np.array([0.75, 0.25])
    assert float(np.abs(target - arrival).sum()) == 0.5

from __future__ import annotations

import inspect
import ast

import numpy as np

from raven_mcs.opportunities.estimator import OpportunityEstimator
from raven_mcs.training.window_runner import FullWindowRunner


def test_opportunity_ema_once_per_window() -> None:
    estimator = OpportunityEstimator(
        forgetting=0.95, smoothing=0, c_prior=0,
        counts={("A", "s"): 100.0},
    )
    estimator.update_window(2, {("A", "s"): 10})
    assert estimator.counts[("A", "s")] == 105.0
    assert len(estimator.diagnostics) == 1


def test_opportunity_ema_not_once_per_record() -> None:
    estimator = OpportunityEstimator(
        forgetting=0.95, smoothing=0, c_prior=0,
        counts={("A", "s"): 100.0},
    )
    estimator.update_window(2, {("A", "s"): 10})
    record_recursive = 100.0
    for _ in range(10):
        record_recursive = 0.95 * record_recursive + 1
    assert estimator.counts[("A", "s")] != record_recursive


def test_opportunity_ema_manual_multi_record_case() -> None:
    estimator = OpportunityEstimator(
        forgetting=0.95, smoothing=0, c_prior=0,
        counts={("A", "s"): 100.0},
    )
    estimator.update_window(0, {("A", "s"): 10.0})
    np.testing.assert_allclose(estimator.counts[("A", "s")], 105.0)


def test_zero_count_strata_decay_once() -> None:
    estimator = OpportunityEstimator(
        forgetting=0.9, smoothing=0, c_prior=0,
        counts={("A", "s"): 50.0},
    )
    estimator.update_window(0, {})
    assert estimator.counts[("A", "s")] == 45.0
    assert estimator.diagnostics[0]["zero_count_decay_applied"] is True


def test_new_strata_added_after_window_close() -> None:
    estimator = OpportunityEstimator(
        forgetting=0.9, smoothing=0, c_prior=0,
    )
    estimator.update_window(0, {("A", "new"): 3})
    assert estimator.counts[("A", "new")] == 3.0


def test_current_window_not_used_for_current_zeta() -> None:
    source = inspect.getsource(FullWindowRunner._process_window)
    assert source.index("zeta = self._compute_zeta") < source.rindex(
        "self._update_lagged_estimators",
    )


def test_opportunity_mass_normalizes_to_one() -> None:
    estimator = OpportunityEstimator(
        forgetting=0.5, smoothing=0, c_prior=0,
        counts={("A", "s1"): 2.0, ("B", "s2"): 3.0},
    )
    estimator.update_window(0, {("A", "s1"): 1, ("B", "s3"): 4})
    assert abs(float(estimator.pi_hat().sum()) - 1.0) <= 1e-12


def test_no_always_true_ema_assertion() -> None:
    source = inspect.getsource(inspect.getmodule(test_opportunity_ema_once_per_window))
    tree = ast.parse(source)
    weak = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Assert)
        and isinstance(node.test, ast.BoolOp)
        and isinstance(node.test.op, ast.Or)
        and any(
            isinstance(value, ast.Constant) and value.value is True
            for value in node.test.values
        )
    ]
    assert weak == []

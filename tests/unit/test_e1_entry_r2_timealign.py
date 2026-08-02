from __future__ import annotations

import inspect
from pathlib import Path

import numpy as np
import pytest

from raven_mcs.aggregation.base import WindowAggregateInput
from raven_mcs.aggregation.methods import (
    FLAMFTimeAlignAdaptedAggregator,
    FedAsyncWindowAggregator,
    get_aggregator,
)

ROOT = Path(__file__).resolve().parents[2]


def _payload(
    coverage: dict[str, list[int]],
    tau: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> WindowAggregateInput:
    return WindowAggregateInput(
        client_ids=["A", "B", "C"],
        raw_counts=np.array([3.0, 2.0, 1.0]),
        total_masses=np.ones(3),
        compositions=np.full((4, 3), 0.25),
        staleness=np.asarray(tau),
        extras={"covered_time_slots": coverage},
    )


def test_timealign_adapted_spec_exists() -> None:
    text = (
        ROOT / "docs/baselines/FLAMF_TIMEALIGN_ADAPTED_SPEC.md"
    ).read_text(encoding="utf-8")
    assert "common-backbone adaptation" in text
    assert "not the original FLAMF implementation" in text


def test_timealign_uses_timestamp_coverage() -> None:
    alpha = FLAMFTimeAlignAdaptedAggregator().compute_server_weights(
        _payload({"A": [1, 2, 3], "B": [1, 2], "C": [4]}),
    )
    np.testing.assert_allclose(alpha, np.array([2.0, 1.0, 1.0]) / 4.0)


def test_timealign_not_uses_exp_staleness_formula() -> None:
    source = inspect.getsource(
        FLAMFTimeAlignAdaptedAggregator.compute_server_weights,
    )
    assert "np.exp" not in source
    assert "staleness" not in source


def test_timealign_differs_from_fedasync_on_overlap_fixture() -> None:
    payload = _payload({"A": [1, 2, 3], "B": [1, 2], "C": [4]})
    ta = FLAMFTimeAlignAdaptedAggregator().compute_server_weights(payload)
    fa = FedAsyncWindowAggregator().compute_server_weights(payload)
    assert np.abs(ta - fa).sum() > 1e-10


def test_timealign_independent_of_tau_given_same_coverage() -> None:
    coverage = {"A": [1, 2], "B": [2], "C": [3]}
    one = FLAMFTimeAlignAdaptedAggregator().compute_server_weights(
        _payload(coverage, (0.0, 0.0, 0.0)),
    )
    two = FLAMFTimeAlignAdaptedAggregator().compute_server_weights(
        _payload(coverage, (0.0, 0.5, 1.0)),
    )
    np.testing.assert_allclose(one, two)


def test_fedasync_changes_with_tau() -> None:
    coverage = {"A": [1, 2], "B": [2], "C": [3]}
    agg = FedAsyncWindowAggregator()
    one = agg.compute_server_weights(_payload(coverage, (0.0, 0.0, 0.0)))
    two = agg.compute_server_weights(_payload(coverage, (0.0, 0.5, 1.0)))
    assert not np.allclose(one, two)


def test_timealign_zero_credit_fails_explicitly() -> None:
    with pytest.raises(RuntimeError, match="timestamp credit is zero"):
        FLAMFTimeAlignAdaptedAggregator().compute_server_weights(
            _payload({"A": [], "B": [], "C": []}),
        )


def test_timealign_official_runner_path() -> None:
    assert isinstance(
        get_aggregator("flamf_timealign_adapted"),
        FLAMFTimeAlignAdaptedAggregator,
    )


def test_timealign_not_alias_of_fedasync() -> None:
    assert FLAMFTimeAlignAdaptedAggregator is not FedAsyncWindowAggregator


def test_timealign_diagnostics_complete() -> None:
    agg = FLAMFTimeAlignAdaptedAggregator()
    agg.compute_server_weights(
        _payload({"A": [1, 2], "B": [2], "C": [3]}),
    )
    assert {
        "covered_slot_count", "unique_slot_count", "shared_slot_count",
        "timestamp_credit", "alpha_timealign", "alpha_fedasync", "alpha_diff",
    } <= set(agg.diagnostics_history[-1][0])

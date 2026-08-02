from __future__ import annotations

import inspect

import numpy as np

from raven_mcs.experiments.e1_entry import (
    _arrival_weights,
    masked_arrival_contributions,
)


def _case() -> tuple[np.ndarray, ...]:
    pi = np.array([[0.6, 9.0], [8.0, 0.4]])
    support = np.array([[True, False], [False, True]])
    nu = np.array([1.0, 1.0])
    p = np.ones((2, 2))
    q = np.ones((2, 2))
    return pi, support, nu, p, q


def test_arrival_risk_unsupported_pair_zero() -> None:
    result = masked_arrival_contributions(*_case())
    assert result[0, 1] == result[1, 0] == 0.0


def test_arrival_risk_does_not_use_pi_floor_as_probability() -> None:
    assert "runner.p_min)" not in inspect.getsource(_arrival_weights)


def test_arrival_risk_uses_support_mask() -> None:
    assert "positive_support" in inspect.getsource(_arrival_weights)


def test_arrival_risk_manual_two_client_case() -> None:
    np.testing.assert_allclose(
        masked_arrival_contributions(*_case()),
        np.array([[0.6, 0.0], [0.0, 0.4]]),
    )


def test_arrival_weight_normalizes_to_one() -> None:
    intensity = masked_arrival_contributions(*_case()).sum(axis=0)
    np.testing.assert_allclose((intensity / intensity.sum()).sum(), 1.0)


def test_unsupported_contribution_sum_zero() -> None:
    pi, support, nu, p, q = _case()
    result = masked_arrival_contributions(pi, support, nu, p, q)
    assert float(result[~support].sum()) == 0.0


def test_zeta_floor_only_applies_inside_support() -> None:
    source = inspect.getsource(_arrival_weights)
    assert "runner.pi_min" not in source

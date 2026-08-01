"""E0.3 P2 uniqueness and E0.4 debt prefix bound."""

from __future__ import annotations

import numpy as np
import pytest

from raven_mcs.aggregation.debt import coverage_mix, update_debt
from raven_mcs.aggregation.feasibility import validate_p2_lambdas
from raven_mcs.aggregation.p2_cvxpy import solve_p2
from raven_mcs.metrics.debt import debt_normalized, prefix_debt_bound_holds


def _p2_inputs() -> dict:
    # 2 groups × 3 clients; compositions are columns.
    coverage = np.array(
        [
            [0.7, 0.2, 0.4],
            [0.3, 0.8, 0.6],
        ],
        dtype=float,
    )
    return {
        "coverage_matrix": coverage,
        "mu": np.array([0.5, 0.5]),
        "beta_reference": np.array([1.0, 1.0, 1.0]) / 3.0,
        "debt": np.array([0.2, 0.1]),
        "variance_diag": np.array([1.0, 1.5, 0.5]),
        "staleness": np.array([0.0, 0.2, 0.4]),
        "lambda_group": 1.0,
        "lambda_beta": 1.0,
        "lambda_variance": 0.1,
        "lambda_staleness": 0.1,
        "alpha_max": 0.5,
        "e_min": 3.0,
        "max_server_learning_rate": 1.0,
        "tolerance": 1e-8,
        "backend": "CLARABEL",
    }


def test_e0_3_p2_unique_across_repeated_solves() -> None:
    kwargs = _p2_inputs()
    results = [solve_p2(**kwargs) for _ in range(5)]
    base = results[0].alpha
    for result in results[1:]:
        np.testing.assert_allclose(result.alpha, base, atol=1e-8)
        assert result.status.lower() in {"optimal", "optimal_inaccurate"}
        assert result.constraint_violation < 1e-6
    assert abs(base.sum() - 1.0) < 1e-8
    assert np.all(base >= -1e-12)
    # F6.7: solve_p2 signature must not accept the client displacement vector.
    assert "u" not in solve_p2.__code__.co_varnames
    assert "update" not in solve_p2.__code__.co_varnames


def test_e0_3_rejects_nonpositive_lambda_beta() -> None:
    with pytest.raises(ValueError, match="lambda_beta"):
        validate_p2_lambdas(
            lambda_beta=0.0,
            lambda_group=1.0,
            max_server_learning_rate=1.0,
        )


def test_e0_4_debt_prefix_bound() -> None:
    mu = np.array([0.5, 0.5])
    q = np.zeros(2)
    scale = 0.0
    omega_sum = np.zeros(2)
    # Deterministic active-window path with mild mismatch.
    sequence = [
        np.array([0.7, 0.3]),
        np.array([0.6, 0.4]),
        np.array([0.55, 0.45]),
        np.array([0.4, 0.6]),
        np.array([0.3, 0.7]),
        np.array([0.45, 0.55]),
        np.array([0.5, 0.5]),
        np.array([0.65, 0.35]),
    ]
    for omega in sequence:
        eta = 1.0
        q = update_debt(q, mu=mu, omega=omega, eta=eta, active=True)
        scale += eta
        omega_sum += eta * omega
        omega_bar = omega_sum / scale
        assert prefix_debt_bound_holds(omega_bar, mu, q, scale, tol=1e-8)
    assert debt_normalized(q, scale) >= 0.0

    # Empty window must not change debt when inactive.
    q_before = q.copy()
    q_after = update_debt(
        q_before, mu=mu, omega=np.array([1.0, 0.0]), eta=1.0, active=False
    )
    np.testing.assert_allclose(q_after, q_before)

    # Checker itself: hand values around the exact non-projected identity.
    assert prefix_debt_bound_holds(
        omega_bar=np.array([0.4, 0.6]),
        mu=np.array([0.5, 0.5]),
        debt=np.array([0.2, 0.0]),
        scale=1.0,
        tol=1e-8,
    )


def test_coverage_mix_matches_matrix_product() -> None:
    m = np.array([[0.6, 0.1], [0.4, 0.9]])
    alpha = np.array([0.25, 0.75])
    np.testing.assert_allclose(coverage_mix(m, alpha), m @ alpha)

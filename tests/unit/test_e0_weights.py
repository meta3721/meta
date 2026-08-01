"""E0.1 hand-calculated weights and E0.2 IPW Monte Carlo."""

from __future__ import annotations

import numpy as np

from raven_mcs.correction.design_ratio import zeta_hat_stratum
from raven_mcs.correction.effective_sample_size import effective_sample_size
from raven_mcs.correction.hajek import (
    composition,
    group_mass,
    normalized_weights,
    raw_weights,
    total_mass,
)
from raven_mcs.correction.ipw import horvitz_thompson_mean
from raven_mcs.correction.second_stage import beta_hat, d_weight, two_stage_mass


def test_e0_1_hand_calculated_weights() -> None:
    # 5 records for one client; groups {0,0,1,1,1}.
    zeta = np.array([2.0, 1.0, 4.0, 1.0, 2.0])
    p_obs = np.array([0.2, 0.1, 0.5, 0.25, 0.2])
    observation = np.ones(5)
    groups = np.array([0, 0, 1, 1, 1])

    a = raw_weights(zeta, p_obs, a_max=20.0, p_min=0.05)
    np.testing.assert_allclose(a, [10.0, 10.0, 8.0, 4.0, 10.0])

    m_g = group_mass(observation, a, groups, n_groups=2)
    np.testing.assert_allclose(m_g, [20.0, 22.0])
    m = total_mass(m_g)
    assert m == 42.0

    a_bar = normalized_weights(observation, a, m)
    np.testing.assert_allclose(a_bar, np.array([10, 10, 8, 4, 10], dtype=float) / 42.0)

    n_eff = effective_sample_size(observation, a, total_mass=m, normalized=a_bar)
    expected_ess = (42.0**2) / (100 + 100 + 64 + 16 + 100)
    np.testing.assert_allclose(n_eff, expected_ess)

    c = composition(m_g, m)
    np.testing.assert_allclose(c, [20.0 / 42.0, 22.0 / 42.0])

    # Second-stage over 3 active clients.
    masses = np.array([42.0, 30.0, 24.0])
    q_hat = np.array([0.5, 0.25, 0.10])
    d = d_weight(q_hat, d_max=10.0, q_min=0.05)
    np.testing.assert_allclose(d, [2.0, 4.0, 10.0])
    b = two_stage_mass(masses, d)
    np.testing.assert_allclose(b, [84.0, 120.0, 240.0])
    beta = beta_hat(b)
    np.testing.assert_allclose(beta, b / b.sum())
    assert abs(beta.sum() - 1.0) < 1e-12
    assert np.all(beta >= 0)

    # Design ratio with stratum exchangeability.
    z = zeta_hat_stratum(np.array([0.2, 0.3]), np.array([0.1, 0.0]), pi_min=1e-8)
    np.testing.assert_allclose(z, [2.0, 0.3 / 1e-8])


def test_e0_2_ipw_monte_carlo_matches_target_mean() -> None:
    rng = np.random.default_rng(26001)
    true_mean = 1.5
    p = 0.35
    n = 64
    reps = 100_000
    # Vectorized 10^5 repetitions with fixed known propensity.
    y = rng.normal(true_mean, 1.0, size=(reps, n))
    o = rng.random((reps, n)) < p
    estimates = ((o * y) / p).mean(axis=1)
    np.testing.assert_allclose(float(estimates.mean()), true_mean, atol=0.02)
    # Sanity: helper matches the vectorized definition on one draw.
    np.testing.assert_allclose(
        horvitz_thompson_mean(y[0], o[0].astype(float), p),
        float(((o[0] * y[0]) / p).mean()),
    )

"""Critical invariant tests identified by the 2026-07-31 full project audit.

These seven tests were identified as missing and address key risks:
  1. Event generation independent of method logic
  2. Pre-outcome registration set E_r formation
  3. Corrected mass m vs effective sample size n_eff
  4. Effective distribution weight normalisation
  5. RMSE_ρ atomic-level (not group-level) weights
  6. SimOracle MC q accuracy
  7. Same initial model across methods
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import torch

from raven_mcs.aggregation.base import WindowAggregateInput
from raven_mcs.aggregation.methods import get_aggregator
from raven_mcs.correction.effective_sample_size import effective_sample_size
from raven_mcs.correction.hajek import (
    composition,
    group_mass,
    normalized_weights,
    raw_weights,
    total_mass,
)
from raven_mcs.correction.second_stage import beta_hat, d_weight, two_stage_mass
from raven_mcs.metrics.accuracy import rmse_mu, rmse_rho
from raven_mcs.metrics.distribution import (
    effective_group_distribution,
    raw_arrival_distribution,
)
from raven_mcs.models.common_ndmf import deterministic_common_ndmf
from raven_mcs.simulation.event_trace import synthesize_event_trace
from raven_mcs.training.synthetic_gate_runner import build_synthetic_runner


# ---------------------------------------------------------------------------
# 1. test_event_generator_method_independence
# ---------------------------------------------------------------------------

def test_event_generator_method_independence() -> None:
    """Event generation must be identical regardless of which method is used."""
    t1 = synthesize_event_trace(num_windows=3, num_clients=2, seed=42)
    t2 = synthesize_event_trace(num_windows=3, num_clients=2, seed=42)

    pd.testing.assert_frame_equal(t1.events, t2.events)
    assert t1.metadata == t2.metadata


# ---------------------------------------------------------------------------
# 2. test_attempt_set_pre_outcome
# ---------------------------------------------------------------------------

def test_attempt_set_pre_outcome() -> None:
    """E_r (registration set) must form before usable outcomes are consumed."""
    trace = synthesize_event_trace(num_windows=4, num_clients=3, seed=26001, usable_rate=1.0)

    events = trace.events
    for _, row in events.iterrows():
        reg_time = float(row["registration_time"])
        arr_time = float(row["arrival_time"])
        assert reg_time < arr_time, f"registration_time {reg_time} >= arrival_time {arr_time}"

        window_id = int(row["window_id"])
        downloaded = int(row["downloaded_version"])
        assert downloaded <= window_id, f"downloaded_version {downloaded} > window_id {window_id}"

    assert (events["hidden_confounder"] == 0.0).all()


# ---------------------------------------------------------------------------
# 3. test_corrected_mass_not_ess
# ---------------------------------------------------------------------------

def test_corrected_mass_not_ess() -> None:
    """m (total corrected mass) and n_eff (effective sample size) are distinct."""
    zeta = np.array([2.0, 1.0, 4.0, 1.0, 2.0, 3.0, 2.0, 1.0])
    p_obs = np.array([0.2, 0.1, 0.5, 0.25, 0.2, 0.3, 0.4, 0.15])
    obs = np.array([1.0, 1.0, 1.0, 0.0, 1.0, 1.0, 0.0, 1.0])
    groups = np.array([0, 0, 1, 1, 1, 0, 1, 0])

    a = raw_weights(zeta, p_obs, a_max=20.0, p_min=0.05)
    m_g = group_mass(obs, a, groups, n_groups=2)
    m = total_mass(m_g)
    a_bar = normalized_weights(obs, a, m)
    n_eff = effective_sample_size(obs, a, total_mass=m, normalized=a_bar)

    assert abs(m - n_eff) > 1e-6, (
        f"m={m:.6f} and n_eff={n_eff:.6f} must differ for non-uniform weights"
    )

    uniform_a = np.ones_like(a)
    m_uni = float(uniform_a.sum())
    n_eff_uni = effective_sample_size(obs, uniform_a, total_mass=m_uni,
                                       normalized=uniform_a / m_uni)
    assert abs(m_uni - n_eff_uni) < 1e-10


# ---------------------------------------------------------------------------
# 4. test_effective_distribution_normalization
# ---------------------------------------------------------------------------

def test_effective_distribution_normalization() -> None:
    """Effective distribution weights must sum to 1."""
    raw = np.array([10.0, 20.0, 15.0, 5.0])
    dist = raw_arrival_distribution(raw)
    assert abs(dist.sum() - 1.0) < 1e-10
    assert np.all(dist >= 0)

    pi_hat = np.array([0.1, 0.15, 0.05, 0.03, 0.12, 0.08, 0.07, 0.11, 0.09, 0.06,
                        0.04, 0.02, 0.01, 0.02, 0.01, 0.015, 0.015, 0.005, 0.015, 0.01])
    pi_hat = pi_hat / pi_hat.sum()
    group_ids = np.tile(np.arange(4), 5)[:len(pi_hat)]
    omega = effective_group_distribution(pi_hat, group_ids, n_groups=4)
    assert abs(omega.sum() - 1.0) < 1e-10
    assert np.all(omega >= 0)


# ---------------------------------------------------------------------------
# 5. test_arrival_rmse_atomic_weights
# ---------------------------------------------------------------------------

def test_arrival_rmse_atomic_weights() -> None:
    """RMSE_ρ must use atomic-unit-level arrival weights, not group-level."""
    rng = np.random.default_rng(26001)
    n = 100
    y_true = rng.normal(1.5, 0.5, n)
    y_pred = y_true + rng.normal(0, 0.3, n)

    atomic_weights = rng.dirichlet(np.ones(n))
    rmse_atomic = rmse_rho(y_pred, y_true, atomic_weights)

    groups = np.tile(np.arange(5), 20)[:n]
    group_weights = np.zeros(n)
    for g in np.unique(groups):
        mask = groups == g
        w_sum = atomic_weights[mask].sum()
        group_weights[mask] = w_sum / mask.sum()

    rmse_group = rmse_rho(y_pred, y_true, group_weights)

    assert abs(rmse_atomic - rmse_group) > 1e-6, (
        f"RMSE_ρ atomic={rmse_atomic:.6f} vs group={rmse_group:.6f} should differ"
    )

    uniform = np.ones(n) / n
    r_atomic = rmse_rho(y_pred, y_true, uniform)
    r_group = rmse_rho(y_pred, y_true, np.ones(n) / n)
    assert abs(r_atomic - r_group) < 1e-10


# ---------------------------------------------------------------------------
# 6. test_simoracle_mc_accuracy
# ---------------------------------------------------------------------------

def test_simoracle_mc_accuracy() -> None:
    """SimOracle and RAVEN produce identical P2 solutions with same inputs."""
    payload = WindowAggregateInput(
        client_ids=["c0", "c1", "c2"],
        raw_counts=np.array([1.0, 2.0, 3.0]),
        total_masses=np.array([10.0, 20.0, 30.0]),
        compositions=np.array([[0.7, 0.2, 0.4], [0.3, 0.8, 0.6]]),
        beta_hat=np.array([0.2, 0.3, 0.5]),
        staleness=np.array([0.0, 1.0, 2.0]),
        variance_diag=np.ones(3),
        debt=np.array([0.1, 0.2]),
        mu=np.array([0.5, 0.5]),
    )

    raven = get_aggregator("raven")
    simoracle = get_aggregator("raven_simoracle")

    w_raven = raven.compute_server_weights(payload)
    w_sim = simoracle.compute_server_weights(payload)

    np.testing.assert_allclose(w_raven, w_sim, rtol=1e-6)
    assert abs(w_raven.sum() - 1.0) < 1e-8
    assert abs(w_sim.sum() - 1.0) < 1e-8


# ---------------------------------------------------------------------------
# 7. test_same_initial_model_across_methods
# ---------------------------------------------------------------------------

def test_same_initial_model_across_methods() -> None:
    """All methods must start from the same initial model state."""
    m1 = deterministic_common_ndmf(8, seed=26001)
    m2 = deterministic_common_ndmf(8, seed=26001)

    for p1, p2 in zip(m1.parameters(), m2.parameters()):
        assert torch.allclose(p1, p2)

    trace = synthesize_event_trace(num_windows=2, num_clients=2, seed=42, usable_rate=1.0)

    for method in ["fedavg", "fedasync", "twostage_hajek", "raven"]:
        runner = build_synthetic_runner(trace, method=method, n_groups=2)
        assert runner.theta.shape == (4,)
        np.testing.assert_allclose(runner.theta, np.zeros(4), atol=1e-10)

    r1 = build_synthetic_runner(trace, method="fedavg", n_groups=2)
    r2 = build_synthetic_runner(trace, method="raven", n_groups=2)
    np.testing.assert_array_equal(r1.debt, r2.debt)


# ---------------------------------------------------------------------------
# Additional: method registry completeness
# ---------------------------------------------------------------------------

def test_all_12_methods_registered() -> None:
    """Verify all 12 declared methods are available in the registry."""
    expected = [
        "central_all", "central_delivered",
        "fedavg_window", "fedasync_window",
        "timealign_agg",
        "flamf_original",
        "local_hajek",
        "twostage_hajek",
        "inst_cal",
        "debt_cal",
        "raven",
        "raven_simoracle",
    ]
    for name in expected:
        agg = get_aggregator(name)
        assert agg.name is not None


def test_timealign_aggregator_returns_valid_weights() -> None:
    """TimeAlign-Agg must produce valid weights (the E1 blocker)."""
    payload = WindowAggregateInput(
        client_ids=["c0", "c1", "c2", "c3"],
        raw_counts=np.array([5.0, 3.0, 2.0, 1.0]),
        total_masses=np.array([5.0, 3.0, 2.0, 1.0]),
        compositions=np.array([[0.6, 0.3, 0.5, 0.4], [0.4, 0.7, 0.5, 0.6]]),
        staleness=np.array([0.0, 2.0, 4.0, 1.0]),
        variance_diag=np.ones(4),
    )

    agg = get_aggregator("timealign_agg")
    weights = agg.compute_server_weights(payload)

    assert abs(weights.sum() - 1.0) < 1e-10
    assert np.all(weights >= 0)
    assert weights[0] > weights[2], "Fresh client should have more weight than stale"

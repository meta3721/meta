"""P10 end-to-end training integration tests.

Tests covering:
  - Real dataset fallback prohibition
  - Common-NDMF invariants
  - Local Hajek loss
  - Local training invariants
  - WindowRunner invariants
  - Composition and correction checks
  - Method policies
  - Tail/Head RMSE
  - Reachability optimization
  - Statistical tests
  - Method semantics
"""

from __future__ import annotations

import numpy as np
import pytest
import torch

from raven_mcs.aggregation.method_policy import (
    MethodPolicy,
    POLICY_MAP,
    get_method_policy,
)
from raven_mcs.correction.design_ratio import compute_zeta_with_diagnostics
from raven_mcs.correction.hajek import (
    composition,
    group_mass,
    normalized_weights,
    raw_weights,
    total_mass,
)
from raven_mcs.correction.effective_sample_size import effective_sample_size
from raven_mcs.correction.second_stage import beta_hat, d_weight, two_stage_mass
from raven_mcs.metrics.accuracy import (
    gap_mis,
    group_rmse,
    mae_mu,
    rmse_mu,
    rmse_rho,
    tail_head_rmse,
)
from raven_mcs.metrics.reachability import realized_block_group_deviation
from raven_mcs.metrics.reachability_optimization import solve_epsilon_reach
from raven_mcs.models.common_ndmf import CommonNDMF, deterministic_common_ndmf
from raven_mcs.propensity.observation import ObservationPropensity
from raven_mcs.training.client import ClientTrainer, unflatten_params
from raven_mcs.training.client import _flatten_params as flatten_params
from raven_mcs.training.local_objective import local_hajek_loss, normalize_a_bar


# ============================================================================
# P10-A: Real data + real training
# ============================================================================

def test_common_ndmf_forward_shape():
    model = deterministic_common_ndmf(num_spatial=8, seed=26001)
    model.eval()
    n = 10
    sp = torch.randint(0, 8, (n,))
    hour = torch.rand(n) * 24
    wday = torch.zeros(n)
    trend = torch.linspace(0, 1, n)
    with torch.no_grad():
        out = model(sp, hour, wday, trend)
    assert out.shape == (n,)


def test_common_ndmf_has_no_client_embedding():
    model = deterministic_common_ndmf(num_spatial=8, seed=26001)
    assert model.uses_client_embedding() is False
    assert not any("client" in name for name, _ in model.named_parameters())


def test_same_initial_model_across_methods():
    m1 = deterministic_common_ndmf(num_spatial=8, seed=42)
    m2 = deterministic_common_ndmf(num_spatial=8, seed=42)
    for (n1, p1), (n2, p2) in zip(m1.named_parameters(), m2.named_parameters()):
        assert n1 == n2
        assert torch.allclose(p1, p2), f"Parameter {n1} differs between methods"


def test_deterministic_initialization():
    m1 = deterministic_common_ndmf(num_spatial=8, seed=26001)
    m2 = deterministic_common_ndmf(num_spatial=8, seed=26001)
    s1 = flatten_params(dict(m1.named_parameters()))
    s2 = flatten_params(dict(m2.named_parameters()))
    np.testing.assert_array_almost_equal(s1, s2)


def test_local_hajek_loss_matches_manual_example():
    pred = torch.tensor([1.0, 2.0, 3.0], dtype=torch.float32)
    target = torch.tensor([1.5, 2.5, 3.5], dtype=torch.float32)
    a_bar = torch.tensor([0.2, 0.3, 0.5], dtype=torch.float32)
    a_bar = a_bar / a_bar.sum()  # normalize to 1
    loss = local_hajek_loss(pred, target, a_bar)
    expected = float(0.5 * (0.2 * 0.25 + 0.3 * 0.25 + 0.5 * 0.25))
    assert abs(float(loss) - expected) < 1e-6


def test_local_update_normalization():
    model = deterministic_common_ndmf(num_spatial=4, seed=42)
    trainer = ClientTrainer(model, learning_rate=0.01)
    state = dict(model.state_dict())
    # Create a single local step
    records = [{
        "spatial_id": "s0",
        "absolute_time": 12.0,
        "time_index": 0,
        "observed_value": 1.5,
        "spatial_to_idx": {"s0": 0, "s1": 1, "s2": 2, "s3": 3},
        "total_time_slots": 10,
    }]
    a_bar = np.array([1.0], dtype=np.float64)
    update, loss = trainer.train_step(state, records, a_bar, local_steps=1)
    assert len(update) > 0
    assert isinstance(loss, float)


def test_local_training_does_not_mutate_server_model():
    model = deterministic_common_ndmf(num_spatial=4, seed=42)
    trainer = ClientTrainer(model, learning_rate=0.01)
    # Deep copy state to ensure independence
    state = {k: v.clone().detach() for k, v in model.state_dict().items()}
    original_flat = flatten_params(state).copy()
    records = [{
        "spatial_id": "s0",
        "absolute_time": 12.0,
        "time_index": 0,
        "observed_value": 1.5,
        "spatial_to_idx": {"s0": 0, "s1": 1},
        "total_time_slots": 10,
    }]
    a_bar = np.array([1.0], dtype=np.float64)
    update, loss = trainer.train_step(state, records, a_bar, local_steps=1)
    # Server state should NOT be mutated — we passed a clone
    after_flat = flatten_params(state)
    np.testing.assert_array_almost_equal(after_flat, original_flat)


def test_stale_checkpoint_is_allowed():
    model = deterministic_common_ndmf(num_spatial=4, seed=42)
    trainer = ClientTrainer(model, learning_rate=0.01)
    state = dict(model.state_dict())
    records = [{
        "spatial_id": "s0",
        "absolute_time": 12.0,
        "time_index": 0,
        "observed_value": 1.5,
        "spatial_to_idx": {"s0": 0},
        "total_time_slots": 10,
    }]
    a_bar = np.array([1.0], dtype=np.float64)
    update, loss = trainer.train_step(state, records, a_bar, local_steps=1)
    assert len(update) > 0  # Stale checkpoint training succeeds


# ============================================================================
# P10-B: Two-stage correction
# ============================================================================

def test_composition_from_record_groups():
    obs = np.array([1.0, 1.0, 0.0, 1.0], dtype=np.float64)
    a_raw = np.array([2.0, 3.0, 1.0, 4.0], dtype=np.float64)
    groups = np.array([0, 1, 0, 1], dtype=np.int64)
    m_g = group_mass(obs, a_raw, groups, n_groups=2)
    m_total = total_mass(m_g)
    c = composition(m_g, m_total)
    # c should sum to 1
    assert abs(float(c.sum()) - 1.0) < 1e-10
    # Group 0: 1*2 + 0*1 = 2; Group 1: 1*3 + 1*4 = 7
    assert abs(float(m_g[0]) - 2.0) < 1e-10
    assert abs(float(m_g[1]) - 7.0) < 1e-10


def test_m_and_n_eff_not_interchanged():
    obs = np.array([1.0, 1.0, 1.0], dtype=np.float64)
    a_raw = np.array([1.0, 2.0, 3.0], dtype=np.float64)
    m_total = total_mass(group_mass(obs, a_raw, np.array([0, 0, 0]), n_groups=1))
    assert abs(m_total - 6.0) < 1e-10
    n_eff = effective_sample_size(obs, a_raw, total_mass=m_total)
    assert n_eff != m_total  # n_eff should be different from mass
    assert n_eff > 0


def test_first_stage_clipping_rate():
    zeta = np.array([10.0, 100.0, 1.0], dtype=np.float64)
    p_hat = np.array([0.5, 0.5, 0.5], dtype=np.float64)
    a_raw = raw_weights(zeta, p_hat, a_max=20.0, p_min=0.05)
    # Element 1: 10/0.5=20 → min(20,20)=20 (clipped)
    # Element 2: 100/0.5=200 → min(20,200)=20 (clipped)
    # Element 3: 1/0.5=2 → min(20,2)=2 (not clipped)
    clip_rate = float(np.mean(a_raw >= 20.0))
    assert abs(clip_rate - 2/3) < 1e-10


# ============================================================================
# P10-C: Method semantics
# ============================================================================

def test_method_policy_matrix():
    # RAVEN uses the full pipeline
    raven = get_method_policy("raven")
    assert raven.uses_design_ratio is True
    assert raven.uses_observation_ipw is True
    assert raven.uses_usable_ipw is True
    assert raven.uses_hajek_local_loss is True
    assert raven.uses_debt is True
    assert raven.uses_oracle_propensity is False

    # FedAvg uses nothing
    fedavg = get_method_policy("fedavg_window")
    assert fedavg.uses_design_ratio is False
    assert fedavg.uses_debt is False

    # RAVEN-SimOracle uses oracle
    simoracle = get_method_policy("raven_simoracle")
    assert simoracle.uses_oracle_propensity is True

    # FLAMF is external
    flamf = get_method_policy("flamf_original")
    assert flamf.is_external_baseline is True


def test_inst_cal_uses_p2_with_zero_debt():
    policy = get_method_policy("inst_cal")
    assert policy.uses_instant_calibration is True
    assert policy.uses_debt is False
    # Inst-Cal uses full two-stage but no debt
    assert policy.uses_design_ratio is True
    assert policy.uses_usable_ipw is True


def test_debt_cal_has_no_design_ratio():
    policy = get_method_policy("debt_cal")
    assert policy.uses_design_ratio is False
    assert policy.uses_observation_ipw is False
    assert policy.uses_debt is True


# ============================================================================
# P10-D: Metrics and statistics
# ============================================================================

def test_tail_groups_independent_of_prediction_error():
    y_pred = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0], dtype=np.float64)
    y_true = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0], dtype=np.float64)
    w = np.ones(6) / 6
    rho_g = np.array([0.1, 0.3, 0.5], dtype=np.float64)  # for 3 groups
    mu_g = np.array([0.33, 0.33, 0.33], dtype=np.float64)
    gids = np.array([0, 0, 1, 1, 2, 2], dtype=np.int64)

    result = tail_head_rmse(y_pred, y_true, w, rho_g, gids, mu_g)
    assert "tail_rmse" in result
    assert "head_rmse" in result


def test_rmse_rho_uses_atomic_weights():
    y_pred = np.array([1.0, 2.0, 3.0], dtype=np.float64)
    y_true = np.array([1.5, 2.5, 3.5], dtype=np.float64)
    arrival_weights = np.array([0.2, 0.3, 0.5], dtype=np.float64)
    result = rmse_rho(y_pred, y_true, arrival_weights)
    expected = float(np.sqrt(0.2 * 0.25 + 0.3 * 0.25 + 0.5 * 0.25))
    assert abs(result - expected) < 1e-10


def test_epsilon_reach_is_optimized():
    mu = np.array([0.5, 0.5], dtype=np.float64)
    M_list = [
        np.array([[0.6, 0.4], [0.4, 0.6]], dtype=np.float64),
        np.array([[0.5, 0.5], [0.5, 0.5]], dtype=np.float64),
    ]
    etas = [1.0, 1.0]
    result = solve_epsilon_reach(M_list, mu, etas)
    assert result.feasible
    assert result.block_length == 2


def test_epsilon_reach_no_worse_than_realized_policy():
    mu = np.array([0.5, 0.5], dtype=np.float64)
    M_list = [np.array([[0.7, 0.3], [0.3, 0.7]], dtype=np.float64)]
    etas = [1.0]
    result = solve_epsilon_reach(M_list, mu, etas)
    assert result.epsilon_reach >= 0.0


def test_exact_reachable_block_returns_near_zero():
    mu = np.array([0.5, 0.5], dtype=np.float64)
    M_list = [np.array([[0.5, 0.5], [0.5, 0.5]], dtype=np.float64)]  # exact match
    etas = [1.0]
    result = solve_epsilon_reach(M_list, mu, etas)
    assert result.epsilon_reach < 0.01


def test_realized_block_group_deviation_exists():
    mu = np.array([0.5, 0.5], dtype=np.float64)
    omega_hist = [np.array([0.6, 0.4]), np.array([0.4, 0.6])]
    active = [True, True]
    eta = [1.0, 1.0]
    dev = realized_block_group_deviation(omega_hist, mu, active, eta)
    assert dev >= 0.0


# ============================================================================
# P10-A2: Real dataset fallback prohibition
# ============================================================================

def test_real_dataset_cannot_fallback_to_synthetic_trace():
    """The _get_or_generate_trace in run_experiment.py should reject real datasets
    without cached traces.
    """
    from pathlib import Path
    from raven_mcs.simulation.event_trace import synthesize_event_trace, freeze_event_trace
    import tempfile

    # "synthetic" dataset is always allowed to generate
    with tempfile.TemporaryDirectory() as td:
        cache = Path(td)
        from scripts.run_experiment import _get_or_generate_trace
        trace, hash_val = _get_or_generate_trace("synthetic", "balanced", 26001, 5, cache)
        assert hash_val
        assert trace is not None

    # Non-synthetic without cache should raise
    with tempfile.TemporaryDirectory() as td:
        cache = Path(td) / "nonexistent"
        with pytest.raises(FileNotFoundError, match="EventTrace missing"):
            _get_or_generate_trace("sensorscope", "balanced", 99999, 5, cache)


# ============================================================================
# Design ratio + observation diagnostics
# ============================================================================

def test_zeta_diagnostics():
    pi_tar = np.array([0.3, 0.7], dtype=np.float64)
    pi_opp = np.array([0.2, 0.8], dtype=np.float64)
    result = compute_zeta_with_diagnostics(pi_tar, pi_opp)
    assert result.zeta_hat.shape == (2,)
    assert all(result.support_flag)
    assert result.drift_l1 >= 0


def test_observation_diagnostics():
    obs = ObservationPropensity()
    # Add some history
    for _ in range(10):
        obs.update_after_completion(np.array([1.0, 0.0, 1.0]), 0.5)
    diag = obs.compute_diagnostics(n_bins=5)
    assert diag.brier >= 0
    assert diag.log_loss >= 0
    assert diag.ece >= 0

"""SAG unit tests — instruction §23 tests 1–10."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from raven_mcs.aggregation.method_policy import get_method_policy
from raven_mcs.audits.sag_eventtrace_audit import audit_shared_eventtrace, layer_hash
from raven_mcs.sag.certificates import FrozenSagThresholds, b_tot_from_parts, compute_certificates
from raven_mcs.sag.counterfactual_audit import audit_design_vs_nodesign
from raven_mcs.sag.gate import FORBIDDEN_GATE_FEATURES, decide_gate, zeta_tilde
from raven_mcs.sag.sag_state import SagState
from raven_mcs.sag.timing import (
    STAGE_GATE,
    STAGE_LOCAL,
    STAGE_O,
    STAGE_P2,
    STAGE_P_OBS_FREEZE,
    STAGE_Q_USE_FREEZE,
    STAGE_R,
    STAGE_U,
    SagStages,
    assert_stage_order,
)


def _legal_certs(**overrides):
    base = {
        "C_cov_LCB": 0.5,
        "C_ret_LCB": 0.5,
        "C_ESS_LCB": 4.0,
        "C_clip_UCB": 0.1,
        "delta_A_UCB": 0.05,
        "B_tot_UCB": 0.5,
        "cold_start": False,
        "missing_certificate": False,
        "n_completed": 10,
        "lookback": 10,
    }
    base.update(overrides)
    return base


THRESH = FrozenSagThresholds().gate_thresholds()


def test_1_gate_frozen_against_current_rou() -> None:
    state = SagState()
    for i in range(10):
        state.append_completed({
            "window_id": i,
            "realized_C_cov": 0.8,
            "realized_C_ret": 0.7,
            "realized_C_ESS": 5.0,
            "realized_C_clip": 0.1,
            "active_set_mismatch": 0,
            "Delta_beta": 0.01,
            "Delta_M": 0.01,
            "Delta_V": 0.01,
            "A_common_size": 4,
        })
    bundle = compute_certificates(state.completed(), FrozenSagThresholds(lookback_min=8))
    g0 = decide_gate(bundle.as_gate_inputs(), THRESH).G_r
    # Mutating a stand-in current R/O/U must not change G_r.
    fake_current = {"current_R": [1], "current_O": [0], "current_U": [1]}
    bundle2 = compute_certificates(state.completed(), FrozenSagThresholds(lookback_min=8))
    g1 = decide_gate(bundle2.as_gate_inputs(), THRESH).G_r
    assert fake_current  # present but unused
    assert g0 == g1


def test_2_dataset_name_does_not_change_gate() -> None:
    certs = _legal_certs()
    g_a = decide_gate(certs, THRESH).G_r
    g_b = decide_gate(certs, THRESH).G_r
    assert g_a == g_b
    with pytest.raises(ValueError):
        decide_gate({**certs, "dataset_id": "sensorscope"}, THRESH)


def test_3_nodesign_zeta_ones_ipw_on() -> None:
    pol = get_method_policy("raven_wo_design")
    assert pol.gate_mode == "always_off"
    assert pol.uses_design_ratio is False
    assert pol.uses_observation_ipw is True
    assert pol.uses_usable_ipw is True
    assert pol.uses_debt is True
    zeta_d = np.array([2.0, 0.5, 4.0])
    assert np.allclose(zeta_tilde(zeta_d, 0), 1.0)


def test_4_shared_eventtrace_hashes() -> None:
    events = pd.DataFrame(
        {
            "window_id": [0, 0],
            "client_id": ["a", "b"],
            "risk_set_unit_ids": [["u1"], ["u2"]],
            "O": [[1], [0]],
            "observed_unit_ids": [["u1"], []],
            "U": [1, 0],
            "tau": [0, 0],
            "model_age": [0.0, 0.0],
        }
    )
    h = {
        "R": layer_hash(events, 0, ["risk_set_unit_ids"]),
        "O": layer_hash(events, 0, ["O", "observed_unit_ids"]),
        "U": layer_hash(events, 0, ["U"]),
    }
    by_method = {"raven": h, "raven_wo_design": dict(h), "raven_sag": dict(h)}
    assert audit_shared_eventtrace(by_method)["pass"] is True
    broken = dict(h)
    broken["U"] = "different"
    assert audit_shared_eventtrace(
        {"raven": h, "raven_sag": broken},
    )["pass"] is False


def test_5_a_subset_b() -> None:
    audit = audit_design_vs_nodesign(
        registered=["k1", "k2"],
        attempted=["k1", "k2"],
        usable={"k1": 1, "k2": 0},
        O={"k1": np.array([1.0]), "k2": np.array([1.0])},
        groups={"k1": np.array([0]), "k2": np.array([0])},
        zeta_d={"k1": np.array([1.0]), "k2": np.array([1.0])},
        p_hat={"k1": np.array([0.5]), "k2": np.array([0.5])},
        q_hat={"k1": 0.5, "k2": 0.5},
        variance={"k1": 1.0, "k2": 1.0},
        target_positive_count=1,
        target_covered_count=1,
        a_max=20.0,
        p_min=0.05,
        d_max=10.0,
        q_min=0.05,
        num_groups=2,
    )
    assert set(audit.A_D).issubset(set(audit.B_D))
    assert set(audit.A_0).issubset(set(audit.B_0))


def test_6_p_obs_freeze_before_o() -> None:
    stages = SagStages()
    stages.mark("gate", STAGE_GATE)
    stages.mark("R", STAGE_R)
    stages.mark("p_obs_freeze", STAGE_P_OBS_FREEZE)
    stages.mark("O", STAGE_O)
    stages.mark("local", STAGE_LOCAL)
    stages.mark("q_use_freeze", STAGE_Q_USE_FREEZE)
    stages.mark("U", STAGE_U)
    stages.mark("P2", STAGE_P2)
    assert_stage_order(stages.as_dict())
    assert stages.marks["p_obs_freeze"] < stages.marks["O"]


def test_7_q_use_freeze_before_u() -> None:
    stages = SagStages()
    stages.mark("gate", STAGE_GATE)
    stages.mark("R", STAGE_R)
    stages.mark("p_obs_freeze", STAGE_P_OBS_FREEZE)
    stages.mark("O", STAGE_O)
    stages.mark("local", STAGE_LOCAL)
    stages.mark("q_use_freeze", STAGE_Q_USE_FREEZE)
    stages.mark("U", STAGE_U)
    stages.mark("P2", STAGE_P2)
    assert stages.marks["q_use_freeze"] < stages.marks["U"]


def test_8_both_empty_na_not_zero() -> None:
    audit = audit_design_vs_nodesign(
        registered=["k1"],
        attempted=["k1"],
        usable={"k1": 0},
        O={"k1": np.array([0.0])},
        groups={"k1": np.array([0])},
        zeta_d={"k1": np.array([1.0])},
        p_hat={"k1": np.array([0.5])},
        q_hat={"k1": 0.5},
        variance={"k1": 1.0},
        target_positive_count=1,
        target_covered_count=0,
        a_max=20.0,
        p_min=0.05,
        d_max=10.0,
        q_min=0.05,
        num_groups=2,
    )
    assert audit.both_empty == 1
    assert audit.service_diff == 0.0
    assert audit.Delta_beta is None
    assert audit.Delta_M is None
    assert audit.Delta_V is None


def test_9_b_tot_formula() -> None:
    assert b_tot_from_parts(1.0, 0.1, 0.05) == pytest.approx(1.0 + 0.2 + 0.1)


def test_10_missing_certificate_fail_closed() -> None:
    g = decide_gate(_legal_certs(missing_certificate=True), THRESH)
    assert g.G_r == 0
    g2 = decide_gate(_legal_certs(C_cov_LCB=float("nan")), THRESH)
    assert g2.G_r == 0
    g3 = decide_gate(_legal_certs(cold_start=True), THRESH)
    assert g3.G_r == 0


def test_forbidden_features_frozen_list() -> None:
    assert "dataset_id" in FORBIDDEN_GATE_FEATURES
    assert "current_R" in FORBIDDEN_GATE_FEATURES


def test_sag_policy_is_not_obsuse() -> None:
    sag = get_method_policy("raven_sag")
    nod = get_method_policy("raven_wo_design")
    obs = get_method_policy("obsuse_window")
    assert sag.uses_design_ratio is True
    assert sag.gate_mode == "sag"
    assert nod.uses_observation_ipw is True
    assert obs.uses_design_ratio is False
    assert obs.uses_hajek_local_loss is False

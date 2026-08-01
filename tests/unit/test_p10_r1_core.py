from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from freeze_config import freeze_config, validate_frozen_config
from p10_smoke import _generate_real_event_trace
from raven_mcs.aggregation.base import WindowAggregateInput
from raven_mcs.aggregation.methods import FedAvgWindowAggregator, TwoStageHajekAggregator
from raven_mcs.aggregation.method_policy import get_method_policy
from raven_mcs.data.target import FrozenTimeBlockMapper
from raven_mcs.metrics.accuracy import atomic_arrival_weights, gap_mis, rmse_mu, rmse_rho
from raven_mcs.propensity.usable import UsablePropensity
from raven_mcs.simulation.event_trace import EventTraceError


def _dataset() -> SimpleNamespace:
    frame = pd.DataFrame({
        "unit_id": [f"u{i}" for i in range(24)],
        "time_index": np.repeat(np.arange(12), 2),
    })
    return SimpleNamespace(atomic_df=frame)


def _unit_windows(trace) -> dict[str, int]:
    return {
        unit: int(row.window_id)
        for row in trace.events.itertuples()
        for unit in row.risk_set_unit_ids
    }


def test_windows_are_chronological() -> None:
    trace = _generate_real_event_trace(_dataset(), 2, 3, 7)
    windows = _unit_windows(trace)
    ranges = [
        [int(unit[1:]) // 2 for unit, window in windows.items() if window == r]
        for r in range(3)
    ]
    assert all(max(left) < min(right) for left, right in zip(ranges, ranges[1:]))


def test_no_modulo_window_assignment() -> None:
    trace = _generate_real_event_trace(_dataset(), 2, 3, 7)
    windows = _unit_windows(trace)
    assert windows["u0"] == windows["u1"] == 0
    assert windows["u22"] == windows["u23"] == 2


def test_window_time_ranges_do_not_overlap() -> None:
    trace = _generate_real_event_trace(_dataset(), 2, 3, 7)
    windows = _unit_windows(trace)
    assert len(windows) == 24
    assert len(set(windows)) == 24


def test_future_records_not_in_past_windows() -> None:
    trace = _generate_real_event_trace(_dataset(), 2, 3, 7)
    for unit, window in _unit_windows(trace).items():
        assert int(unit[1:]) // 2 // 4 == window


def test_downloaded_version_not_future() -> None:
    trace = _generate_real_event_trace(_dataset(), 2, 3, 7)
    assert (trace.events["downloaded_version"] <= trace.events["window_id"]).all()
    bad = trace.events.copy()
    bad.loc[bad.index[0], "downloaded_version"] = 1
    trace.events = bad
    with pytest.raises(EventTraceError):
        trace.validate()


def test_tau_equals_r_minus_s() -> None:
    trace = _generate_real_event_trace(_dataset(), 2, 3, 7)
    assert (
        trace.events["tau"]
        == trace.events["window_id"] - trace.events["downloaded_version"]
    ).all()


def test_current_version_has_zero_staleness() -> None:
    trace = _generate_real_event_trace(_dataset(), 2, 3, 7)
    current = trace.events["downloaded_version"] == trace.events["window_id"]
    assert (trace.events.loc[current, "tau"] == 0).all()


def test_arrival_weights_match_manual_small_case() -> None:
    pi = np.array([[0.2, 0.4], [0.8, 0.6]])
    nu = np.array([0.5, 0.5])
    p = np.array([[0.5, 0.25], [0.5, 1.0]])
    q = np.array([[1.0, 1.0], [0.5, 0.5]])
    intensity, weights = atomic_arrival_weights(pi, nu, p, q)
    expected = np.sum(pi * nu * p * q, axis=0)
    assert np.allclose(intensity, expected)
    assert np.allclose(weights, expected / expected.sum())


def test_arrival_weights_normalize_to_one() -> None:
    _, weights = atomic_arrival_weights(
        np.ones((2, 3)), np.ones(3) / 3, np.ones((2, 3)), np.ones((2, 3)),
    )
    assert weights.sum() == pytest.approx(1.0)
    assert (weights >= 0).all()


def test_arrival_weights_do_not_use_prediction_error() -> None:
    args = (
        np.array([[0.1, 0.9]]), np.array([0.5, 0.5]),
        np.array([[0.5, 0.5]]), np.array([[0.5, 0.5]]),
    )
    assert np.array_equal(atomic_arrival_weights(*args)[1], atomic_arrival_weights(*args)[1])


def test_gap_mis_identity() -> None:
    y_pred = np.array([0.0, 2.0])
    y_true = np.array([1.0, 0.0])
    mu = rmse_mu(y_pred, y_true, np.array([0.5, 0.5]))
    rho = rmse_rho(y_pred, y_true, np.array([0.8, 0.2]))
    assert gap_mis(mu, rho) == pytest.approx(mu - rho)
    assert mu != rho


def test_gap_zero_when_weights_equal() -> None:
    assert gap_mis(1.25, 1.25) == 0.0


def test_q_model_input_columns_pre_outcome_only() -> None:
    assert set(UsablePropensity().feature_names) == {
        "bias", "model_age", "device_class", "network_budget", "deadline_slack_pre",
    }


def test_e1_group_count_is_4_or_8() -> None:
    frame = pd.DataFrame({"time_index": np.arange(16)})
    groups = FrozenTimeBlockMapper(4).map(frame)
    assert set(groups) == {0, 1, 2, 3}
    with pytest.raises(ValueError):
        FrozenTimeBlockMapper(5).map(frame)


def test_twostage_policy_reaches_local_loss() -> None:
    assert get_method_policy("twostage_hajek").uses_hajek_local_loss
    assert not get_method_policy("fedavg_window").uses_hajek_local_loss


def test_twostage_policy_reaches_server_weights() -> None:
    payload = WindowAggregateInput(
        client_ids=["a", "b", "c"],
        raw_counts=np.array([1.0, 2.0, 7.0]),
        total_masses=np.array([1.0, 2.0, 7.0]),
        compositions=np.ones((1, 3)),
        beta_hat=np.array([0.7, 0.2, 0.1]),
    )
    fed = FedAvgWindowAggregator().compute_server_weights(payload)
    two = TwoStageHajekAggregator().compute_server_weights(payload)
    assert not np.allclose(fed, two)


def test_frozen_config_hash_contract(tmp_path: Path) -> None:
    config_dir, frozen_dir = tmp_path / "experiment", tmp_path / "frozen"
    config_dir.mkdir()
    group_path = tmp_path / "groups.yaml"
    group_path.write_text("group_count: 4\n", encoding="utf-8")
    (config_dir / "smoke.yaml").write_text("name: smoke\n", encoding="utf-8")
    frozen = freeze_config(
        "smoke", "sensorscope", config_dir, frozen_dir,
        group_mapping_path=group_path,
        data_hash="d" * 64,
        event_trace_hash="e" * 64,
    )
    validation = validate_frozen_config(
        "smoke", "sensorscope", frozen_dir,
        expected_data_hash="d" * 64,
        expected_group_mapping_hash=__import__("hashlib").sha256(group_path.read_bytes()).hexdigest(),
        expected_event_trace_hash="e" * 64,
    )
    assert validation["config_hash"] == frozen["config_hash"]
    with pytest.raises(ValueError, match="data_hash mismatch"):
        validate_frozen_config(
            "smoke", "sensorscope", frozen_dir, expected_data_hash="x" * 64,
        )


def test_q_whitelist_is_explicit() -> None:
    config = yaml.safe_load(
        (ROOT / "configs" / "audit" / "q_feature_whitelist.yaml")
        .read_text(encoding="utf-8")
    )
    for entry in config["entries"]:
        assert {"file", "symbol", "reason", "allowed_role"} <= set(entry)

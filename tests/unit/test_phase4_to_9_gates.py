"""Phase 4–9 EventTrace / model / window / aggregator / hard-gate tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import torch

from raven_mcs.aggregation.methods import get_aggregator
from raven_mcs.models.common_ndmf import CommonNDMF, deterministic_common_ndmf
from raven_mcs.propensity.observation import ObservationPropensity
from raven_mcs.propensity.usable import UsablePropensity
from raven_mcs.simulation.event_trace import (
    assert_methods_share_trace,
    freeze_event_trace,
    synthesize_event_trace,
    verify_event_trace_hash,
)
from raven_mcs.training.synthetic_gate_runner import build_synthetic_runner


def test_event_trace_freeze_and_g1_hash(tmp_path: Path) -> None:
    trace = synthesize_event_trace(num_windows=3, num_clients=2, seed=11, usable_rate=1.0)
    identity = freeze_event_trace(trace, tmp_path / "trace")
    assert identity["trace_hash"]
    assert verify_event_trace_hash(tmp_path / "trace", identity["trace_hash"]) == []
    assert_methods_share_trace({"a": identity["trace_hash"], "b": identity["trace_hash"]})
    # Tamper
    path = tmp_path / "trace" / "events.parquet"
    path.write_bytes(path.read_bytes() + b"x")
    assert verify_event_trace_hash(tmp_path / "trace")


def test_common_ndmf_shape_no_client_embedding_deterministic() -> None:
    m1 = deterministic_common_ndmf(8, seed=26001)
    m2 = deterministic_common_ndmf(8, seed=26001)
    m1.eval()
    m2.eval()
    x = torch.zeros(5, dtype=torch.long)
    hour = torch.tensor([0.0, 1.0, 2.0, 3.0, 4.0])
    weekday = torch.zeros(5)
    trend = torch.linspace(0, 1, 5)
    with torch.no_grad():
        y1 = m1(x, hour, weekday, trend)
        y2 = m2(x, hour, weekday, trend)
    assert y1.shape == (5,)
    assert torch.allclose(y1, y2)
    assert m1.uses_client_embedding() is False
    # No parameter name suggests client id embedding.
    assert not any("client" in name for name, _ in m1.named_parameters())


def test_window_runner_g2_invariants() -> None:
    trace = synthesize_event_trace(num_windows=4, num_clients=3, seed=26001, usable_rate=1.0)
    runner = build_synthetic_runner(trace, method="fedavg", n_groups=2)
    metrics = runner.run()
    assert len(metrics) == 4
    for item in metrics:
        if item.active:
            assert item.theta_hash_before != item.theta_hash_after
            assert abs(sum(item.alpha) - 1.0) < 1e-8


def test_aggregators_and_raven_weights() -> None:
    from raven_mcs.aggregation.base import WindowAggregateInput

    payload = WindowAggregateInput(
        client_ids=["c0", "c1", "c2"],
        raw_counts=np.array([1.0, 2.0, 3.0]),
        total_masses=np.array([1.0, 2.0, 3.0]),
        compositions=np.array([[0.7, 0.2, 0.4], [0.3, 0.8, 0.6]]),
        beta_hat=np.array([0.2, 0.3, 0.5]),
        staleness=np.array([0.0, 1.0, 2.0]),
        variance_diag=np.ones(3),
        debt=np.array([0.1, 0.2]),
        mu=np.array([0.5, 0.5]),
    )
    fed = get_aggregator("fedavg").compute_server_weights(payload)
    two = get_aggregator("twostage_hajek").compute_server_weights(payload)
    raven = get_aggregator("raven").compute_server_weights(payload)
    assert abs(fed.sum() - 1) < 1e-9
    assert abs(two.sum() - 1) < 1e-9
    assert abs(raven.sum() - 1) < 1e-9
    np.testing.assert_allclose(two, payload.beta_hat)


def test_propensity_models_keep_u0_and_lag_update() -> None:
    obs = ObservationPropensity()
    usable = UsablePropensity()
    x = np.array([1.0, 0.0, 1.0, 0.5, 0.2])
    # Observation uses first 3 features.
    p0 = obs.predict(x[:3])
    obs.update_after_completion(x[:3], 0.0)
    assert 0 < p0 < 1
    q0 = usable.predict(x)
    usable.update_lagged(x, 0.0)  # keep U=0
    usable.update_lagged(x, 1.0)
    assert usable.q_min <= usable.predict(x) <= usable.q_max
    assert q0 >= usable.q_min

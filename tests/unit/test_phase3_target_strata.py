"""Phase 3 target / opportunity strata tests."""

from __future__ import annotations

import numpy as np
import pandas as pd

from raven_mcs.data.target import (
    GroupMapper,
    TargetBuilder,
    audit_target_support,
    client_atom_mass,
    client_stratum_mass,
)
from raven_mcs.opportunities.estimator import OpportunityEstimator
from raven_mcs.opportunities.strata import OpportunityStrataMapper


def _toy_atomic() -> pd.DataFrame:
    rows = []
    start = pd.Timestamp("2026-01-01T00:00:00Z")
    for t in range(10):
        for s in range(4):
            rows.append(
                {
                    "unit_id": f"n{s}_t{t}",
                    "spatial_id": f"n{s}",
                    "absolute_time": start + pd.Timedelta(hours=t),
                    "target_value": float(s + t),
                    "split": "train" if t < 6 else ("validation" if t < 8 else "test"),
                    "target_group": f"n{s}::block{t // 3}",
                    "opportunity_stratum": f"r{s // 2}::block{t // 3}::weekday",
                    "public_features": {},
                    "support_flag": True,
                    "time_index": t,
                    "is_warmup": t < 2,
                }
            )
    return pd.DataFrame(rows)


def test_target_builder_uniform_and_normalized() -> None:
    atomic = _toy_atomic()
    masses = TargetBuilder().build(atomic, split="test")
    assert abs(masses.atom_mass.sum() - 1.0) < 1e-12
    assert abs(masses.group_mass.sum() - 1.0) < 1e-12
    # Uniform over supported test units.
    assert np.allclose(masses.atom_mass.to_numpy(), masses.atom_mass.iloc[0])
    assert audit_target_support(masses) == []


def test_group_and_strata_mappers() -> None:
    atomic = _toy_atomic()
    groups = GroupMapper().map(atomic)
    strata = OpportunityStrataMapper().map(atomic)
    assert len(groups) == len(atomic)
    assert len(strata.unique()) >= 2


def test_client_stratum_and_atom_masses() -> None:
    lam = {
        "client-a": {"s1": 0.7, "s2": 0.3},
        "client-b": {"s1": 0.2, "s2": 0.8},
    }
    pi = client_stratum_mass(lam, {"s1": 0.5, "s2": 0.5})
    assert abs(float(pi.to_numpy().sum()) - 1.0) < 1e-12
    unit_stratum = pd.Series({"u1": "s1", "u2": "s1", "u3": "s2"})
    within = pd.Series({"u1": 0.4, "u2": 0.6, "u3": 1.0})
    atom = client_atom_mass(pi, unit_stratum, within)
    assert abs(float(atom.to_numpy().sum()) - 1.0) < 1e-12


def test_opportunity_estimator_is_lagged_ema() -> None:
    est = OpportunityEstimator(forgetting=0.5, smoothing=0.0)
    est.initialize_support([("c0", "s0"), ("c1", "s1")])
    est.update_window(0, {("c0", "s0"): 2.0})
    first = est.counts.copy()
    est.update_window(1, {("c1", "s1"): 3.0})
    assert first[("c0", "s0")] == 2.5
    assert est.counts[("c0", "s0")] == 1.25
    assert est.counts[("c1", "s1")] == 3.25
    tar = est.pi_hat()
    assert est.zeta_error(tar) == 0.0

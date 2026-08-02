from __future__ import annotations

import inspect
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from raven_mcs.aggregation.base import WindowAggregateInput
from raven_mcs.aggregation.methods import FedAsyncWindowAggregator, TimeAlignAggregator
from raven_mcs.correction.pi_target import load_pi_target
from raven_mcs.data.target import GroupMapper, TargetBuilder
from raven_mcs.data.window_dataset import extract_window_slice
from raven_mcs.experiments.e1_entry import (
    add_e1_groups,
    generate_balanced_trace,
    sensorscope_dataset,
)
from raven_mcs.metrics.accuracy import tail_head_rmse
from raven_mcs.propensity.observation import ObservationPropensity
from raven_mcs.training.window_runner import FullWindowRunner
from raven_mcs.utils.serialization import load_json, load_yaml

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def dataset():
    return sensorscope_dataset(ROOT)


def test_e1_main_groups_are_repeatable_time_blocks(dataset) -> None:
    grouped = add_e1_groups(dataset.atomic_df)
    hours = pd.to_datetime(grouped["absolute_time"], utc=True).dt.hour
    assert np.array_equal(grouped["target_group_main"], hours // 6)


def test_e1_main_groups_not_global_time_quartiles(dataset) -> None:
    grouped = add_e1_groups(dataset.atomic_df)
    global_quartile = pd.qcut(
        grouped["time_index"], 4, labels=False, duplicates="drop",
    )
    assert not np.array_equal(grouped["target_group_main"], global_quartile)


def test_all_four_groups_supported_in_each_split(dataset) -> None:
    grouped = add_e1_groups(dataset.atomic_df)
    support = grouped.groupby(["split", "target_group_main"]).size()
    assert all(support.get((split, group), 0) > 0
               for split in ("train", "validation", "test")
               for group in range(4))


def test_mu_derived_from_frozen_target_weights(dataset) -> None:
    grouped = add_e1_groups(dataset.atomic_df)
    target = TargetBuilder(
        group_mapper=GroupMapper("target_group_main"),
    ).build(grouped, split="test")
    mu = np.array([target.group_mass[str(group)] for group in range(4)])
    assert np.isclose(mu.sum(), 1.0)
    assert not np.allclose(mu, np.full(4, 0.25))


def test_local_training_uses_potential_measurement(dataset) -> None:
    trace, _ = generate_balanced_trace(dataset, seed=26001, num_windows=4)
    sliced = extract_window_slice(0, trace.events, dataset, coarse_time_groups=4)
    rec = next(record for record in sliced.records if record.observed_unit_ids)
    expected = dataset.get_potential_measurement(
        rec.client_id, rec.observed_unit_ids[0],
    )
    assert rec.observed_values[0] == expected


def test_local_training_never_falls_back_to_target_value() -> None:
    source = inspect.getsource(extract_window_slice)
    assert "get_potential_measurement" in source
    assert "obs_value = unit.target_value" not in source


def test_measurement_lookup_by_client_and_unit(dataset) -> None:
    row = dataset.client_df.iloc[0]
    assert dataset.get_potential_measurement(
        str(row.client_id), str(row.unit_id),
    ) == float(row.potential_measurement)


def test_missing_potential_measurement_fails(dataset) -> None:
    with pytest.raises(KeyError):
        dataset.get_potential_measurement("absent-client", "absent-unit")


def test_p_features_pre_outcome_only() -> None:
    assert ObservationPropensity().feature_names == (
        "bias", "hour_block", "planned_workload_pre",
    )


def test_observed_count_not_in_p_features() -> None:
    names = ObservationPropensity().feature_names
    assert "observed_count" not in names
    assert "raw_workload" not in names


def test_pi_target_client_stratum_sums_to_one() -> None:
    values, digest = load_pi_target(
        ROOT / "configs/frozen/e1_pi_target_client_stratum.parquet",
    )
    assert np.isclose(sum(values.values()), 1.0)
    assert len(digest) == 64


def test_zeta_uses_frozen_pi_target() -> None:
    source = inspect.getsource(FullWindowRunner._compute_zeta)
    assert "self.pi_target[(client_id, str(s))]" in source
    assert "np.ones(len(stratum_ids))" not in source


def test_first_stage_clip_rate_gate() -> None:
    report = load_json(
        ROOT / "outputs/validation/e1_r1_weight_safety_report.json",
    )
    assert report["first_stage_clip_rate"] <= 0.05
    assert report["second_stage_clip_rate"] <= 0.05
    assert report["median_n_eff"] >= 2.0
    assert report["a_max_unchanged"]


def test_weight_safety_selected_on_validation_only() -> None:
    frozen = load_yaml(ROOT / "configs/frozen/e1_weight_safety.yaml")
    assert frozen["selection_data"] == "validation_only"


@pytest.mark.xfail(
    reason="TimeAlign primary definition is unresolved; E1 intentionally blocked",
    strict=True,
)
def test_timealign_not_same_formula_as_fedasync() -> None:
    payload = WindowAggregateInput(
        client_ids=["a", "b"],
        raw_counts=np.array([1.0, 3.0]),
        total_masses=np.ones(2),
        compositions=np.full((2, 2), 0.5),
        staleness=np.array([0.0, 1.0]),
    )
    assert not np.allclose(
        FedAsyncWindowAggregator().compute_server_weights(payload),
        TimeAlignAggregator().compute_server_weights(payload),
    )


def test_variance_uses_lagged_history() -> None:
    runner = object.__new__(FullWindowRunner)
    runner.variance_mean = {}
    runner.variance_state = {}
    runner.variance_count = {}
    runner.variance_decay = 0.9
    FullWindowRunner._update_variance_state(
        runner, {"a": np.array([2.0, -2.0])}, ["a"],
    )
    first = runner.variance_state["a"]
    FullWindowRunner._update_variance_state(
        runner, {"a": np.array([4.0, -4.0])}, ["a"],
    )
    assert runner.variance_count["a"] == 2
    assert runner.variance_state["a"] != first


def test_p2_receives_normalized_staleness() -> None:
    source = inspect.getsource(FullWindowRunner._process_window)
    assert "raw_staleness / float(max(int(self.s_max), 1))" in source
    assert "normalized staleness must be in [0, 1]" in source


def test_empty_tail_group_fails_instead_of_zero() -> None:
    result = tail_head_rmse(
        np.array([1.0]), np.array([1.0]), np.array([1.0]),
        np.array([0.1, 0.2, 0.3, 0.4]), np.array([1]), np.full(4, 0.25),
    )
    assert np.isnan(result["tail_rmse"])

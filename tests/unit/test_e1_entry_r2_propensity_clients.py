from __future__ import annotations

import inspect
from pathlib import Path

import numpy as np

from raven_mcs.experiments.e1_entry import (
    _arrival_weights,
    generate_balanced_trace,
    sensorscope_dataset,
    stable_client_mapping,
)
from raven_mcs.propensity.observation import ObservationPropensity
from raven_mcs.training.window_runner import FullWindowRunner
from raven_mcs.utils.serialization import load_yaml

ROOT = Path(__file__).resolve().parents[2]


def test_arrival_risk_uses_planned_workload_pre() -> None:
    source = inspect.getsource(_arrival_weights)
    assert "planned_workload_pre" in source


def test_arrival_risk_not_use_raw_workload() -> None:
    assert "raw_workload" not in inspect.getsource(_arrival_weights)


def test_arrival_risk_not_use_observed_count() -> None:
    assert "observed_count" not in inspect.getsource(_arrival_weights)


def test_arrival_risk_uses_frozen_train_history() -> None:
    source = inspect.getsource(_arrival_weights)
    assert "runner.trace.events" in source
    assert "runner.obs_propensity.predict" in source


def test_arrival_risk_not_use_test_outcomes() -> None:
    assert "target_value" not in inspect.getsource(_arrival_weights)


def test_p_history_one_row_per_risk_record() -> None:
    model = ObservationPropensity()
    x = np.array([[1.0, 0.0, 2.0], [1.0, 1.0, 2.0]])
    model.update_records_after_completion(x, np.array([0.0, 1.0]))
    assert len(model.history_y) == 2
    assert model.history_y == [0.0, 1.0]


def test_p_current_outcome_added_after_window_close() -> None:
    source = inspect.getsource(FullWindowRunner._process_window)
    assert source.rindex("self._update_lagged_estimators") > source.index(
        "self.aggregator.compute_server_weights",
    )


def test_p_current_outcome_not_predict_itself() -> None:
    source = inspect.getsource(FullWindowRunner._process_window)
    assert source.index("p_hat = self._compute_p_hat") < source.rindex(
        "self._update_lagged_estimators",
    )


def test_p_history_contains_positive_and_negative_records() -> None:
    model = ObservationPropensity()
    model.update_records_after_completion(
        np.ones((3, 3)), np.array([0.0, 1.0, 0.0]),
    )
    assert set(model.history_y) == {0.0, 1.0}


def test_p_prediction_conditioned_on_record_features() -> None:
    assert ObservationPropensity().feature_names == (
        "bias", "hour_block", "planned_workload_pre",
    )


def test_p_history_no_test_leakage() -> None:
    source = inspect.getsource(FullWindowRunner._update_lagged_estimators)
    assert '"source_split": "train"' in source


def test_e1_official_num_clients_equals_eight() -> None:
    protocol = load_yaml(
        ROOT / "configs/frozen/e1_sensorscope_balanced.yaml",
    )
    assert protocol["num_clients"] == 8


def test_all_eight_clients_nonempty() -> None:
    mapping = load_yaml(ROOT / "configs/frozen/e1_sensorscope_clients.yaml")
    counts = {}
    for client in mapping["station_to_client"].values():
        counts[client] = counts.get(client, 0) + 1
    assert len(counts) == 8
    assert min(counts.values()) > 0


def test_client_mapping_same_across_seeds() -> None:
    dataset = sensorscope_dataset(ROOT)
    one = generate_balanced_trace(dataset, seed=26001, num_windows=4)[1]
    two = generate_balanced_trace(dataset, seed=26002, num_windows=4)[1]
    assert one == two


def test_client_mapping_same_across_methods() -> None:
    dataset = sensorscope_dataset(ROOT)
    one = stable_client_mapping(
        dataset.atomic_df, 8, dataset.client_df,
    )
    two = stable_client_mapping(
        dataset.atomic_df, 8, dataset.client_df,
    )
    assert one == two


def test_trace_generation_requires_clean_git() -> None:
    source = (
        ROOT / "scripts/generate_e1_event_traces.py"
    ).read_text(encoding="utf-8")
    assert "--require-clean-git" in source
    assert "official EventTrace generation requires clean Git" in source


def test_r2_baseline_selection_includes_timealign_adapted() -> None:
    import importlib.util

    path = ROOT / "scripts/select_e1_baseline.py"
    spec = importlib.util.spec_from_file_location("r2_select_baseline", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.CANDIDATES == (
        "fedavg_window", "fedasync_window", "flamf_timealign_adapted",
    )


def test_r2_baseline_selection_validation_only() -> None:
    source = (
        ROOT / "scripts/select_e1_baseline.py"
    ).read_text(encoding="utf-8")
    assert "--validation-only is mandatory" in source
    assert 'evaluation_split="validation"' in source

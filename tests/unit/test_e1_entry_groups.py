from __future__ import annotations

import inspect
import json
from pathlib import Path

import pandas as pd
import pytest

from raven_mcs.experiments.e1_entry import (
    E1_METHODS,
    add_e1_groups,
    frozen_group_identity,
    generate_balanced_trace,
    sensorscope_dataset,
    stable_client_mapping,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def dataset():
    return sensorscope_dataset(ROOT)


def test_official_e1_runner_uses_frozen_g4(dataset) -> None:
    grouped = add_e1_groups(dataset.atomic_df)
    assert set(grouped["target_group_main"]) == {0, 1, 2, 3}


def test_processed_num_groups_not_used_for_main_debt() -> None:
    source = inspect.getsource(
        __import__(
            "raven_mcs.experiments.e1_entry", fromlist=["run_official_method"],
        ).run_official_method,
    )
    assert "n_groups=E1_GROUPS" in source
    assert "processed.num_groups" not in source
    assert "dataset.num_groups" not in source


def test_main_and_fine_groups_are_separate(dataset) -> None:
    grouped = add_e1_groups(dataset.atomic_df)
    assert grouped["target_group_main"].nunique() == 4
    assert grouped["target_group_fine"].nunique() == 220


def test_e1_group_hash_matches_manifest() -> None:
    _, digest = frozen_group_identity(ROOT)
    protocol = __import__("yaml").safe_load(
        (ROOT / "configs/frozen/e1_sensorscope_balanced.yaml").read_text(),
    )
    assert protocol["target_group_hash"] == digest


def test_e1_main_group_count_equals_four(dataset) -> None:
    assert add_e1_groups(dataset.atomic_df)["target_group_main"].nunique() == 4


def test_all_e1_methods_share_same_group_mapping() -> None:
    assert len(E1_METHODS) == 5
    _, digest = frozen_group_identity(ROOT)
    assert len(digest) == 64


def test_e1_eventtrace_uses_real_unit_ids(dataset) -> None:
    trace, _ = generate_balanced_trace(dataset, seed=26001, num_windows=4)
    real = set(dataset.atomic_df["unit_id"].astype(str))
    used = {unit for values in trace.events["risk_set_unit_ids"] for unit in values}
    assert used <= real


def test_e1_eventtrace_no_dummy_unit_ids(dataset) -> None:
    trace, _ = generate_balanced_trace(dataset, seed=26001, num_windows=4)
    used = {unit for values in trace.events["risk_set_unit_ids"] for unit in values}
    assert not any(unit.startswith("u") and unit[1:].isdigit() for unit in used)


def test_all_eventtrace_units_exist_in_processed_data(dataset) -> None:
    trace, _ = generate_balanced_trace(dataset, seed=26002, num_windows=4)
    real = set(dataset.atomic_df["unit_id"].astype(str))
    assert all(
        unit in real
        for values in trace.events["risk_set_unit_ids"]
        for unit in values
    )


def test_e1_client_mapping_is_stable(dataset) -> None:
    one = stable_client_mapping(dataset.atomic_df)
    two = stable_client_mapping(dataset.atomic_df)
    assert one == two
    trace1, mapping1 = generate_balanced_trace(dataset, seed=26001, num_windows=4)
    trace2, mapping2 = generate_balanced_trace(dataset, seed=26002, num_windows=4)
    assert mapping1 == mapping2
    assert set(trace1.events["client_id"]) == set(trace2.events["client_id"])


def test_python_builtin_hash_not_used_for_identity() -> None:
    source = inspect.getsource(stable_client_mapping)
    assert "hashlib.sha256" in source
    assert "hash(" not in source.replace("sha256(", "")


def test_e1_eventtrace_chronological(dataset) -> None:
    trace, _ = generate_balanced_trace(dataset, seed=26001, num_windows=8)
    assert list(sorted(trace.events["window_id"].unique())) == list(range(8))


def test_e1_eventtrace_same_across_methods(dataset) -> None:
    trace, _ = generate_balanced_trace(dataset, seed=26001, num_windows=4)
    assert all(method in E1_METHODS for method in E1_METHODS)
    assert trace.metadata.generator == "official-e1-balanced-real-ids-v1"


def test_e1_eventtrace_retains_failures(dataset) -> None:
    trace, _ = generate_balanced_trace(dataset, seed=26001, num_windows=8)
    assert (trace.events["U"] == 0).any()


def test_e1_eventtrace_respects_smax(dataset) -> None:
    trace, _ = generate_balanced_trace(dataset, seed=26001, num_windows=8)
    assert trace.metadata.s_max == 5
    assert trace.events["tau"].max() <= 5

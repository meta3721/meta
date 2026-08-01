from __future__ import annotations

import pandas as pd

from raven_mcs.data.audit import (
    assert_record_sources_disjoint,
    audit_processed_bundle,
)
from raven_mcs.data.fleet import assert_fleet_disjoint, stratified_fleet_split
from raven_mcs.data.scaling import TrainOnlyStandardizer
from raven_mcs.data.synthetic import SyntheticDatasetAdapter


def test_train_only_scaling() -> None:
    frame = pd.DataFrame(
        {
            "value": [1.0, 3.0, 10_000.0, -10_000.0],
            "split": ["train", "train", "validation", "test"],
        }
    )
    scaler = TrainOnlyStandardizer.fit(frame, ["value"])
    statistic = scaler.statistics[0]
    assert statistic.mean == 2.0
    assert statistic.scale == 1.0
    assert statistic.train_count == 2
    transformed = scaler.transform(frame)
    assert transformed.loc[:1, "value_standardized"].tolist() == [-1.0, 1.0]


def test_reference_client_disjoint() -> None:
    lengths = pd.Series(
        {f"vehicle-{index:03d}": float(index + 10) for index in range(100)}
    )
    assignment = stratified_fleet_split(lengths, seed=19)
    assert_fleet_disjoint(assignment)
    assert (assignment["fleet"] == "reference").sum() == 30
    reference = set(assignment.loc[assignment["fleet"] == "reference", "vehicle_id"])
    clients = set(assignment.loc[assignment["fleet"] == "client", "vehicle_id"])
    assert reference.isdisjoint(clients)


def test_audit_rejects_target_client_source_reuse(tmp_path) -> None:
    bundle = SyntheticDatasetAdapter().prepare(tmp_path, seed=4)
    bundle.target_source_trace_ids.add(
        str(bundle.client_measurements.iloc[0]["source_trace_id"])
    )
    result = audit_processed_bundle(bundle)
    assert not result.passed
    assert any("source records overlap" in error for error in result.errors)


def test_synthetic_bundle_passes_data_audit(tmp_path) -> None:
    bundle = SyntheticDatasetAdapter().prepare(tmp_path, seed=4)
    result = audit_processed_bundle(bundle)
    assert result.passed
    assert result.statistics["split_counts"] == {
        "test": 24,
        "train": 72,
        "validation": 24,
    }
    assert_record_sources_disjoint(
        bundle.target_source_trace_ids,
        bundle.client_measurements["source_trace_id"],
    )

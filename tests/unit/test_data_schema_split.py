from __future__ import annotations

import pandas as pd
import pyarrow.parquet as pq
import pytest

from raven_mcs.data.schema import (
    ATOMIC_REQUIRED_COLUMNS,
    CLIENT_REQUIRED_COLUMNS,
    ProcessedSchemaError,
    normalize_atomic_units,
    normalize_client_measurements,
    write_processed_parquet,
)
from raven_mcs.data.split import (
    TemporalSplitError,
    assert_split_no_overlap,
    assign_temporal_splits,
)
from raven_mcs.data.synthetic import SyntheticDatasetAdapter


def test_processed_schema_and_parquet_round_trip(tmp_path) -> None:
    bundle = SyntheticDatasetAdapter().prepare(tmp_path, seed=7)
    atomic_path, client_path = write_processed_parquet(
        bundle.atomic_units, bundle.client_measurements, tmp_path
    )

    atomic = pd.read_parquet(atomic_path)
    clients = pd.read_parquet(client_path)
    assert set(ATOMIC_REQUIRED_COLUMNS).issubset(atomic.columns)
    assert set(CLIENT_REQUIRED_COLUMNS).issubset(clients.columns)
    assert str(atomic["absolute_time"].dtype) == "datetime64[ns, UTC]"
    assert atomic["unit_id"].is_unique
    assert pq.read_schema(atomic_path).metadata[b"schema_version"] == b"2.3.0"


def test_client_schema_requires_measurement_or_generator_parameters() -> None:
    frame = pd.DataFrame(
        [
            {
                "client_id": "c1",
                "unit_id": "u1",
                "potential_measurement": None,
                "controlled_generator_parameters": None,
                "split": "train",
                "source_trace_id": "s1",
            }
        ]
    )
    with pytest.raises(ProcessedSchemaError, match="needs potential_measurement"):
        normalize_client_measurements(frame)


def test_atomic_schema_rejects_string_boolean(tmp_path) -> None:
    bundle = SyntheticDatasetAdapter().prepare(tmp_path, seed=7)
    invalid = bundle.atomic_units.copy()
    invalid["support_flag"] = invalid["support_flag"].astype(object)
    invalid.loc[0, "support_flag"] = "False"
    with pytest.raises(ProcessedSchemaError, match="only boolean"):
        normalize_atomic_units(invalid)


def test_split_no_overlap() -> None:
    times = pd.date_range("2026-01-01", periods=10, freq="h", tz="UTC")
    frame = pd.DataFrame(
        [
            {
                "unit_id": f"{spatial}-{time_index}",
                "spatial_id": spatial,
                "absolute_time": time,
            }
            for time_index, time in enumerate(times)
            for spatial in ("a", "b")
        ]
    )
    result = assign_temporal_splits(frame)
    assert_split_no_overlap(result)
    assert result.groupby("split")["absolute_time"].nunique().to_dict() == {
        "test": 2,
        "train": 6,
        "validation": 2,
    }
    assert result.loc[result["is_warmup"], "absolute_time"].nunique() == 2


def test_split_detects_absolute_time_overlap() -> None:
    frame = pd.DataFrame(
        {
            "unit_id": ["a", "b", "c"],
            "absolute_time": pd.to_datetime(
                ["2026-01-01", "2026-01-01", "2026-01-03"], utc=True
            ),
            "split": ["train", "validation", "test"],
        }
    )
    with pytest.raises(TemporalSplitError, match="absolute_time overlaps"):
        assert_split_no_overlap(frame)

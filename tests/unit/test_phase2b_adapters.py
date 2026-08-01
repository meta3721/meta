"""Phase 2B adapter contract tests (fixtures; no silent dataset substitution)."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from raven_mcs.data.fleet import assert_fleet_disjoint
from raven_mcs.data.registry import AdapterUnavailableError, get_dataset_adapter
from raven_mcs.data.traffic import TrafficAdapter, TrafficQualityError
from raven_mcs.data.tdrive import TDriveSpeedAdapter


def test_real_names_are_registered_not_synthetic() -> None:
    for name in ("sensorscope", "uair", "traffic", "tdrive_speed"):
        adapter = get_dataset_adapter(name)
        assert adapter.name in {"sensorscope", "uair", "traffic", "tdrive_speed"}
        assert adapter.name != "synthetic"


def test_unknown_adapter_still_errors() -> None:
    with pytest.raises(KeyError):
        get_dataset_adapter("pems_bay_silent_substitute")


def test_traffic_floor_rejects_sparse_matrix(tmp_path: Path) -> None:
    raw = tmp_path / "traffic"
    raw.mkdir(parents=True)
    stations = pd.DataFrame({"station_key": [f"s{i}" for i in range(5)]})
    stations.to_csv(raw / "road_traffic_counts_station_reference.csv", index=False)

    # Build a tiny wide hourly table that cannot meet 30×336.
    rows = []
    for day in range(2):
        row = {
            "station_key": "s0",
            "date": f"2020-01-{day + 1:02d}",
        }
        for hour in range(24):
            row[f"hour_{hour:02d}"] = 10.0
        rows.append(row)
    frame = pd.DataFrame(rows)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("road_traffic_counts_hourly_permanent0.csv", frame.to_csv(index=False))
    (raw / "road_traffic_counts_hourly_permanent.zip").write_bytes(buf.getvalue())

    with pytest.raises(TrafficQualityError, match="hard floor"):
        TrafficAdapter().prepare(raw, seed=26001)


def test_tdrive_fleet_disjoint_and_source_separation(tmp_path: Path) -> None:
    raw = tmp_path / "tdrive_speed"
    raw.mkdir(parents=True)
    # Synthetic mini trajectories mimicking official CSV layout.
    # Need >=5 half-hour slots after reference aggregation and physical filters.
    rng = np.random.default_rng(0)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for vehicle in range(20):
            lines = []
            lon, lat = 116.35, 39.95
            t0 = pd.Timestamp("2008-02-02T08:00:00Z")
            for step in range(180):
                # ~0.004 deg / 2 min ≈ 13 km/h on average (inside 5–120).
                lon += 0.004 + float(rng.normal(0, 0.0005))
                lat += float(rng.normal(0, 0.0005))
                lon = float(np.clip(lon, 116.05, 116.75))
                lat = float(np.clip(lat, 39.65, 40.15))
                ts = t0 + pd.Timedelta(minutes=2 * step)
                lines.append(
                    f"{1000 + vehicle},{ts.strftime('%Y-%m-%d %H:%M:%S')},{lon:.5f},{lat:.5f}"
                )
            zf.writestr(f"{1000 + vehicle}.txt", "\n".join(lines) + "\n")
    (raw / "06.zip").write_bytes(buf.getvalue())

    bundle = TDriveSpeedAdapter().prepare(raw, seed=31)
    assert bundle.fleet_assignments is not None
    assert_fleet_disjoint(bundle.fleet_assignments)
    overlap = bundle.target_source_trace_ids & set(
        bundle.client_measurements["source_trace_id"].astype(str)
    )
    assert not overlap
    assert bundle.atomic_units["absolute_time"].nunique() >= 5
    assert len(bundle.client_measurements) > 0


def test_adapter_unavailable_error_still_exported() -> None:
    assert issubclass(AdapterUnavailableError, NotImplementedError)

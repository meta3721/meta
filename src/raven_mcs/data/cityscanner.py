"""City Scanner NYC PM2.5 → 500 m × 30 min cells as federated clients.

Y is mean calibrated PM2.5 in an occupied cell-slot. GPS only places the visit.
Vehicles / SensorID are audit-only and are never FL clients.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

from raven_mcs.data.base import DatasetAdapter, DatasetMetadata, ProcessedBundle
from raven_mcs.data.controlled import public_time_features, time_of_day_block, weekday_label
from raven_mcs.data.schema import (
    normalize_atomic_units,
    normalize_client_measurements,
)
from raven_mcs.data.split import TemporalSplitConfig, assign_temporal_splits
from raven_mcs.utils.config import repo_root_from_here
from raven_mcs.utils.serialization import load_json, load_yaml

EARTH_KM_PER_DEG_LAT = 111.32
REQUIRED_FILES = (
    "NYC_Pilot1_PM.csv",
    "NYC_Pilot2_PM_Part1.csv",
    "NYC_Pilot2_PM_Part2.csv",
    "NYC_Pilot2_PM_Part3.csv",
)
REGION_ORDER = ("region0", "region1", "region2", "region3")


class CityScannerNYCPM25Adapter(DatasetAdapter):
    @property
    def name(self) -> str:
        return "cityscanner_nyc_pm25"

    def discover_raw_files(self, raw_root: Path) -> tuple[Path, ...]:
        root = Path(raw_root)
        license_path = root / "LICENSE.json"
        if not license_path.is_file():
            raise FileNotFoundError(
                f"City Scanner LICENSE.json missing under {root}; copy from Zenodo"
            )
        license_meta = load_json(license_path)
        if str(license_meta.get("license_id") or "").lower() != "cc-by-4.0":
            raise RuntimeError(
                "City Scanner ingest aborted: LICENSE.json is not cc-by-4.0 from Zenodo"
            )
        files = []
        for name in REQUIRED_FILES:
            path = root / name
            if not path.is_file():
                raise FileNotFoundError(f"Missing City Scanner NYC PM file: {path}")
            files.append(path)
        return tuple(files)

    def prepare(self, raw_root: Path, *, seed: int) -> ProcessedBundle:
        del seed  # temporal split is deterministic; vehicles are not clients
        files = self.discover_raw_files(raw_root)
        cfg = load_yaml(
            repo_root_from_here() / "configs" / "dataset" / "cityscanner_nyc_pm25.yaml"
        )
        cell_meters = int(cfg["grid"]["cell_meters"])
        slot_minutes = int(cfg["grid"]["slot_minutes"])
        if cell_meters != 500 or slot_minutes != 30:
            raise RuntimeError("City Scanner grid/slot must stay 500 m × 30 min")

        points, anomalies, parse_meta = _load_nyc_pm_points(files)
        raw_n = int(len(points))
        keep, drop_rows = _physical_filter(points)
        anomalies = pd.concat([anomalies, drop_rows], ignore_index=True)
        dropped = int(raw_n - len(keep))
        if keep.empty:
            raise RuntimeError("City Scanner ingest aborted: no rows after physical filters")

        # Origin = observed min lon/lat of kept GPS (no Y). Cell index uses floor.
        lon0 = float(keep["longitude"].min())
        lat0 = float(keep["latitude"].min())
        lon1 = float(keep["longitude"].max())
        lat1 = float(keep["latitude"].max())
        gx, gy, spatial = _grid_xy(
            keep["longitude"],
            keep["latitude"],
            lon0=lon0,
            lat0=lat0,
            lon1=lon1,
            lat1=lat1,
            cell_meters=cell_meters,
        )
        keep = keep.copy()
        keep["gx"] = gx
        keep["gy"] = gy
        keep["spatial_id"] = spatial
        keep["slot_time"] = keep["absolute_time"].dt.floor(f"{slot_minutes}min")

        atomic_src = (
            keep.groupby(["spatial_id", "gx", "gy", "slot_time"], as_index=False)
            .agg(
                target_value=("pm25", "mean"),
                support_n=("pm25", "size"),
                n_sensors=("sensor_id", "nunique"),
            )
        )
        n_cells = int(atomic_src["spatial_id"].nunique())
        n_slots = int(atomic_src["slot_time"].nunique())
        if n_cells < 20:
            raise RuntimeError(
                f"City Scanner ingest aborted: unique occupied cells={n_cells} < 20"
            )
        if n_slots < 120:
            raise RuntimeError(
                f"City Scanner ingest aborted: unique occupied 30min slots={n_slots} < 120"
            )

        cells = atomic_src.drop_duplicates("spatial_id")[["spatial_id", "gx", "gy"]]
        mx = float(cells["gx"].median())
        my = float(cells["gy"].median())
        region_map = {
            str(r.spatial_id): "region%d"
            % ((int(r.gx >= mx) << 1) + int(r.gy >= my))
            for r in cells.itertuples(index=False)
        }
        region_counts = {name: 0 for name in REGION_ORDER}
        for rid in region_map.values():
            region_counts[rid] += 1

        rows: list[dict[str, object]] = []
        for record in atomic_src.itertuples(index=False):
            spatial_id = str(record.spatial_id)
            region = region_map[spatial_id]
            absolute_time = pd.Timestamp(record.slot_time)
            if absolute_time.tzinfo is None:
                absolute_time = absolute_time.tz_localize("UTC")
            else:
                absolute_time = absolute_time.tz_convert("UTC")
            block = time_of_day_block(absolute_time)
            unit_id = f"{spatial_id}_{absolute_time.strftime('%Y%m%dT%H%MZ')}"
            rows.append(
                {
                    "unit_id": unit_id,
                    "spatial_id": spatial_id,
                    "absolute_time": absolute_time,
                    "target_value": float(record.target_value),
                    "target_group": region,
                    "opportunity_stratum": (
                        f"{region}::block{block}::{weekday_label(absolute_time)}"
                    ),
                    "public_features": {
                        **public_time_features(absolute_time),
                        "support_n": int(record.support_n),
                        "n_sensors_audit_only": int(record.n_sensors),
                        "gx": int(record.gx),
                        "gy": int(record.gy),
                        "cell_meters": cell_meters,
                        "slot_minutes": slot_minutes,
                    },
                    "support_flag": True,
                }
            )
        atomic = assign_temporal_splits(
            pd.DataFrame(rows), config=TemporalSplitConfig()
        )
        atomic["unit_id"] = (
            atomic["spatial_id"].astype(str)
            + "_t"
            + atomic["time_index"].astype(int).map(lambda i: f"{i:05d}")
        )
        target_ids = {
            f"cityscanner::atomic::{uid}" for uid in atomic["unit_id"].astype(str)
        }
        n_strata = int(atomic["opportunity_stratum"].nunique())
        if n_strata > 32:
            raise RuntimeError(
                f"City Scanner ingest aborted: opportunity strata={n_strata} > 32"
            )
        test = atomic.loc[atomic["split"].astype(str) == "test"]
        test_regions = set(test["target_group"].astype(str))
        missing_test = [r for r in REGION_ORDER if r not in test_regions]
        if missing_test:
            raise RuntimeError(
                "City Scanner ingest aborted: test split missing region(s) "
                f"{missing_test}"
            )
        atomic = normalize_atomic_units(atomic)

        clients = normalize_client_measurements(
            pd.DataFrame(
                {
                    "client_id": atomic["spatial_id"].astype(str),
                    "unit_id": atomic["unit_id"].astype(str),
                    "potential_measurement": atomic["target_value"].astype(float),
                    "controlled_generator_parameters": None,
                    "split": atomic["split"].astype(str),
                    "source_trace_id": (
                        "cityscanner::cell::"
                        + atomic["spatial_id"].astype(str)
                        + "::"
                        + atomic["unit_id"].astype(str)
                    ),
                }
            )
        )
        if clients["client_id"].astype(str).str.startswith("NYCP").any():
            raise RuntimeError(
                "City Scanner ingest aborted: vehicle/SensorID used as FL client"
            )
        if set(clients["client_id"].astype(str)) != set(atomic["spatial_id"].astype(str)):
            raise RuntimeError(
                "City Scanner ingest aborted: client_id must equal spatial_id"
            )

        metadata = DatasetMetadata(
            dataset="cityscanner_nyc_pm25",
            target_name=str(cfg["target"]["name"]),
            target_unit=str(cfg["target"]["unit"]),
            spatial_unit="grid_cell_500m",
            time_unit="30min",
            source_name=str(cfg["download"]["source_name"]),
            source_url=str(cfg["download"]["source_url"]),
            raw_license=str(cfg["download"]["license"]),
            filtering_rules=tuple(cfg["physical_filters"]),
            notes=(
                "Y=mean finite pm25 in occupied 500m x 30min cell; GPS only for R",
                "FL clients are grid cells (spatial_id), never SensorID/vehicles",
                "h(i)=4 quadrants from median gx,gy over all occupied cells, no Y",
                "s(i)=region::block::weekday, at most 32 strata",
                "hybrid O/U: p_obs=0.35, s_max=5; not end-to-end MCS",
            ),
        )
        audit = {
            "raw_record_count": raw_n,
            "dropped_record_count": dropped,
            "atomic_units": int(len(atomic)),
            "client_rows": int(len(clients)),
            "n_occupied_cells": n_cells,
            "n_occupied_slots": n_slots,
            "n_opportunity_strata": n_strata,
            "cell_meters": cell_meters,
            "slot_minutes": slot_minutes,
            "grid_origin_lon": lon0,
            "grid_origin_lat": lat0,
            "grid_max_lon": lon1,
            "grid_max_lat": lat1,
            "median_gx": mx,
            "median_gy": my,
            "region_cell_counts": region_counts,
            "used_y_for_h": False,
            "clients_are_spatial_id": True,
            "vehicles_are_fl_clients": False,
            "n_unique_sensor_ids_audit_only": int(keep["sensor_id"].nunique()),
            **parse_meta,
        }
        return ProcessedBundle(
            atomic_units=atomic,
            client_measurements=clients,
            metadata=metadata,
            target_source_trace_ids=target_ids,
            anomaly_records=anomalies,
            audit_context=audit,
        )


def _load_nyc_pm_points(
    files: tuple[Path, ...],
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    frames: list[pd.DataFrame] = []
    n_by_file: dict[str, int] = {}
    for path in files:
        header = pd.read_csv(path, nrows=0)
        cols = [c for c in ("time", "latitude", "longitude", "pm25", "SensorID") if c in header.columns]
        missing = [c for c in ("time", "latitude", "longitude", "pm25") if c not in header.columns]
        if missing:
            raise RuntimeError(f"{path.name} missing columns {missing}")
        chunk = pd.read_csv(path, usecols=cols)
        n_by_file[path.name] = int(len(chunk))
        if "SensorID" not in chunk.columns:
            chunk["SensorID"] = "unknown"
        frames.append(chunk.rename(columns={"SensorID": "sensor_id"}))
    raw = pd.concat(frames, ignore_index=True)
    time_num = pd.to_numeric(raw["time"], errors="coerce")
    unit = "ms" if float(np.nanmedian(time_num.to_numpy(dtype=np.float64))) > 1e12 else "s"
    absolute_time = pd.to_datetime(time_num, unit=unit, utc=True, errors="coerce")
    points = pd.DataFrame(
        {
            "sensor_id": raw["sensor_id"].astype(str),
            "absolute_time": absolute_time,
            "latitude": pd.to_numeric(raw["latitude"], errors="coerce"),
            "longitude": pd.to_numeric(raw["longitude"], errors="coerce"),
            "pm25": pd.to_numeric(raw["pm25"], errors="coerce"),
            "source_file": np.repeat(
                [p.name for p in files],
                [n_by_file[p.name] for p in files],
            ),
        }
    )
    anomalies = pd.DataFrame(columns=["source_trace_id", "rule", "action", "value"])
    parse_meta = {
        "n_rows_by_file": n_by_file,
        "time_unit": unit,
        "n_raw_concat": int(len(points)),
    }
    return points, anomalies, parse_meta


def _physical_filter(points: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    lat = points["latitude"].to_numpy(dtype=np.float64)
    lon = points["longitude"].to_numpy(dtype=np.float64)
    pm = points["pm25"].to_numpy(dtype=np.float64)
    finite = (
        np.isfinite(lat)
        & np.isfinite(lon)
        & np.isfinite(pm)
        & points["absolute_time"].notna().to_numpy()
    )
    phys = finite & (pm >= 0.0) & (pm <= 1000.0)
    dropped = points.loc[~phys].copy()
    rows = []
    if not dropped.empty:
        rows.append(
            {
                "source_trace_id": "cityscanner::aggregate",
                "rule": "nonfinite_or_pm25_outside_0_1000",
                "action": "drop",
                "value": str(int(len(dropped))),
            }
        )
    anomalies = pd.DataFrame(
        rows, columns=["source_trace_id", "rule", "action", "value"]
    )
    return points.loc[phys].copy(), anomalies


def _grid_xy(
    longitude: pd.Series,
    latitude: pd.Series,
    *,
    lon0: float,
    lat0: float,
    lon1: float,
    lat1: float,
    cell_meters: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    cell_km = cell_meters / 1000.0
    lat_deg = cell_km / EARTH_KM_PER_DEG_LAT
    if lon1 < lon0 or lat1 < lat0:
        raise RuntimeError("City Scanner GPS bbox is empty")
    mid_lat = 0.5 * (lat0 + lat1)
    lon_deg = cell_km / (
        EARTH_KM_PER_DEG_LAT * max(0.2, math.cos(math.radians(mid_lat)))
    )
    gx = np.floor((longitude.to_numpy(dtype=np.float64) - lon0) / lon_deg).astype(int)
    gy = np.floor((latitude.to_numpy(dtype=np.float64) - lat0) / lat_deg).astype(int)
    spatial = np.asarray(
        [f"g{int(x):04d}_{int(y):04d}" for x, y in zip(gx, gy)], dtype=object
    )
    return gx, gy, spatial

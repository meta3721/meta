"""MSR T-Drive trajectory sample → grid speed field with fleet split."""

from __future__ import annotations

import math
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from raven_mcs.data.base import DatasetAdapter, DatasetMetadata, ProcessedBundle
from raven_mcs.data.controlled import public_time_features, time_of_day_block, weekday_label
from raven_mcs.data.fleet import assert_fleet_disjoint, stratified_fleet_split
from raven_mcs.data.schema import (
    normalize_atomic_units,
    normalize_client_measurements,
)
from raven_mcs.data.split import TemporalSplitConfig, assign_temporal_splits
from raven_mcs.utils.config import repo_root_from_here
from raven_mcs.utils.serialization import load_yaml

# Beijing bounding box used by the public T-Drive sample.
LON_MIN, LON_MAX = 116.0, 116.8
LAT_MIN, LAT_MAX = 39.6, 40.2
EARTH_KM_PER_DEG_LAT = 111.32


class TDriveSpeedAdapter(DatasetAdapter):
    @property
    def name(self) -> str:
        return "tdrive_speed"

    def discover_raw_files(self, raw_root: Path) -> tuple[Path, ...]:
        root = Path(raw_root)
        zips = sorted(root.glob("*.zip"))
        if not zips:
            raise FileNotFoundError(f"No T-Drive sample zips under {root}")
        return tuple(zips)

    def prepare(self, raw_root: Path, *, seed: int) -> ProcessedBundle:
        archives = self.discover_raw_files(raw_root)
        cfg = load_yaml(
            repo_root_from_here() / "configs" / "dataset" / "tdrive_speed.yaml"
        )
        cell_meters = int(cfg["grid"]["cell_meters"])
        slot_minutes = int(cfg["grid"]["slot_minutes"])
        reference_fraction = float(cfg["fleet"]["reference_fraction"])

        points, anomalies, parse_meta = _load_tdrive_points(archives)
        segments = _segments_with_speed(points)
        before = len(segments)
        speed_ok = (segments["speed_kmh"] >= 5.0) & (segments["speed_kmh"] <= 120.0)
        dropped = int((~speed_ok).sum())
        anomalies = pd.concat(
            [
                anomalies,
                pd.DataFrame(
                    [
                        {
                            "source_trace_id": "tdrive::aggregate",
                            "rule": "speed_outside_5_120",
                            "action": "drop",
                            "value": str(dropped),
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )
        segments = segments.loc[speed_ok].copy()
        if segments.empty:
            raise RuntimeError("No T-Drive segments remain after speed filtering")

        segments["grid_id"] = _grid_ids(
            segments["longitude"], segments["latitude"], cell_meters=cell_meters
        )
        segments["slot_time"] = segments["absolute_time"].dt.floor(f"{slot_minutes}min")

        lengths = segments.groupby("vehicle_id").size().astype("float64")
        fleet = stratified_fleet_split(
            lengths,
            reference_fraction=reference_fraction,
            seed=int(seed),
        )
        assert_fleet_disjoint(fleet)
        fleet_map = fleet.set_index("vehicle_id")["fleet"].to_dict()
        segments["fleet"] = segments["vehicle_id"].map(fleet_map)
        segments = segments.dropna(subset=["fleet"])

        reference = segments.loc[segments["fleet"] == "reference"].copy()
        client = segments.loc[segments["fleet"] == "client"].copy()
        if reference.empty or client.empty:
            raise RuntimeError("T-Drive fleet split produced an empty fleet")

        atomic_src = (
            reference.groupby(["grid_id", "slot_time"], as_index=False)
            .agg(
                target_value=("speed_kmh", "mean"),
                support_n=("speed_kmh", "size"),
                source_trace_id=("source_trace_id", "first"),
            )
            .rename(columns={"grid_id": "spatial_id", "slot_time": "absolute_time"})
        )
        if atomic_src["absolute_time"].nunique() < 5:
            raise RuntimeError("T-Drive reference field has fewer than 5 time slots")

        times = pd.Index(atomic_src["absolute_time"].drop_duplicates().sort_values())
        time_to_index = {ts: idx for idx, ts in enumerate(times)}
        rows: list[dict[str, object]] = []
        target_ids: set[str] = set(atomic_src["source_trace_id"].astype(str))
        for record in atomic_src.itertuples(index=False):
            spatial_id = str(record.spatial_id)
            absolute_time = pd.Timestamp(record.absolute_time)
            time_index = time_to_index[absolute_time]
            unit_id = f"{spatial_id}_t{time_index:05d}"
            block = time_of_day_block(absolute_time)
            rows.append(
                {
                    "unit_id": unit_id,
                    "spatial_id": spatial_id,
                    "absolute_time": absolute_time,
                    "time_index": int(time_index),
                    "target_value": float(record.target_value),
                    "target_group": f"{spatial_id}::block{block}",
                    "opportunity_stratum": (
                        f"{spatial_id}::block{block}::{weekday_label(absolute_time)}"
                    ),
                    "public_features": {
                        **public_time_features(absolute_time),
                        "support_n": int(record.support_n),
                        "cell_meters": cell_meters,
                        "slot_minutes": slot_minutes,
                    },
                    "support_flag": True,
                }
            )
        atomic = assign_temporal_splits(
            pd.DataFrame(rows), config=TemporalSplitConfig()
        )
        atomic = normalize_atomic_units(atomic)

        unit_keys = atomic[["spatial_id", "absolute_time", "unit_id", "split"]].copy()
        unit_keys["spatial_id"] = unit_keys["spatial_id"].astype(str)
        client_join = client[
            ["vehicle_id", "grid_id", "slot_time", "speed_kmh", "source_trace_id"]
        ].copy()
        client_join = client_join.rename(
            columns={"grid_id": "spatial_id", "slot_time": "absolute_time"}
        )
        client_join["spatial_id"] = client_join["spatial_id"].astype(str)
        # One measurement per vehicle×unit to keep tables tractable.
        client_join = (
            client_join.sort_values("absolute_time", kind="stable")
            .groupby(["vehicle_id", "spatial_id", "absolute_time"], as_index=False)
            .agg(
                potential_measurement=("speed_kmh", "mean"),
                source_trace_id=("source_trace_id", "first"),
            )
        )
        merged = client_join.merge(
            unit_keys, on=["spatial_id", "absolute_time"], how="inner"
        )
        merged = merged.loc[~merged["source_trace_id"].astype(str).isin(target_ids)]
        if merged.empty:
            raise RuntimeError(
                "No client-fleet measurements aligned to reference grid/slots"
            )
        clients = normalize_client_measurements(
            pd.DataFrame(
                {
                    "client_id": "vehicle::" + merged["vehicle_id"].astype(str),
                    "unit_id": merged["unit_id"].astype(str),
                    "potential_measurement": merged["potential_measurement"].astype(
                        float
                    ),
                    "controlled_generator_parameters": None,
                    "split": merged["split"].astype(str),
                    "source_trace_id": merged["source_trace_id"].astype(str),
                }
            )
        )
        overlap = target_ids & set(clients["source_trace_id"].astype(str))
        if overlap:
            raise RuntimeError(
                f"T-Drive target/client source overlap ({len(overlap)}); "
                "same record cannot build both"
            )

        metadata = DatasetMetadata(
            dataset="tdrive_speed",
            target_name=str(cfg["target"]["name"]),
            target_unit=str(cfg["target"]["unit"]),
            spatial_unit=f"grid_{cell_meters}m",
            time_unit=f"{slot_minutes}_minutes",
            source_name=str(cfg["download"]["source_name"]),
            source_url=str(cfg["download"]["source_url"]),
            raw_license=str(cfg["download"]["license"]),
            filtering_rules=tuple(cfg["physical_filters"]),
            notes=(
                f"Grid {cell_meters}m and slot {slot_minutes}min frozen for validation",
                "Reference fleet constructs Y; client fleet provides measurements only",
            ),
        )
        audit = {
            "seed": int(seed),
            "segments_before_speed_filter": before,
            "segments_after_speed_filter": int(len(segments)),
            "reference_vehicles": int((fleet["fleet"] == "reference").sum()),
            "client_vehicles": int((fleet["fleet"] == "client").sum()),
            "atomic_units": int(len(atomic)),
            "client_rows": int(len(clients)),
            "cell_meters": cell_meters,
            "slot_minutes": slot_minutes,
            **parse_meta,
        }
        return ProcessedBundle(
            atomic_units=atomic,
            client_measurements=clients,
            metadata=metadata,
            target_source_trace_ids=target_ids,
            anomaly_records=anomalies,
            audit_context=audit,
            fleet_assignments=fleet,
        )


def _load_tdrive_points(
    archives: tuple[Path, ...],
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    vehicle_ids: list[str] = []
    timestamps: list[np.ndarray] = []
    lons: list[np.ndarray] = []
    lats: list[np.ndarray] = []
    members = 0
    for archive in archives:
        with zipfile.ZipFile(archive) as zf:
            for name in zf.namelist():
                if not name.lower().endswith(".txt"):
                    continue
                if "readme" in name.lower():
                    continue
                try:
                    payload = zf.read(name)
                except Exception:  # noqa: BLE001
                    continue
                parsed = _parse_trajectory_bytes(payload)
                if parsed is None:
                    continue
                vid, ts, lon, lat = parsed
                vehicle_ids.append(vid)
                timestamps.append(ts)
                lons.append(lon)
                lats.append(lat)
                members += 1
    if not vehicle_ids:
        raise RuntimeError("No T-Drive trajectory points parsed from official zips")

    n_per = [len(arr) for arr in timestamps]
    vehicle_col = np.repeat(np.asarray(vehicle_ids, dtype=object), n_per)
    ts_col = np.concatenate(timestamps)
    lon_col = np.concatenate(lons)
    lat_col = np.concatenate(lats)
    absolute_time = pd.to_datetime(ts_col, utc=True)
    source_trace_id = (
        "tdrive::"
        + pd.Series(vehicle_col, dtype="string")
        + "::"
        + absolute_time.astype("int64").astype(str)
        + "::"
        + pd.Series(np.round(lon_col, 5)).astype(str)
        + "::"
        + pd.Series(np.round(lat_col, 5)).astype(str)
    )
    points = pd.DataFrame(
        {
            "vehicle_id": vehicle_col.astype(str),
            "absolute_time": absolute_time,
            "longitude": lon_col,
            "latitude": lat_col,
            "source_trace_id": source_trace_id.astype(str),
        }
    )
    anomalies = pd.DataFrame(columns=["source_trace_id", "rule", "action", "value"])
    meta = {
        "trajectory_members_parsed": members,
        "point_rows": int(len(points)),
        "vehicle_count_raw": int(points["vehicle_id"].nunique()),
    }
    return points, anomalies, meta


def _parse_trajectory_bytes(
    payload: bytes,
) -> tuple[str, np.ndarray, np.ndarray, np.ndarray] | None:
    text = payload.decode("utf-8", errors="ignore").strip()
    if not text:
        return None
    lines = text.splitlines()
    vids: list[str] = []
    times: list[str] = []
    lons: list[float] = []
    lats: list[float] = []
    for line in lines:
        parts = line.split(",")
        if len(parts) < 4:
            continue
        try:
            lon = float(parts[2])
            lat = float(parts[3])
        except ValueError:
            continue
        if not (LON_MIN <= lon <= LON_MAX and LAT_MIN <= lat <= LAT_MAX):
            continue
        vids.append(parts[0].strip())
        times.append(parts[1].strip())
        lons.append(lon)
        lats.append(lat)
    if not times:
        return None
    vehicle_id = vids[0] or "unknown"
    ts = np.asarray(pd.to_datetime(times, utc=True, errors="coerce").to_numpy())
    lon_arr = np.asarray(lons, dtype="float64")
    lat_arr = np.asarray(lats, dtype="float64")
    valid = ~pd.isna(ts)
    if not valid.any():
        return None
    return vehicle_id, ts[valid], lon_arr[valid], lat_arr[valid]


def _haversine_km(lon1, lat1, lon2, lat2) -> np.ndarray:
    radius = 6371.0
    lon1_r = np.radians(lon1)
    lat1_r = np.radians(lat1)
    lon2_r = np.radians(lon2)
    lat2_r = np.radians(lat2)
    dlon = lon2_r - lon1_r
    dlat = lat2_r - lat1_r
    a = (
        np.sin(dlat / 2.0) ** 2
        + np.cos(lat1_r) * np.cos(lat2_r) * np.sin(dlon / 2.0) ** 2
    )
    return 2.0 * radius * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def _segments_with_speed(points: pd.DataFrame) -> pd.DataFrame:
    ordered = points.sort_values(
        ["vehicle_id", "absolute_time"], kind="stable"
    ).reset_index(drop=True)
    next_rows = ordered.groupby("vehicle_id", sort=False).shift(-1)
    dt_seconds = (
        next_rows["absolute_time"] - ordered["absolute_time"]
    ).dt.total_seconds()
    dt_hours = dt_seconds / 3600.0
    distance = _haversine_km(
        ordered["longitude"].to_numpy(),
        ordered["latitude"].to_numpy(),
        next_rows["longitude"].to_numpy(),
        next_rows["latitude"].to_numpy(),
    )
    with np.errstate(divide="ignore", invalid="ignore"):
        speed = np.divide(distance, dt_hours.to_numpy())
    valid = (
        next_rows["absolute_time"].notna()
        & np.isfinite(speed)
        & (dt_hours > 0)
        & (dt_hours <= 0.25)
    )
    out = ordered.loc[valid].copy()
    out["speed_kmh"] = speed[valid.to_numpy()]
    return out


def _grid_ids(
    longitude: pd.Series, latitude: pd.Series, *, cell_meters: int
) -> pd.Series:
    cell_km = cell_meters / 1000.0
    lat_deg = cell_km / EARTH_KM_PER_DEG_LAT
    mid_lat = 0.5 * (LAT_MIN + LAT_MAX)
    lon_deg = cell_km / (
        EARTH_KM_PER_DEG_LAT * max(0.2, math.cos(math.radians(mid_lat)))
    )
    x = np.floor((longitude.to_numpy() - LON_MIN) / lon_deg).astype(int)
    y = np.floor((latitude.to_numpy() - LAT_MIN) / lat_deg).astype(int)
    return pd.Series(
        [f"g{xx:04d}_{yy:04d}" for xx, yy in zip(x, y)], index=longitude.index
    )

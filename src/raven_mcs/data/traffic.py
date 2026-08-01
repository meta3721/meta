"""NSW / TfNSW traffic volume adapter with continuity hard floor."""

from __future__ import annotations

import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from raven_mcs.data.base import DatasetAdapter, DatasetMetadata, ProcessedBundle
from raven_mcs.data.matrix_adapter import prepare_controlled_from_matrix
from raven_mcs.utils.config import repo_root_from_here
from raven_mcs.utils.serialization import load_yaml


class TrafficQualityError(RuntimeError):
    """Raised when Traffic fails the continuity hard floor."""


class TrafficAdapter(DatasetAdapter):
    @property
    def name(self) -> str:
        return "traffic"

    def discover_raw_files(self, raw_root: Path) -> tuple[Path, ...]:
        root = Path(raw_root)
        station = root / "road_traffic_counts_station_reference.csv"
        hourly = root / "road_traffic_counts_hourly_permanent.zip"
        missing = [str(path) for path in (station, hourly) if not path.exists()]
        if missing:
            raise FileNotFoundError(
                "Missing official Traffic artifacts: "
                + ", ".join(missing)
                + "; do not substitute PEMS-BAY"
            )
        return station, hourly

    def prepare(self, raw_root: Path, *, seed: int) -> ProcessedBundle:
        station_path, hourly_zip = self.discover_raw_files(raw_root)
        cfg = load_yaml(repo_root_from_here() / "configs" / "dataset" / "traffic.yaml")
        hard_stations = int(cfg["matrix"]["hard_floor_stations"])
        hard_hours = int(cfg["matrix"]["hard_floor_hours"])
        preferred_stations = int(cfg["matrix"]["preferred_stations"])
        preferred_hours = int(cfg["matrix"]["preferred_hours"])

        matrix, quality, anomalies, parse_meta = _load_traffic_matrix(
            station_path, hourly_zip
        )
        quality_path = Path(raw_root) / "station_quality_report.csv"
        quality.to_csv(quality_path, index=False)

        eligible = quality.loc[
            (quality["max_continuous_hours"] >= hard_hours)
            & (quality["non_negative_fraction"] >= 0.99)
        ]
        if len(eligible) < hard_stations:
            raise TrafficQualityError(
                f"Traffic hard floor unmet: only {len(eligible)} stations have "
                f">={hard_hours} continuous hours (need >={hard_stations}). "
                "Stop and report; do not substitute PEMS-BAY."
            )

        ranked = eligible.sort_values(
            ["max_continuous_hours", "coverage", "station_id"],
            ascending=[False, False, True],
            kind="stable",
        )
        candidate_stations = list(
            ranked["station_id"].astype(str).head(max(preferred_stations, hard_stations))
        )
        window_hours = min(
            preferred_hours,
            int(ranked["max_continuous_hours"].max()),
        )
        window_hours = max(window_hours, hard_hours)

        subset = matrix.loc[
            matrix["spatial_id"].astype(str).isin(candidate_stations)
        ].copy()
        pivot = subset.pivot_table(
            index="absolute_time",
            columns="spatial_id",
            values="target_value",
            aggfunc="mean",
        ).sort_index()
        best_start = 0
        best_score = (-1, -1.0)
        chosen_stations: list[str] = []
        for start in range(0, max(0, len(pivot) - window_hours) + 1):
            block = pivot.iloc[start : start + window_hours]
            complete = [str(col) for col in block.columns[block.notna().all(axis=0)]]
            if len(complete) < hard_stations:
                continue
            use = complete[: min(len(complete), preferred_stations)]
            coverage = float(block[use].notna().to_numpy().mean())
            score = (len(use), coverage)
            if score > best_score:
                best_score = score
                best_start = start
                chosen_stations = use
        if best_score[0] < hard_stations:
            raise TrafficQualityError(
                "Traffic hard floor unmet after window search: "
                f"best continuous block had {best_score[0]} stations "
                f"(need >={hard_stations} × {hard_hours})."
            )

        selected_pivot = pivot.iloc[best_start : best_start + window_hours][
            chosen_stations
        ]
        selected = selected_pivot.stack().rename("target_value").reset_index()
        selected.columns = ["absolute_time", "spatial_id", "target_value"]
        selected["spatial_id"] = selected["spatial_id"].astype(str)
        selected = selected.dropna(subset=["target_value"]).reset_index(drop=True)

        if (
            selected["spatial_id"].nunique() < hard_stations
            or selected["absolute_time"].nunique() < hard_hours
        ):
            raise TrafficQualityError(
                "Traffic hard floor unmet in final matrix: "
                f"{selected['spatial_id'].nunique()}×{selected['absolute_time'].nunique()}"
            )

        atomic, clients, target_ids, audit, anomalies = prepare_controlled_from_matrix(
            selected,
            seed=seed,
            target_spatial=len(chosen_stations),
            target_times=int(selected["absolute_time"].nunique()),
            anomaly_records=anomalies,
            audit_extra={
                **parse_meta,
                "quality_report": str(quality_path),
                "eligible_stations": int(len(eligible)),
                "selected_stations": len(chosen_stations),
                "selected_hours": int(selected["absolute_time"].nunique()),
                "hard_floor_stations": hard_stations,
                "hard_floor_hours": hard_hours,
                "preferred_met": bool(
                    len(chosen_stations) >= preferred_stations
                    and selected["absolute_time"].nunique() >= preferred_hours
                ),
            },
            min_coverage=0.95,
        )
        metadata = DatasetMetadata(
            dataset="traffic",
            target_name=str(cfg["target"]["name"]),
            target_unit=str(cfg["target"]["unit"]),
            spatial_unit="traffic_station",
            time_unit=str(cfg["matrix"]["time_unit"]),
            source_name=str(cfg["download"]["source_name"]),
            source_url=str(cfg["download"]["source_url"]),
            raw_license=str(cfg["download"]["license"]),
            filtering_rules=tuple(cfg["physical_filters"]),
            notes=(
                "station_quality_report.csv is required before acceptance",
                "Hard floor: >=30 stations × 336 continuous hours",
            ),
        )
        return ProcessedBundle(
            atomic_units=atomic,
            client_measurements=clients,
            metadata=metadata,
            target_source_trace_ids=target_ids,
            anomaly_records=anomalies,
            audit_context=audit,
        )


def _load_traffic_matrix(
    station_path: Path,
    hourly_zip: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, object]]:
    stations = pd.read_csv(station_path)
    station_id_col = _first_existing(
        stations.columns,
        ("station_key", "station_id", "stationid", "traffic_station", "site_id"),
    )
    if station_id_col is None:
        raise RuntimeError(
            f"Could not identify station id column in {station_path.name}: "
            f"{list(stations.columns)}"
        )
    station_ids = set(stations[station_id_col].astype(str))

    # Aggregate per chunk so the melted hour columns do not all stay in RAM.
    partials: list[pd.DataFrame] = []
    raw_rows = 0
    dropped_non_finite = 0
    dropped_negative = 0

    with zipfile.ZipFile(hourly_zip) as zf:
        csv_names = [name for name in zf.namelist() if name.lower().endswith(".csv")]
        if not csv_names:
            raise RuntimeError("Traffic hourly zip contains no CSV members")
        for name in csv_names:
            with zf.open(name) as handle:
                for chunk in pd.read_csv(
                    handle, chunksize=50_000, low_memory=False
                ):
                    parsed = _normalize_hourly_chunk(chunk)
                    if parsed is None or parsed.empty:
                        continue
                    raw_rows += len(parsed)
                    values = pd.to_numeric(parsed["target_value"], errors="coerce")
                    times = pd.to_datetime(
                        parsed["absolute_time"], utc=True, errors="coerce"
                    )
                    spatial = parsed["spatial_id"].astype(str)
                    keep_ref = (
                        spatial.isin(station_ids)
                        if station_ids
                        else pd.Series(True, index=parsed.index)
                    )
                    finite = np.isfinite(values.to_numpy(dtype="float64"))
                    nonneg = values >= 0
                    dropped_non_finite += int((keep_ref & ~finite).sum())
                    dropped_negative += int((keep_ref & finite & ~nonneg).sum())
                    keep = keep_ref & finite & nonneg & times.notna()
                    if not keep.any():
                        continue
                    part = pd.DataFrame(
                        {
                            "spatial_id": spatial.loc[keep].to_numpy(),
                            "absolute_time": times.loc[keep].dt.floor("h").to_numpy(),
                            "target_value": values.loc[keep].to_numpy(dtype="float64"),
                        }
                    )
                    partials.append(
                        part.groupby(["spatial_id", "absolute_time"], as_index=False)[
                            "target_value"
                        ].mean()
                    )

    if not partials:
        raise RuntimeError("No hourly traffic volume rows could be parsed")

    matrix = (
        pd.concat(partials, ignore_index=True)
        .groupby(["spatial_id", "absolute_time"], as_index=False)["target_value"]
        .mean()
        .sort_values(["absolute_time", "spatial_id"], kind="stable")
    )

    anomalies = pd.DataFrame(
        [
            {
                "source_trace_id": "traffic::aggregate",
                "rule": "non_finite_volume",
                "action": "drop",
                "value": str(dropped_non_finite),
            },
            {
                "source_trace_id": "traffic::aggregate",
                "rule": "negative_volume",
                "action": "drop",
                "value": str(dropped_negative),
            },
        ]
    )
    quality = _station_quality_report(matrix)
    meta = {
        "station_reference_rows": int(len(stations)),
        "raw_rows_before_filter": raw_rows,
        "hourly_rows": int(len(matrix)),
        "station_count_raw": int(matrix["spatial_id"].nunique()),
        "hour_count_raw": int(matrix["absolute_time"].nunique()),
    }
    return matrix, quality, anomalies, meta


def _max_continuous_hours(times: pd.Series | pd.Index) -> int:
    """Longest run of consecutive hourly timestamps (pandas-unit safe)."""
    ordered = pd.DatetimeIndex(pd.to_datetime(times, utc=True)).drop_duplicates().sort_values()
    if len(ordered) == 0:
        return 0
    if len(ordered) == 1:
        return 1
    # Compare with Timedelta to avoid asi8 unit assumptions (ns vs us in pandas 3).
    deltas = ordered.to_series().diff().iloc[1:]
    consecutive = (deltas == pd.Timedelta(hours=1)).to_numpy()
    best = 1
    run = 1
    for flag in consecutive:
        if flag:
            run += 1
            best = max(best, run)
        else:
            run = 1
    return int(best)


def _station_quality_report(matrix: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for station_id, group in matrix.groupby("spatial_id"):
        times = group["absolute_time"]
        if times.empty:
            continue
        best = _max_continuous_hours(times)
        values = group["target_value"]
        records.append(
            {
                "station_id": str(station_id),
                "n_hours": int(pd.to_datetime(times, utc=True).nunique()),
                "max_continuous_hours": int(best),
                "coverage": float(values.notna().mean()),
                "non_negative_fraction": float((values >= 0).mean()),
                "mean_volume": float(values.mean()),
            }
        )
    return pd.DataFrame(records).sort_values(
        ["max_continuous_hours", "station_id"], ascending=[False, True]
    )


def _normalize_hourly_chunk(chunk: pd.DataFrame) -> pd.DataFrame | None:
    cols = {str(c).strip().lower(): c for c in chunk.columns}
    station_col = _first_existing(
        cols,
        ("station_key", "station_id", "stationid", "traffic_station", "site_id"),
    )
    if station_col is None:
        return None

    hour_cols = []
    for hour in range(24):
        key = f"hour_{hour:02d}"
        if key in cols:
            hour_cols.append((hour, cols[key]))
    if hour_cols:
        date_col = _first_existing(
            cols, ("date", "datetime", "timestamp", "date_time")
        )
        if date_col is None:
            return None
        base = pd.to_datetime(chunk[cols[date_col]], utc=True, errors="coerce")
        pieces: list[pd.DataFrame] = []
        for hour, hour_name in hour_cols:
            pieces.append(
                pd.DataFrame(
                    {
                        "spatial_id": chunk[cols[station_col]].astype(str),
                        "absolute_time": base + pd.to_timedelta(hour, unit="h"),
                        "target_value": pd.to_numeric(chunk[hour_name], errors="coerce"),
                    }
                )
            )
        out = pd.concat(pieces, ignore_index=True)
        return out

    volume_col = _first_existing(
        cols,
        (
            "traffic_count",
            "traffic_volume",
            "volume",
            "hourly_counts",
            "count",
            "vehicle_count",
        ),
    )
    if volume_col is None:
        return None
    time_col = _first_existing(
        cols, ("date", "datetime", "timestamp", "date_time", "end_time", "start_time")
    )
    if time_col is None:
        return None
    return pd.DataFrame(
        {
            "spatial_id": chunk[cols[station_col]].astype(str),
            "absolute_time": pd.to_datetime(
                chunk[cols[time_col]], utc=True, errors="coerce"
            ),
            "target_value": pd.to_numeric(chunk[cols[volume_col]], errors="coerce"),
        }
    )


def _first_existing(columns, candidates: tuple[str, ...]) -> str | None:
    if isinstance(columns, dict):
        for key in candidates:
            if key in columns:
                return key
        return None
    lowered = {str(col).strip().lower(): str(col) for col in columns}
    for key in candidates:
        if key in lowered:
            return lowered[key]
    return None

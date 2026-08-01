"""Microsoft Research Urban Air (U-Air) PM2.5 adapter."""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from raven_mcs.data.base import DatasetAdapter, DatasetMetadata, ProcessedBundle
from raven_mcs.data.matrix_adapter import prepare_controlled_from_matrix
from raven_mcs.utils.config import repo_root_from_here
from raven_mcs.utils.serialization import load_yaml

PM25_ALIASES = (
    "pm25_concentration",
    "pm2_5_concentration",
    "pm2_5",
    "pm25",
    "pm2.5",
    "pm_2_5",
    "fine_particles",
)
STATION_ALIASES = ("station_id", "station", "site_id", "monitor_id", "aqi_station")
TIME_ALIASES = ("timestamp", "time", "datetime", "date_time", "utc_time", "local_time")


class UAirAdapter(DatasetAdapter):
    @property
    def name(self) -> str:
        return "uair"

    def discover_raw_files(self, raw_root: Path) -> tuple[Path, ...]:
        root = Path(raw_root)
        zips = sorted(root.glob("*.zip"))
        if not zips:
            raise FileNotFoundError(
                f"No official U-Air zip found under {root}; "
                "do not substitute UCI Beijing or other proxies"
            )
        return tuple(zips)

    def prepare(self, raw_root: Path, *, seed: int) -> ProcessedBundle:
        archives = self.discover_raw_files(raw_root)
        cfg = load_yaml(repo_root_from_here() / "configs" / "dataset" / "uair.yaml")
        matrix, anomalies, parse_meta = _load_uair_matrix(archives)
        if matrix.empty:
            raise RuntimeError(
                "Official U-Air archive downloaded but no PM2.5 matrix could be parsed"
            )
        atomic, clients, target_ids, audit, anomalies = prepare_controlled_from_matrix(
            matrix,
            seed=seed,
            target_spatial=int(cfg["matrix"]["spatial_count"]),
            target_times=int(cfg["matrix"]["time_count"]),
            anomaly_records=anomalies,
            audit_extra=parse_meta,
            min_coverage=0.55,
        )
        metadata = DatasetMetadata(
            dataset="uair",
            target_name=str(cfg["target"]["name"]),
            target_unit=str(cfg["target"]["unit"]),
            spatial_unit="air_quality_station",
            time_unit=str(cfg["matrix"]["time_unit"]),
            source_name=str(cfg["download"]["source_name"]),
            source_url=str(cfg["download"]["source_url"]),
            raw_license=str(cfg["download"]["license"]),
            filtering_rules=tuple(cfg["physical_filters"]),
            notes=(
                "Only official MSR Urban Air artifacts are admissible",
                "Dense-window selection targets design starting point ~36×264",
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


def _normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")


def _find_column(columns: list[str], aliases: tuple[str, ...]) -> str | None:
    normalized = {_normalize(col): col for col in columns}
    for alias in aliases:
        key = _normalize(alias)
        if key in normalized:
            return normalized[key]
    for key, original in normalized.items():
        if any(_normalize(alias) in key for alias in aliases):
            return original
    return None


def _load_uair_matrix(
    archives: tuple[Path, ...],
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    frames: list[pd.DataFrame] = []
    anomalies: list[dict[str, object]] = []
    members_used: list[str] = []

    for archive in archives:
        with zipfile.ZipFile(archive) as zf:
            for name in zf.namelist():
                lower = name.lower()
                if not lower.endswith((".csv", ".txt", ".tsv")):
                    continue
                if "forecast" in lower and "airquality" not in lower:
                    continue
                # Prefer air-quality / PM tables.
                interesting = any(
                    token in lower
                    for token in ("airquality", "air_quality", "aqi", "pm25", "pm2")
                )
                try:
                    payload = zf.read(name)
                except Exception:  # noqa: BLE001
                    continue
                parsed = _parse_air_table(payload, member_name=name)
                if parsed is None or parsed.empty:
                    continue
                if not interesting and "pm25" not in "".join(
                    str(c).lower() for c in parsed.columns
                ):
                    # Keep only if we already found a PM column inside.
                    if _find_column([str(c) for c in parsed.columns], PM25_ALIASES) is None:
                        continue
                frames.append(parsed)
                members_used.append(f"{archive.name}::{name}")
                if len(frames) >= 40:
                    break

    if not frames:
        raise RuntimeError(
            "Could not locate PM2.5 tables inside official U-Air zip(s)"
        )

    raw = pd.concat(frames, ignore_index=True)
    raw["target_value"] = pd.to_numeric(raw["target_value"], errors="coerce")
    before = len(raw)
    invalid = ~np.isfinite(raw["target_value"].to_numpy(dtype="float64"))
    low = raw["target_value"] < 0
    high = raw["target_value"] > 1000
    drop = invalid | low | high
    for rule, mask in (
        ("non_finite_pm25", invalid),
        ("pm25_below_0", low),
        ("pm25_above_1000", high),
    ):
        count = int(mask.sum())
        if count:
            anomalies.append(
                {
                    "source_trace_id": "uair::aggregate",
                    "rule": rule,
                    "action": "drop",
                    "value": str(count),
                }
            )
    cleaned = raw.loc[~drop].copy()
    cleaned["absolute_time"] = cleaned["absolute_time"].dt.floor("h")
    matrix = (
        cleaned.groupby(["spatial_id", "absolute_time"], as_index=False)["target_value"]
        .mean()
        .sort_values(["absolute_time", "spatial_id"], kind="stable")
    )
    meta = {
        "members_used": members_used,
        "raw_rows_before_filter": before,
        "raw_rows_after_filter": int(len(cleaned)),
        "hourly_rows": int(len(matrix)),
        "station_count_raw": int(matrix["spatial_id"].nunique()),
        "hour_count_raw": int(matrix["absolute_time"].nunique()),
    }
    return matrix, pd.DataFrame(anomalies), meta


def _parse_air_table(payload: bytes, *, member_name: str) -> pd.DataFrame | None:
    text = payload.decode("utf-8", errors="ignore")
    if len(text) < 50:
        return None
    buffer = io.StringIO(text)
    frame: pd.DataFrame | None = None
    for sep in (",", "\t", ";", r"\s+"):
        buffer.seek(0)
        try:
            candidate = pd.read_csv(buffer, sep=sep, engine="python")
        except Exception:  # noqa: BLE001
            continue
        if candidate.shape[1] < 2:
            continue
        frame = candidate
        break
    if frame is None:
        return None

    columns = [str(c) for c in frame.columns]
    pm_col = _find_column(columns, PM25_ALIASES)
    if pm_col is None:
        return None
    time_col = _find_column(columns, TIME_ALIASES)
    station_col = _find_column(columns, STATION_ALIASES)

    times = (
        pd.to_datetime(frame[time_col], utc=True, errors="coerce")
        if time_col is not None
        else pd.Series(pd.NaT, index=frame.index)
    )
    if times.notna().mean() < 0.5:
        return None

    if station_col is not None:
        stations = frame[station_col].astype(str)
    else:
        # Wide format: stations as columns besides time/pm labels.
        value_cols = [
            c
            for c in columns
            if c != time_col and pd.api.types.is_numeric_dtype(frame[c])
        ]
        if len(value_cols) >= 2 and pm_col in value_cols:
            # Treat as already-selected PM column with implicit station from filename.
            stations = pd.Series(
                Path(member_name).stem.replace(" ", "_"), index=frame.index
            )
        else:
            stations = pd.Series(
                Path(member_name).stem.replace(" ", "_"), index=frame.index
            )

    out = pd.DataFrame(
        {
            "spatial_id": stations.map(lambda value: re.sub(r"[^A-Za-z0-9_-]+", "_", str(value))[:64]),
            "absolute_time": times,
            "target_value": pd.to_numeric(frame[pm_col], errors="coerce"),
        }
    ).dropna()
    return out if not out.empty else None

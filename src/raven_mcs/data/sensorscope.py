"""SensorScope / Zenodo controlled ambient-temperature adapter."""

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


class SensorScopeAdapter(DatasetAdapter):
    @property
    def name(self) -> str:
        return "sensorscope"

    def discover_raw_files(self, raw_root: Path) -> tuple[Path, ...]:
        archive = Path(raw_root) / "Sensorscope.zip"
        if not archive.exists():
            raise FileNotFoundError(f"Missing SensorScope archive: {archive}")
        return (archive,)

    def prepare(self, raw_root: Path, *, seed: int) -> ProcessedBundle:
        archive = self.discover_raw_files(raw_root)[0]
        cfg = load_yaml(repo_root_from_here() / "configs" / "dataset" / "sensorscope.yaml")
        matrix, anomalies, parse_meta = _load_sensorscope_matrix(archive)
        atomic, clients, target_ids, audit, anomalies = prepare_controlled_from_matrix(
            matrix,
            seed=seed,
            target_spatial=int(cfg["matrix"]["spatial_count"]),
            target_times=int(cfg["matrix"]["time_count"]),
            anomaly_records=anomalies,
            audit_extra=parse_meta,
            min_coverage=0.60,
        )
        metadata = DatasetMetadata(
            dataset="sensorscope",
            target_name=str(cfg["target"]["name"]),
            target_unit=str(cfg["target"]["unit"]),
            spatial_unit="sensorscope_station",
            time_unit=str(cfg["matrix"]["time_unit"]),
            source_name=str(cfg["download"]["source_name"]),
            source_url=str(cfg["download"]["source_url"]),
            raw_license=str(cfg["download"]["license"]),
            filtering_rules=tuple(cfg["physical_filters"]),
            notes=(
                "Dense-window selection targets design starting point ~55×312",
                "Nested deployment zips and column-definition files are audited",
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


def _ambient_column_index(def_text: str) -> int | None:
    """Return 0-based ambient-temperature column index from a def file."""
    for line in def_text.splitlines():
        match = re.match(
            r"\s*(\d+)\.\s*(.+)$",
            line.strip(),
            flags=re.IGNORECASE,
        )
        if not match:
            continue
        label = match.group(2).lower()
        if "ambient temperature" in label or (
            "temperature" in label and "surface" not in label and "soil" not in label
        ):
            return int(match.group(1)) - 1
    return None


def _epoch_column_index(def_text: str) -> int:
    for line in def_text.splitlines():
        match = re.match(r"\s*(\d+)\.\s*(.+)$", line.strip(), flags=re.IGNORECASE)
        if match and "epoch" in match.group(2).lower():
            return int(match.group(1)) - 1
    return 7  # SensorScope convention


def _load_sensorscope_matrix(
    archive: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    anomalies: list[dict[str, object]] = []
    frames: list[pd.DataFrame] = []
    nested_used: list[str] = []
    defs_recorded: list[str] = []

    with zipfile.ZipFile(archive) as outer:
        all_nested = [
            name
            for name in outer.namelist()
            if name.lower().endswith(".zip")
            and (
                "meteo" in name.lower()
                or "luce_stations" in name.lower()
            )
            and "monitor" not in name.lower()
            and "vidicam" not in name.lower()
        ]
        # Prefer EPFL Luce station packs (design starting point ~55 stations).
        luce = [name for name in all_nested if "luce_stations" in name.lower()]
        nested_names = sorted(luce) if luce else sorted(all_nested)
        if not nested_names:
            raise RuntimeError("No SensorScope meteo nested archives found")

        for nested_name in nested_names:
            try:
                nested_bytes = outer.read(nested_name)
            except Exception:  # noqa: BLE001
                continue
            with zipfile.ZipFile(io.BytesIO(nested_bytes)) as nested:
                def_members = [
                    name
                    for name in nested.namelist()
                    if name.lower().endswith("def.txt")
                ]
                ambient_idx = 8
                epoch_idx = 7
                for def_name in def_members:
                    text = nested.read(def_name).decode("utf-8", errors="ignore")
                    defs_recorded.append(f"{nested_name}::{def_name}")
                    anomalies.append(
                        {
                            "source_trace_id": f"columns::{nested_name}::{Path(def_name).name}",
                            "rule": "column_definition",
                            "action": "record",
                            "value": text.replace("\n", " | ")[:500],
                        }
                    )
                    found = _ambient_column_index(text)
                    if found is not None:
                        ambient_idx = found
                    epoch_idx = _epoch_column_index(text)

                data_members = [
                    name
                    for name in nested.namelist()
                    if name.lower().endswith(".txt")
                    and "def" not in name.lower()
                    and not name.endswith("/")
                ]
                for member in data_members:
                    try:
                        payload = nested.read(member)
                    except Exception:  # noqa: BLE001
                        continue
                    frame = _parse_meteo_table(
                        payload,
                        station_hint=Path(member).stem,
                        ambient_idx=ambient_idx,
                        epoch_idx=epoch_idx,
                    )
                    if frame is None or frame.empty:
                        continue
                    # Aggregate to hourly early to keep memory bounded.
                    frame["absolute_time"] = frame["absolute_time"].dt.floor("h")
                    frames.append(
                        frame.groupby(
                            ["spatial_id", "absolute_time"], as_index=False
                        )["target_value"].mean()
                    )
                nested_used.append(nested_name)

    if not frames:
        raise RuntimeError(
            "SensorScope archive contained no parseable ambient-temperature tables"
        )

    raw = pd.concat(frames, ignore_index=True)
    raw["target_value"] = pd.to_numeric(raw["target_value"], errors="coerce")
    before = len(raw)
    invalid = ~np.isfinite(raw["target_value"].to_numpy(dtype="float64"))
    cold = raw["target_value"] < -40
    hot = raw["target_value"] > 60
    drop_mask = invalid | cold | hot
    for rule, mask in (
        ("non_finite_temperature", invalid),
        ("temperature_below_-40C", cold),
        ("temperature_above_60C", hot),
    ):
        count = int(mask.sum())
        if count:
            anomalies.append(
                {
                    "source_trace_id": "sensorscope::aggregate",
                    "rule": rule,
                    "action": "drop",
                    "value": str(count),
                }
            )
    cleaned = raw.loc[~drop_mask].copy()
    cleaned["absolute_time"] = cleaned["absolute_time"].dt.floor("h")
    matrix = (
        cleaned.groupby(["spatial_id", "absolute_time"], as_index=False)["target_value"]
        .mean()
        .sort_values(["absolute_time", "spatial_id"], kind="stable")
    )
    meta = {
        "nested_archives_used": nested_used,
        "column_definition_files": defs_recorded,
        "raw_rows_before_filter": before,
        "raw_rows_after_filter": int(len(cleaned)),
        "hourly_rows": int(len(matrix)),
        "station_count_raw": int(matrix["spatial_id"].nunique()),
        "hour_count_raw": int(matrix["absolute_time"].nunique()),
    }
    return matrix, pd.DataFrame(anomalies), meta


def _parse_meteo_table(
    payload: bytes,
    *,
    station_hint: str,
    ambient_idx: int,
    epoch_idx: int,
) -> pd.DataFrame | None:
    text = payload.decode("utf-8", errors="ignore")
    if len(text) < 50:
        return None
    try:
        frame = pd.read_csv(
            io.StringIO(text),
            sep=r"\s+",
            header=None,
            engine="python",
            na_values=["NaN", "nan", "NA", ""],
        )
    except Exception:  # noqa: BLE001
        return None
    if frame.shape[1] <= max(ambient_idx, epoch_idx):
        return None
    epochs = pd.to_numeric(frame.iloc[:, epoch_idx], errors="coerce")
    temps = pd.to_numeric(frame.iloc[:, ambient_idx], errors="coerce")
    station_ids = frame.iloc[:, 0].astype(str)
    times = pd.to_datetime(epochs, unit="s", utc=True, errors="coerce")
    out = pd.DataFrame(
        {
            "spatial_id": "s"
            + station_ids.map(lambda value: re.sub(r"[^0-9A-Za-z]+", "", value)[:16]),
            "absolute_time": times,
            "target_value": temps,
        }
    ).dropna()
    if out.empty:
        # Fall back to filename-derived station id.
        fallback = re.sub(r"[^0-9]+", "", station_hint)
        if not fallback:
            return None
        out = pd.DataFrame(
            {
                "spatial_id": f"s{fallback}",
                "absolute_time": times,
                "target_value": temps,
            }
        ).dropna()
    return out if not out.empty else None

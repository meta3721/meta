"""Canonical processed-data schemas for RAVEN-MCS (Phase 2)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

SCHEMA_VERSION = "2.3.0"
VALID_SPLITS = frozenset({"train", "validation", "test"})

ATOMIC_REQUIRED_COLUMNS = (
    "unit_id",
    "spatial_id",
    "absolute_time",
    "time_index",
    "target_value",
    "split",
    "target_group",
    "opportunity_stratum",
    "public_features",
    "support_flag",
)
ATOMIC_OPTIONAL_COLUMNS = ("is_warmup",)

CLIENT_REQUIRED_COLUMNS = (
    "client_id",
    "unit_id",
    "potential_measurement",
    "controlled_generator_parameters",
    "split",
    "source_trace_id",
)


class ProcessedSchemaError(ValueError):
    """Raised when processed data violates the frozen schema."""


def _is_missing_scalar(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (dict, list, tuple, set)):
        return False
    missing = pd.isna(value)
    return isinstance(missing, (bool, np.bool_)) and bool(missing)


def atomic_units_arrow_schema(*, include_warmup: bool = True) -> pa.Schema:
    fields = [
        pa.field("unit_id", pa.string(), nullable=False),
        pa.field("spatial_id", pa.string(), nullable=False),
        pa.field("absolute_time", pa.timestamp("ns", tz="UTC"), nullable=False),
        pa.field("time_index", pa.int64(), nullable=False),
        pa.field("target_value", pa.float64(), nullable=False),
        pa.field("split", pa.string(), nullable=False),
        pa.field("target_group", pa.string(), nullable=False),
        pa.field("opportunity_stratum", pa.string(), nullable=False),
        pa.field("public_features", pa.large_string(), nullable=False),
        pa.field("support_flag", pa.bool_(), nullable=False),
    ]
    if include_warmup:
        fields.append(pa.field("is_warmup", pa.bool_(), nullable=False))
    return pa.schema(fields, metadata={b"schema_version": SCHEMA_VERSION.encode()})


def client_measurements_arrow_schema() -> pa.Schema:
    return pa.schema(
        [
            pa.field("client_id", pa.string(), nullable=False),
            pa.field("unit_id", pa.string(), nullable=False),
            pa.field("potential_measurement", pa.float64(), nullable=True),
            pa.field(
                "controlled_generator_parameters", pa.large_string(), nullable=True
            ),
            pa.field("split", pa.string(), nullable=False),
            pa.field("source_trace_id", pa.string(), nullable=False),
        ],
        metadata={b"schema_version": SCHEMA_VERSION.encode()},
    )


def _canonical_json_cell(value: Any) -> str:
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ProcessedSchemaError(f"Invalid JSON feature value: {value}") from exc
        return json.dumps(
            decoded, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
    if _is_missing_scalar(value):
        return "{}"
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _strict_bool(series: pd.Series, label: str) -> pd.Series:
    valid = series.map(lambda value: isinstance(value, (bool, np.bool_)))
    if not valid.all():
        raise ProcessedSchemaError(f"{label} must contain only boolean values")
    return series.astype("bool")


def _require_columns(frame: pd.DataFrame, columns: tuple[str, ...], label: str) -> None:
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise ProcessedSchemaError(f"{label} missing columns: {missing}")


def _validate_splits(series: pd.Series, label: str) -> None:
    observed = set(series.dropna().astype(str).unique())
    invalid = sorted(observed - VALID_SPLITS)
    if invalid:
        raise ProcessedSchemaError(f"{label} contains invalid splits: {invalid}")


def normalize_atomic_units(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize and validate an atomic-units table without mutating input."""
    _require_columns(frame, ATOMIC_REQUIRED_COLUMNS, "atomic_units")
    result = frame.copy()
    result["unit_id"] = result["unit_id"].astype("string")
    result["spatial_id"] = result["spatial_id"].astype("string")
    result["absolute_time"] = pd.to_datetime(
        result["absolute_time"], utc=True, errors="raise"
    )
    result["time_index"] = pd.to_numeric(
        result["time_index"], errors="raise"
    ).astype("int64")
    result["target_value"] = pd.to_numeric(
        result["target_value"], errors="raise"
    ).astype("float64")
    result["split"] = result["split"].astype("string")
    result["target_group"] = result["target_group"].astype("string")
    result["opportunity_stratum"] = result["opportunity_stratum"].astype("string")
    result["public_features"] = result["public_features"].map(_canonical_json_cell)
    result["support_flag"] = _strict_bool(
        result["support_flag"], "atomic_units.support_flag"
    )
    if "is_warmup" not in result:
        result["is_warmup"] = False
    result["is_warmup"] = _strict_bool(
        result["is_warmup"], "atomic_units.is_warmup"
    )

    nonnullable = list(ATOMIC_REQUIRED_COLUMNS)
    if result[nonnullable].isna().any().any():
        raise ProcessedSchemaError("atomic_units contains null in required columns")
    for column in (
        "unit_id",
        "spatial_id",
        "split",
        "target_group",
        "opportunity_stratum",
    ):
        if result[column].str.strip().eq("").any():
            raise ProcessedSchemaError(f"atomic_units.{column} contains empty values")
    if result["unit_id"].duplicated().any():
        raise ProcessedSchemaError("atomic_units.unit_id must be unique")
    if not np.isfinite(result["target_value"].to_numpy(dtype=np.float64)).all():
        raise ProcessedSchemaError("atomic_units.target_value contains non-finite values")
    _validate_splits(result["split"], "atomic_units")
    if (result["is_warmup"] & (result["split"] != "train")).any():
        raise ProcessedSchemaError("is_warmup may only be true for train rows")
    return result[list(ATOMIC_REQUIRED_COLUMNS) + list(ATOMIC_OPTIONAL_COLUMNS)]


def normalize_client_measurements(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize and validate a client-measurements table."""
    _require_columns(frame, CLIENT_REQUIRED_COLUMNS, "client_measurements")
    result = frame.copy()
    for column in ("client_id", "unit_id", "split", "source_trace_id"):
        result[column] = result[column].astype("string")
    result["potential_measurement"] = pd.to_numeric(
        result["potential_measurement"], errors="raise"
    ).astype("float64")
    result["controlled_generator_parameters"] = result[
        "controlled_generator_parameters"
    ].map(
        lambda value: None
        if _is_missing_scalar(value)
        else _canonical_json_cell(value)
    )

    for column in ("client_id", "unit_id", "split", "source_trace_id"):
        if result[column].isna().any():
            raise ProcessedSchemaError(
                f"client_measurements.{column} contains null values"
            )
        if result[column].str.strip().eq("").any():
            raise ProcessedSchemaError(
                f"client_measurements.{column} contains empty values"
            )
    has_measurement = result["potential_measurement"].notna()
    has_parameters = result["controlled_generator_parameters"].notna()
    if not (has_measurement | has_parameters).all():
        raise ProcessedSchemaError(
            "Each client row needs potential_measurement or "
            "controlled_generator_parameters"
        )
    finite_measurements = result.loc[
        has_measurement, "potential_measurement"
    ].to_numpy(dtype=np.float64)
    if not np.isfinite(finite_measurements).all():
        raise ProcessedSchemaError(
            "client_measurements.potential_measurement contains Inf"
        )
    if result.duplicated(["client_id", "unit_id"]).any():
        raise ProcessedSchemaError(
            "client_measurements (client_id, unit_id) pairs must be unique"
        )
    _validate_splits(result["split"], "client_measurements")
    return result[list(CLIENT_REQUIRED_COLUMNS)]


def write_processed_parquet(
    atomic_units: pd.DataFrame,
    client_measurements: pd.DataFrame,
    output_dir: Path,
) -> tuple[Path, Path]:
    """Validate and atomically replace both canonical Parquet files."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    atomic = normalize_atomic_units(atomic_units)
    clients = normalize_client_measurements(client_measurements)

    atomic_path = output_dir / "atomic_units.parquet"
    client_path = output_dir / "client_measurements.parquet"
    atomic_tmp = output_dir / ".atomic_units.parquet.tmp"
    client_tmp = output_dir / ".client_measurements.parquet.tmp"
    try:
        pq.write_table(
            pa.Table.from_pandas(
                atomic,
                schema=atomic_units_arrow_schema(),
                preserve_index=False,
                safe=True,
            ),
            atomic_tmp,
        )
        pq.write_table(
            pa.Table.from_pandas(
                clients,
                schema=client_measurements_arrow_schema(),
                preserve_index=False,
                safe=True,
            ),
            client_tmp,
        )
        atomic_tmp.replace(atomic_path)
        client_tmp.replace(client_path)
    finally:
        atomic_tmp.unlink(missing_ok=True)
        client_tmp.unlink(missing_ok=True)
    return atomic_path, client_path

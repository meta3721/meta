"""Executable data-integrity audits shared by all dataset adapters."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from raven_mcs.data.base import ProcessedBundle
from raven_mcs.data.schema import (
    ProcessedSchemaError,
    normalize_atomic_units,
    normalize_client_measurements,
)
from raven_mcs.data.split import (
    TemporalSplitError,
    assert_split_no_overlap,
    assert_time_monotonic,
)
from raven_mcs.utils.serialization import dump_json


@dataclass
class DataAuditResult:
    dataset: str
    passed: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    statistics: dict[str, Any] = field(default_factory=dict)
    physical_anomalies: list[dict[str, Any]] = field(default_factory=list)

    def fail(self, message: str) -> None:
        self.passed = False
        self.errors.append(message)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def assert_record_sources_disjoint(
    target_source_trace_ids: Iterable[str],
    client_source_trace_ids: Iterable[str],
) -> None:
    """Prevent one raw record from constructing both target and client input."""
    overlap = set(target_source_trace_ids) & set(client_source_trace_ids)
    if overlap:
        sample = sorted(overlap)[:5]
        raise ValueError(
            f"Target/client source records overlap ({len(overlap)}); sample={sample}"
        )


def audit_processed_bundle(
    bundle: ProcessedBundle,
    *,
    high_drop_rate: float = 0.10,
) -> DataAuditResult:
    """Run Phase 2A schema, split, provenance, unit, and anomaly audits."""
    result = DataAuditResult(dataset=bundle.metadata.dataset)
    try:
        bundle.metadata.validate()
    except ValueError as exc:
        result.fail(str(exc))

    try:
        atomic = normalize_atomic_units(bundle.atomic_units)
        clients = normalize_client_measurements(bundle.client_measurements)
    except ProcessedSchemaError as exc:
        result.fail(str(exc))
        return result

    try:
        assert_split_no_overlap(atomic)
        assert_time_monotonic(atomic)
    except TemporalSplitError as exc:
        result.fail(str(exc))

    atomic_units = set(atomic["unit_id"])
    unknown_units = set(clients["unit_id"]) - atomic_units
    if unknown_units:
        result.fail(
            f"client_measurements references {len(unknown_units)} unknown unit_ids"
        )

    split_by_unit = atomic.set_index("unit_id")["split"]
    joined = clients[["unit_id", "split"]].join(
        split_by_unit.rename("atomic_split"), on="unit_id"
    )
    split_mismatch = joined["split"] != joined["atomic_split"]
    if split_mismatch.any():
        result.fail(
            f"{int(split_mismatch.sum())} client rows disagree with atomic split"
        )

    try:
        assert_record_sources_disjoint(
            bundle.target_source_trace_ids,
            clients["source_trace_id"].astype(str),
        )
    except ValueError as exc:
        result.fail(str(exc))

    required_anomaly_columns = {"source_trace_id", "rule", "action", "value"}
    if not required_anomaly_columns.issubset(bundle.anomaly_records.columns):
        result.fail(
            "anomaly report missing columns: "
            f"{sorted(required_anomaly_columns - set(bundle.anomaly_records.columns))}"
        )
    else:
        result.physical_anomalies = bundle.anomaly_records.to_dict(orient="records")

    raw_count = bundle.audit_context.get("raw_record_count")
    dropped_count = bundle.audit_context.get("dropped_record_count")
    if raw_count is not None and dropped_count is not None:
        if int(raw_count) <= 0 or int(dropped_count) < 0:
            result.fail("raw/dropped record counts must be non-negative and raw > 0")
        else:
            drop_rate = float(dropped_count) / float(raw_count)
            result.statistics["drop_rate"] = drop_rate
            if drop_rate > high_drop_rate:
                result.warnings.append(
                    f"High physical-filter drop rate: {drop_rate:.2%}"
                )

    result.statistics.update(
        {
            "atomic_unit_count": len(atomic),
            "client_measurement_count": len(clients),
            "spatial_count": int(atomic["spatial_id"].nunique()),
            "time_slot_count": int(atomic["absolute_time"].nunique()),
            "split_counts": {
                str(key): int(value)
                for key, value in atomic["split"].value_counts().sort_index().items()
            },
            "warmup_count": int(atomic["is_warmup"].sum()),
            "target_unit": bundle.metadata.target_unit,
            "physical_anomaly_count": len(bundle.anomaly_records),
        }
    )
    return result


def write_audit_report(result: DataAuditResult, path: Path) -> Path:
    dump_json(result.to_dict(), path)
    return Path(path)

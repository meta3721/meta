"""Dataset-adapter contract and processed bundle types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class DatasetMetadata:
    dataset: str
    target_name: str
    target_unit: str
    spatial_unit: str
    time_unit: str
    source_name: str
    source_url: str
    raw_license: str
    adapter_version: str = "0.1.0"
    filtering_rules: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    def validate(self) -> None:
        for field_name, value in asdict(self).items():
            if field_name in {"filtering_rules", "notes"}:
                continue
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Dataset metadata {field_name} must be non-empty")
        if not self.filtering_rules:
            raise ValueError(
                "Dataset metadata must state at least one physical filtering rule"
            )


@dataclass
class ProcessedBundle:
    atomic_units: pd.DataFrame
    client_measurements: pd.DataFrame
    metadata: DatasetMetadata
    target_source_trace_ids: set[str] = field(default_factory=set)
    anomaly_records: pd.DataFrame = field(
        default_factory=lambda: pd.DataFrame(
            columns=["source_trace_id", "rule", "action", "value"]
        )
    )
    audit_context: dict[str, Any] = field(default_factory=dict)
    fleet_assignments: pd.DataFrame | None = None


class DatasetAdapter(ABC):
    """Uniform boundary for real and controlled dataset adapters."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Canonical dataset name used in configs/manifests."""

    @abstractmethod
    def discover_raw_files(self, raw_root: Path) -> tuple[Path, ...]:
        """Return sorted immutable raw inputs; raise if required inputs are absent."""

    @abstractmethod
    def prepare(self, raw_root: Path, *, seed: int) -> ProcessedBundle:
        """Create canonical in-memory tables without writing outputs."""

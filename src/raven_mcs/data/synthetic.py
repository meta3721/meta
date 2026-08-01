"""Deterministic synthetic adapter used only for Phase 2A smoke/tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from raven_mcs.data.base import DatasetAdapter, DatasetMetadata, ProcessedBundle
from raven_mcs.data.schema import (
    normalize_atomic_units,
    normalize_client_measurements,
)
from raven_mcs.data.split import TemporalSplitConfig, assign_temporal_splits


class SyntheticDatasetAdapter(DatasetAdapter):
    """Small controlled city field; never substitute for a paper dataset."""

    @property
    def name(self) -> str:
        return "synthetic"

    def discover_raw_files(self, raw_root: Path) -> tuple[Path, ...]:
        del raw_root
        return ()

    def prepare(self, raw_root: Path, *, seed: int) -> ProcessedBundle:
        del raw_root
        rng = np.random.default_rng(int(seed))
        spatial_count = 4
        time_count = 30
        start = pd.Timestamp("2026-01-01T00:00:00Z")
        rows: list[dict[str, object]] = []
        target_sources: set[str] = set()
        for time_index in range(time_count):
            absolute_time = start + pd.Timedelta(hours=time_index)
            for spatial_index in range(spatial_count):
                unit_id = f"n{spatial_index:03d}_t{time_index:04d}"
                source_id = f"target::{unit_id}"
                target_sources.add(source_id)
                hour = absolute_time.hour
                target_value = (
                    20.0
                    + 0.8 * spatial_index
                    + 2.0 * np.sin(2.0 * np.pi * hour / 24.0)
                )
                rows.append(
                    {
                        "unit_id": unit_id,
                        "spatial_id": f"n{spatial_index:03d}",
                        "absolute_time": absolute_time,
                        "target_value": target_value,
                        "target_group": f"n{spatial_index:03d}::block{hour // 6}",
                        "opportunity_stratum": (
                            f"region{spatial_index // 2}::block{hour // 6}::weekday"
                        ),
                        "public_features": {
                            "hour_sin": float(np.sin(2.0 * np.pi * hour / 24.0)),
                            "hour_cos": float(np.cos(2.0 * np.pi * hour / 24.0)),
                            "spatial_index": spatial_index,
                        },
                        "support_flag": True,
                    }
                )
        atomic = assign_temporal_splits(
            pd.DataFrame(rows), config=TemporalSplitConfig()
        )
        atomic = normalize_atomic_units(atomic)

        client_rows: list[dict[str, object]] = []
        split_by_unit = atomic.set_index("unit_id")["split"].to_dict()
        target_by_unit = atomic.set_index("unit_id")["target_value"].to_dict()
        for client_index in range(3):
            bias = (client_index - 1) * 0.1
            for unit_id in atomic["unit_id"]:
                client_rows.append(
                    {
                        "client_id": f"client-{client_index:02d}",
                        "unit_id": unit_id,
                        "potential_measurement": (
                            float(target_by_unit[unit_id])
                            + bias
                            + float(rng.normal(0.0, 0.02))
                        ),
                        "controlled_generator_parameters": None,
                        "split": split_by_unit[unit_id],
                        "source_trace_id": (
                            f"client::{client_index:02d}::{unit_id}"
                        ),
                    }
                )
        clients = normalize_client_measurements(pd.DataFrame(client_rows))
        metadata = DatasetMetadata(
            dataset="synthetic",
            target_name="controlled_temperature",
            target_unit="degree_Celsius",
            spatial_unit="synthetic_sensor",
            time_unit="hour",
            source_name="RAVEN-MCS deterministic synthetic fixture",
            source_url="internal://raven-mcs/tests",
            raw_license="internal-test-only",
            filtering_rules=("No physical filtering required for generated fixture",),
            notes=("Not admissible as a paper benchmark",),
        )
        return ProcessedBundle(
            atomic_units=atomic,
            client_measurements=clients,
            metadata=metadata,
            target_source_trace_ids=target_sources,
            audit_context={"seed": int(seed), "generator": "synthetic-v1"},
        )

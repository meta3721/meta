"""Standard data interface for processed datasets (P10-A).

Loads atomic_units.parquet and client_measurements.parquet and returns
AtomicUnit and ClientMeasurement dataclasses with strict split separation
and train-only scaling.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from raven_mcs.data.base import DatasetMetadata
from raven_mcs.data.schema import normalize_atomic_units, normalize_client_measurements


@dataclass(frozen=True)
class AtomicUnit:
    unit_id: str
    spatial_id: str
    absolute_time: float
    time_index: int
    target_value: float
    split: str
    target_group: int
    opportunity_stratum: str
    public_features: dict[str, float]
    support_flag: bool


@dataclass(frozen=True)
class ClientMeasurement:
    client_id: str
    unit_id: str
    observed_value: float
    split: str
    source_trace_id: str


class ProcessedDataset:
    """Loads and validates processed parquet data, enforcing train/val/test no overlap."""

    def __init__(self, data_dir: str | Path, metadata: DatasetMetadata) -> None:
        data_path = Path(data_dir)
        atomic_path = data_path / "atomic_units.parquet"
        client_path = data_path / "client_measurements.parquet"

        if not atomic_path.exists():
            raise FileNotFoundError(f"atomic_units.parquet not found at {atomic_path}")
        if not client_path.exists():
            raise FileNotFoundError(f"client_measurements.parquet not found at {client_path}")

        self.metadata = metadata
        self._atomic_df = pd.read_parquet(atomic_path)
        self._client_df = pd.read_parquet(client_path)

        normalize_atomic_units(self._atomic_df)
        normalize_client_measurements(self._client_df)

        self._validate_splits()
        self._build_mappings()
        self._fit_scaler()

    def _validate_splits(self) -> None:
        splits = set(self._atomic_df["split"].unique())
        expected = {"train", "validation", "test"}
        unknown = splits - expected
        if unknown:
            raise ValueError(f"Unknown split values: {unknown}")

        train_units = set(self._atomic_df.loc[self._atomic_df["split"] == "train", "unit_id"])
        val_units = set(self._atomic_df.loc[self._atomic_df["split"] == "validation", "unit_id"])
        test_units = set(self._atomic_df.loc[self._atomic_df["split"] == "test", "unit_id"])

        if train_units & val_units:
            raise ValueError("Overlap between train and validation unit_ids")
        if train_units & test_units:
            raise ValueError("Overlap between train and test unit_ids")
        if val_units & test_units:
            raise ValueError("Overlap between validation and test unit_ids")

        meas_units = set(self._client_df["unit_id"].unique())
        if meas_units - (train_units | val_units | test_units):
            raise ValueError("client_measurements contain unit_ids not in atomic_units")

    def _build_mappings(self) -> None:
        self._unit_id_to_row: dict[str, int] = {}
        for idx, row in self._atomic_df.iterrows():
            self._unit_id_to_row[str(row["unit_id"])] = idx

        spatial_ids = sorted(self._atomic_df["spatial_id"].unique())
        self._spatial_to_idx: dict[str, int] = {sid: i for i, sid in enumerate(spatial_ids)}
        self.num_spatial = len(spatial_ids)

        raw_groups = sorted(self._atomic_df["target_group"].unique())
        self._target_group_str_to_int: dict[str, int] = {
            g: i for i, g in enumerate(raw_groups)
        }
        self.num_groups = len(raw_groups)
        self._target_groups = list(range(self.num_groups))

    def _fit_scaler(self) -> None:
        train_mask = self._atomic_df["split"] == "train"
        train_targets = self._atomic_df.loc[train_mask, "target_value"].values
        self.target_mean = float(np.mean(train_targets))
        self.target_std = float(np.std(train_targets))
        if self.target_std < 1e-10:
            self.target_std = 1.0

    def spatial_index(self, spatial_id: str) -> int:
        return self._spatial_to_idx[str(spatial_id)]

    def _absolute_time_hours(self, row: pd.Series) -> float:
        ts = row["absolute_time"]
        if hasattr(ts, "timestamp"):
            return float(ts.timestamp()) / 3600.0
        return float(ts)

    def _encode_target_group(self, raw_value: str) -> int:
        """Encode string target_group to integer index."""
        encoded = self._target_group_str_to_int.get(str(raw_value))
        if encoded is not None:
            return encoded
        return 0

    def get_atomic_units(self, split: str | None = None) -> list[AtomicUnit]:
        df = self._atomic_df if split is None else self._atomic_df[self._atomic_df["split"] == split]
        units: list[AtomicUnit] = []
        for _, row in df.iterrows():
            units.append(AtomicUnit(
                unit_id=str(row["unit_id"]),
                spatial_id=str(row["spatial_id"]),
                absolute_time=self._absolute_time_hours(row),
                time_index=int(row["time_index"]),
                target_value=float(row["target_value"]),
                split=str(row["split"]),
                target_group=self._encode_target_group(str(row["target_group"])),
                opportunity_stratum=str(row["opportunity_stratum"]),
                public_features={},
                support_flag=bool(row.get("support_flag", True)),
            ))
        return units

    def get_client_measurements(self, split: str | None = None) -> list[ClientMeasurement]:
        df = self._client_df if split is None else self._client_df[self._client_df["split"] == split]
        measurements: list[ClientMeasurement] = []
        for _, row in df.iterrows():
            measurements.append(ClientMeasurement(
                client_id=str(row["client_id"]),
                unit_id=str(row["unit_id"]),
                observed_value=float(row["potential_measurement"]),
                split=str(row["split"]),
                source_trace_id=str(row.get("source_trace_id", "")),
            ))
        return measurements

    def get_atomic_by_id(self, unit_id: str) -> Optional[AtomicUnit]:
        idx = self._unit_id_to_row.get(unit_id)
        if idx is None:
            return None
        row = self._atomic_df.iloc[idx]
        return AtomicUnit(
            unit_id=str(row["unit_id"]),
            spatial_id=str(row["spatial_id"]),
            absolute_time=self._absolute_time_hours(row),
            time_index=int(row["time_index"]),
            target_value=float(row["target_value"]),
            split=str(row["split"]),
            target_group=self._encode_target_group(str(row["target_group"])),
            opportunity_stratum=str(row["opportunity_stratum"]),
            public_features={},
            support_flag=bool(row.get("support_flag", True)),
        )

    @property
    def atomic_df(self) -> pd.DataFrame:
        return self._atomic_df

    @property
    def client_df(self) -> pd.DataFrame:
        return self._client_df

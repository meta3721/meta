"""Train-only standardization with auditable fitted statistics."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable

import numpy as np
import pandas as pd

from raven_mcs.utils.hashing import sha256_json


class ScalingError(ValueError):
    """Raised for leakage-prone or invalid scaling requests."""


@dataclass(frozen=True)
class ScalingStatistic:
    column: str
    mean: float
    scale: float
    train_count: int
    train_values_hash: str
    constant_column: bool


@dataclass(frozen=True)
class TrainOnlyStandardizer:
    """Immutable standardizer whose statistics are fitted only on split=train."""

    statistics: tuple[ScalingStatistic, ...]
    fitted_split: str = "train"

    @classmethod
    def fit(
        cls,
        frame: pd.DataFrame,
        columns: Iterable[str],
        *,
        split_column: str = "split",
    ) -> TrainOnlyStandardizer:
        if split_column not in frame:
            raise ScalingError(f"Missing split column: {split_column}")
        train = frame.loc[frame[split_column].astype(str) == "train"]
        if train.empty:
            raise ScalingError("Cannot fit scaler without train rows")

        statistics: list[ScalingStatistic] = []
        for column in columns:
            if column not in train:
                raise ScalingError(f"Missing scaling column: {column}")
            values = pd.to_numeric(train[column], errors="raise").to_numpy(
                dtype=np.float64
            )
            if not np.isfinite(values).all():
                raise ScalingError(f"Train column {column} contains NaN/Inf")
            mean = float(values.mean())
            raw_scale = float(values.std(ddof=0))
            constant = raw_scale == 0.0
            scale = 1.0 if constant else raw_scale
            statistics.append(
                ScalingStatistic(
                    column=column,
                    mean=mean,
                    scale=scale,
                    train_count=len(values),
                    train_values_hash=sha256_json(values.tolist()),
                    constant_column=constant,
                )
            )
        if not statistics:
            raise ScalingError("At least one scaling column is required")
        return cls(statistics=tuple(statistics))

    def transform(self, frame: pd.DataFrame, *, suffix: str = "_standardized") -> pd.DataFrame:
        """Return a copy with standardized columns; never refit implicitly."""
        result = frame.copy()
        for statistic in self.statistics:
            if statistic.column not in result:
                raise ScalingError(f"Missing scaling column: {statistic.column}")
            values = pd.to_numeric(result[statistic.column], errors="raise").astype(
                "float64"
            )
            result[f"{statistic.column}{suffix}"] = (
                values - statistic.mean
            ) / statistic.scale
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "fitted_split": self.fitted_split,
            "statistics": [asdict(statistic) for statistic in self.statistics],
        }

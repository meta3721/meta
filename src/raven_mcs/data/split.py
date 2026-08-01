"""Leakage-safe temporal splitting and warm-up assignment."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, floor

import pandas as pd

from raven_mcs.data.schema import VALID_SPLITS


class TemporalSplitError(ValueError):
    """Raised when temporal split boundaries are invalid or overlap."""


@dataclass(frozen=True)
class TemporalSplitConfig:
    train_fraction: float = 0.60
    validation_fraction: float = 0.20
    test_fraction: float = 0.20
    warmup_fraction_of_train: float = 0.20

    def validate(self) -> None:
        fractions = (
            self.train_fraction,
            self.validation_fraction,
            self.test_fraction,
        )
        if any(value <= 0 or value >= 1 for value in fractions):
            raise TemporalSplitError("train/validation/test fractions must be in (0, 1)")
        if abs(sum(fractions) - 1.0) > 1e-12:
            raise TemporalSplitError("train/validation/test fractions must sum to 1")
        if not 0 < self.warmup_fraction_of_train <= 1:
            raise TemporalSplitError("warmup_fraction_of_train must be in (0, 1]")


def assign_temporal_splits(
    frame: pd.DataFrame,
    *,
    config: TemporalSplitConfig = TemporalSplitConfig(),
    time_column: str = "absolute_time",
) -> pd.DataFrame:
    """
    Split by unique absolute time slots, never by individual rows.

    Every row at one absolute time receives the same split. Warm-up is the first
    ceil(20%) of train time slots and remains part of the train split.
    """
    config.validate()
    if time_column not in frame:
        raise TemporalSplitError(f"Missing time column: {time_column}")
    result = frame.copy()
    result[time_column] = pd.to_datetime(result[time_column], utc=True, errors="raise")
    slots = pd.Index(result[time_column].drop_duplicates().sort_values())
    if len(slots) < 5:
        raise TemporalSplitError(
            "At least 5 unique time slots are required for a non-empty 60/20/20 split"
        )

    raw_counts = [
        len(slots) * config.train_fraction,
        len(slots) * config.validation_fraction,
        len(slots) * config.test_fraction,
    ]
    counts = [floor(value) for value in raw_counts]
    remaining = len(slots) - sum(counts)
    remainder_order = sorted(
        range(3), key=lambda index: raw_counts[index] - counts[index], reverse=True
    )
    for index in remainder_order[:remaining]:
        counts[index] += 1
    train_count, validation_count, test_count = counts
    if min(train_count, validation_count, test_count) < 1:
        raise TemporalSplitError("Temporal split produced an empty partition")

    train_slots = slots[:train_count]
    validation_slots = slots[train_count : train_count + validation_count]
    test_slots = slots[train_count + validation_count :]
    split_by_time = {
        **{time: "train" for time in train_slots},
        **{time: "validation" for time in validation_slots},
        **{time: "test" for time in test_slots},
    }
    result["split"] = result[time_column].map(split_by_time).astype("string")

    warmup_count = max(1, ceil(train_count * config.warmup_fraction_of_train))
    warmup_slots = set(train_slots[:warmup_count])
    result["is_warmup"] = result[time_column].isin(warmup_slots)

    slot_index = {time: index for index, time in enumerate(slots)}
    result["time_index"] = result[time_column].map(slot_index).astype("int64")
    result = result.sort_values(
        [time_column] + (["spatial_id"] if "spatial_id" in result else []),
        kind="stable",
    ).reset_index(drop=True)
    assert_split_no_overlap(result, time_column=time_column)
    assert_time_monotonic(result, time_column=time_column)
    return result


def assert_split_no_overlap(
    frame: pd.DataFrame,
    *,
    time_column: str = "absolute_time",
    unit_column: str = "unit_id",
) -> None:
    """Assert disjoint unit IDs and absolute time slots across all splits."""
    if "split" not in frame:
        raise TemporalSplitError("Missing split column")
    observed = set(frame["split"].astype(str).unique())
    invalid = observed - VALID_SPLITS
    if invalid:
        raise TemporalSplitError(f"Invalid split values: {sorted(invalid)}")
    if observed != VALID_SPLITS:
        raise TemporalSplitError(
            f"All train/validation/test splits are required; observed={sorted(observed)}"
        )

    for column in (time_column, unit_column):
        if column not in frame:
            continue
        sets = {
            split: set(frame.loc[frame["split"] == split, column])
            for split in VALID_SPLITS
        }
        if (
            sets["train"] & sets["validation"]
            or sets["train"] & sets["test"]
            or sets["validation"] & sets["test"]
        ):
            raise TemporalSplitError(f"{column} overlaps across temporal splits")


def assert_time_monotonic(
    frame: pd.DataFrame, *, time_column: str = "absolute_time"
) -> None:
    """Assert nondecreasing absolute time and matching dense time index."""
    if time_column not in frame or "time_index" not in frame:
        raise TemporalSplitError("absolute_time and time_index are required")
    times = pd.to_datetime(frame[time_column], utc=True, errors="raise")
    if not times.is_monotonic_increasing:
        raise TemporalSplitError("absolute_time must be monotonically nondecreasing")
    expected = pd.Series(pd.factorize(times, sort=True)[0], index=frame.index)
    actual = frame["time_index"].astype("int64")
    if not expected.equals(actual):
        raise TemporalSplitError("time_index must be the dense rank of absolute_time")

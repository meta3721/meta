"""Opportunity stratum mapping s(i) (paper F1.2)."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


class StrataError(ValueError):
    pass


@dataclass(frozen=True)
class OpportunityStrataMapper:
    """
    Coarse region × time-of-day × weekday/weekend.

    Prefers an existing `opportunity_stratum` column; otherwise derives one from
    `spatial_id` / `absolute_time` / public features.
    """

    column: str = "opportunity_stratum"
    time_blocks: int = 4

    def map(self, atomic_units: pd.DataFrame) -> pd.Series:
        if self.column in atomic_units:
            return atomic_units[self.column].astype(str)
        if "spatial_id" not in atomic_units or "absolute_time" not in atomic_units:
            raise StrataError(
                "Need opportunity_stratum or spatial_id+absolute_time to map strata"
            )
        times = pd.to_datetime(atomic_units["absolute_time"], utc=True, errors="raise")
        block = (times.dt.hour // max(1, 24 // int(self.time_blocks))).astype(int)
        weekday = times.dt.dayofweek.map(lambda d: "weekend" if int(d) >= 5 else "weekday")
        region = atomic_units["spatial_id"].astype(str).map(lambda value: value[: max(1, len(value) // 2)])
        return (
            region.astype(str)
            + "::block"
            + block.astype(str)
            + "::"
            + weekday.astype(str)
        )

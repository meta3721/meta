"""Target groups, atomic masses, and client-stratum masses (paper F1.3, F1.5–F1.7)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np
import pandas as pd


class TargetError(ValueError):
    pass


@dataclass(frozen=True)
class GroupMapper:
    """Map atomic units to evaluation target groups h(i)."""

    column: str = "target_group"

    def map(self, atomic_units: pd.DataFrame) -> pd.Series:
        if self.column not in atomic_units:
            raise TargetError(f"Missing target group column: {self.column}")
        return atomic_units[self.column].astype(str)


@dataclass(frozen=True)
class FrozenTimeBlockMapper:
    """Prediction-independent mapping over sorted, frozen time slots."""

    group_count: int = 4
    time_column: str = "time_index"

    def map(self, atomic_units: pd.DataFrame) -> pd.Series:
        if self.group_count not in {4, 8}:
            raise TargetError("main target group count must be 4 or 8")
        if self.time_column not in atomic_units:
            raise TargetError(f"Missing time column: {self.time_column}")
        slots = np.sort(atomic_units[self.time_column].dropna().unique())
        if len(slots) < self.group_count:
            raise TargetError("fewer time slots than frozen target groups")
        slot_to_group: dict[object, int] = {}
        for group_id, block in enumerate(np.array_split(slots, self.group_count)):
            for slot in block:
                slot_to_group[slot] = group_id
        mapped = atomic_units[self.time_column].map(slot_to_group)
        if mapped.isna().any():
            raise TargetError("unmapped time slot in frozen target support")
        return mapped.astype("int64")


@dataclass(frozen=True)
class RepeatableTimeOfDayMapper:
    """Map each timestamp to a repeatable UTC six-hour block."""

    timezone: str = "UTC"
    time_column: str = "absolute_time"

    def map(self, atomic_units: pd.DataFrame) -> pd.Series:
        if self.timezone != "UTC":
            raise TargetError("SensorScope E1 currently freezes UTC time-of-day")
        if self.time_column not in atomic_units:
            raise TargetError(f"Missing time column: {self.time_column}")
        timestamps = pd.to_datetime(
            atomic_units[self.time_column], utc=True, errors="coerce",
        )
        if timestamps.isna().any():
            raise TargetError("invalid absolute_time for repeatable UTC mapping")
        return (timestamps.dt.hour // 6).astype("int64")


@dataclass(frozen=True)
class TargetMasses:
    atom_mass: pd.Series  # index=unit_id
    group_mass: pd.Series  # index=group
    within_group: pd.Series  # index=unit_id, ν_{i|h}
    support_flag: pd.Series  # index=unit_id


class TargetBuilder:
    """
    Build nonnegative, normalized target masses from supported atomic units.

    Main objective: uniform over supported units in the evaluation split,
    then marginalize to μ_h and ν_{i|h}.
    """

    def __init__(
        self,
        *,
        group_mapper: GroupMapper | None = None,
        support_column: str = "support_flag",
        unit_column: str = "unit_id",
        split_column: str = "split",
    ) -> None:
        self.group_mapper = group_mapper or GroupMapper()
        self.support_column = support_column
        self.unit_column = unit_column
        self.split_column = split_column

    def build(
        self,
        atomic_units: pd.DataFrame,
        *,
        split: str = "test",
        service_weights: Mapping[str, float] | None = None,
    ) -> TargetMasses:
        frame = atomic_units.copy()
        if self.unit_column not in frame or self.split_column not in frame:
            raise TargetError("atomic_units missing unit_id/split")
        if self.support_column not in frame:
            raise TargetError(f"Missing support column: {self.support_column}")

        selected = frame.loc[frame[self.split_column].astype(str) == str(split)].copy()
        if selected.empty:
            raise TargetError(f"No atomic units in split={split}")
        supported = selected.loc[selected[self.support_column].astype(bool)].copy()
        if supported.empty:
            raise TargetError(f"No supported atomic units in split={split}")

        groups = self.group_mapper.map(supported)
        supported = supported.assign(_group=groups)
        unit_ids = supported[self.unit_column].astype(str)

        if service_weights is None:
            raw = pd.Series(1.0, index=unit_ids.to_numpy())
        else:
            raw = unit_ids.map(lambda unit: float(service_weights.get(unit, 0.0)))
            raw.index = unit_ids.to_numpy()
            if float(raw.sum()) <= 0:
                raise TargetError("service_weights sum to zero on supported units")

        if (raw < 0).any():
            raise TargetError("target masses must be nonnegative")
        atom = raw / float(raw.sum())
        atom.index = unit_ids.to_numpy()

        group_mass = atom.groupby(supported["_group"].to_numpy(), sort=False).sum()
        within = atom / atom.index.to_series().map(group_mass).to_numpy()
        within.index = atom.index

        support = pd.Series(True, index=atom.index)
        return TargetMasses(
            atom_mass=atom.astype("float64"),
            group_mass=group_mass.astype("float64"),
            within_group=within.astype("float64"),
            support_flag=support,
        )


def client_stratum_mass(
    lambda_given_stratum: Mapping[str, Mapping[str, float]] | pd.DataFrame,
    stratum_mass: Mapping[str, float] | pd.Series,
) -> pd.DataFrame:
    """
    π_{k,s}^tar = Λ_s^tar · λ_{k|s}^tar.

    Returns DataFrame indexed by stratum with client columns.
    """
    if isinstance(stratum_mass, pd.Series):
        lam_s = stratum_mass.astype("float64")
    else:
        lam_s = pd.Series({str(k): float(v) for k, v in stratum_mass.items()}, dtype="float64")
    if (lam_s < 0).any() or float(lam_s.sum()) <= 0:
        raise TargetError("stratum_mass must be nonnegative and positive-sum")
    lam_s = lam_s / float(lam_s.sum())

    if isinstance(lambda_given_stratum, pd.DataFrame):
        cond = lambda_given_stratum.astype("float64")
    else:
        # dict[client][stratum] -> DataFrame with strata rows, client columns
        cond = pd.DataFrame(
            {
                str(client): {str(s): float(v) for s, v in per.items()}
                for client, per in lambda_given_stratum.items()
            }
        ).astype("float64")
    if set(cond.columns).issuperset(set(lam_s.index)) and not set(cond.index).issuperset(
        set(lam_s.index)
    ):
        cond = cond.T
    cond = cond.reindex(index=lam_s.index).fillna(0.0)
    if (cond.to_numpy() < 0).any():
        raise TargetError("lambda_{k|s} must be nonnegative")
    row_sums = cond.sum(axis=1).replace(0.0, np.nan)
    cond = cond.div(row_sums, axis=0).fillna(0.0)
    return cond.mul(lam_s, axis=0)


def client_atom_mass(
    client_stratum: pd.DataFrame,
    unit_stratum: pd.Series,
    within_stratum: pd.Series,
) -> pd.DataFrame:
    """π_{k,i}^tar = π_{k,s(i)}^tar · ν_{i|s(i)}^tar."""
    units = within_stratum.index.astype(str)
    strata = unit_stratum.reindex(units).astype(str)
    out = {}
    for client in client_stratum.columns.astype(str):
        pi_s = strata.map(client_stratum[client]).astype("float64").fillna(0.0)
        out[client] = (pi_s * within_stratum.astype("float64")).to_numpy()
    result = pd.DataFrame(out, index=units)
    total = float(result.to_numpy().sum())
    if total <= 0:
        raise TargetError("client_atom_mass sums to zero")
    return result / total


def audit_target_support(masses: TargetMasses, *, min_units: int = 1) -> list[str]:
    errors: list[str] = []
    if len(masses.atom_mass) < min_units:
        errors.append(f"supported units {len(masses.atom_mass)} < {min_units}")
    if abs(float(masses.atom_mass.sum()) - 1.0) > 1e-9:
        errors.append("atom_mass does not sum to 1")
    if abs(float(masses.group_mass.sum()) - 1.0) > 1e-9:
        errors.append("group_mass does not sum to 1")
    if (masses.atom_mass < 0).any() or (masses.group_mass < 0).any():
        errors.append("negative target masses")
    return errors

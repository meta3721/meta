"""Per-window data access for real datasets (P10-A).

Given a window_id and EventTrace, extracts client observations and
risk set records for local training.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class WindowRecords:
    window_id: int
    client_id: str
    risk_set_unit_ids: list[str]
    observed_unit_ids: list[str]
    observed_values: list[float]
    opportunity_strata: list[str]
    target_groups: list[int]
    O: np.ndarray  # observation indicators
    U: int  # usable indicator
    downloaded_version: int
    model_age: float
    tau: int
    registration_time: float
    window_close_time: float
    planned_workload_pre: float
    risk_set_size_pre: int
    observed_count: int
    attempted: int
    usable: int
    attempt_failure: int
    non_attempt: int


@dataclass
class WindowDataSlice:
    """Per-window data extracted from EventTrace and processed dataset."""

    window_id: int
    records: list[WindowRecords] = field(default_factory=list)
    active_client_ids: list[str] = field(default_factory=list)
    all_client_ids: list[str] = field(default_factory=list)  # E_r — all with m>0

    @property
    def num_active(self) -> int:
        return len(self.active_client_ids)

    @property
    def is_empty(self) -> bool:
        return len(self.active_client_ids) == 0


def extract_window_slice(
    window_id: int,
    event_trace_events: Any,  # pd.DataFrame with EventTrace schema
    processed_dataset: Any,  # ProcessedDataset
    coarse_time_groups: int | None = None,
) -> WindowDataSlice:
    """Extract per-window observation records from EventTrace and atomic units.

    Args:
        window_id: The window to extract data for.
        event_trace_events: DataFrame from EventTrace.events.
        processed_dataset: ProcessedDataset instance for atomic unit lookups.

    Returns:
        WindowDataSlice with records for all clients in the window.
    """
    rows = event_trace_events.loc[event_trace_events["window_id"] == window_id]
    if rows.empty:
        return WindowDataSlice(window_id=window_id)

    records: list[WindowRecords] = []
    active_client_ids: list[str] = []
    all_client_ids: list[str] = []

    for _, row in rows.iterrows():
        client_id = str(row["client_id"])
        all_client_ids.append(client_id)

        risk_ids = list(row["risk_set_unit_ids"]) if isinstance(row["risk_set_unit_ids"], (list, np.ndarray)) else []
        obs_ids = list(row["observed_unit_ids"]) if isinstance(row["observed_unit_ids"], (list, np.ndarray)) else []
        if not set(obs_ids).issubset(set(risk_ids)):
            raise ValueError("observed_unit_ids must be a subset of risk_set_unit_ids")

        risk_strata: list[str] = []
        risk_groups: list[int] = []
        obs_values: list[float] = []
        ordered_obs_ids: list[str] = []
        O_array: list[float] = []

        for rid in risk_ids:
            unit = processed_dataset.get_atomic_by_id(rid)
            if unit is not None:
                risk_strata.append(unit.opportunity_stratum)
                if coarse_time_groups is None:
                    risk_groups.append(unit.target_group)
                elif coarse_time_groups == 4:
                    utc_hour = int(np.floor(unit.absolute_time)) % 24
                    risk_groups.append(utc_hour // 6)
                else:
                    total_slots = int(processed_dataset.atomic_df["time_index"].max()) + 1
                    risk_groups.append(
                        min(coarse_time_groups - 1, int(unit.time_index * coarse_time_groups / total_slots))
                    )
            else:
                risk_strata.append("unknown")
                risk_groups.append(-1)

            is_observed = 1.0 if rid in obs_ids else 0.0
            O_array.append(is_observed)

            if is_observed:
                # Look up observed value from measurements
                if unit is None:
                    raise ValueError(f"Observed unit is absent from processed data: {rid}")
                try:
                    obs_value = processed_dataset.get_potential_measurement(
                        client_id, rid,
                    )
                except KeyError as exc:
                    raise ValueError(str(exc)) from exc
                obs_values.append(obs_value)
                ordered_obs_ids.append(rid)

        U_val = int(row["U"])
        if U_val == 1:
            active_client_ids.append(client_id)

        records.append(WindowRecords(
            window_id=window_id,
            client_id=client_id,
            risk_set_unit_ids=risk_ids,
            observed_unit_ids=ordered_obs_ids,
            observed_values=obs_values,
            opportunity_strata=risk_strata,
            target_groups=risk_groups,
            O=np.array(O_array, dtype=np.float64),
            U=U_val,
            downloaded_version=int(row["downloaded_version"]),
            model_age=float(row["model_age"]),
            tau=int(row.get("tau", row["model_age"])),
            registration_time=float(row["registration_time"]),
            window_close_time=float(window_id + 1),
            planned_workload_pre=float(row.get(
                "planned_workload_pre", len(risk_ids),
            )),
            risk_set_size_pre=int(row.get("risk_set_size_pre", len(risk_ids))),
            observed_count=int(row.get("observed_count", len(obs_ids))),
            attempted=int(row.get("attempted", len(obs_ids) > 0)),
            usable=int(row.get("usable", row["U"])),
            attempt_failure=int(row.get(
                "attempt_failure",
                len(obs_ids) > 0 and int(row["U"]) == 0,
            )),
            non_attempt=int(row.get("non_attempt", len(obs_ids) == 0)),
        ))

    return WindowDataSlice(
        window_id=window_id,
        records=records,
        active_client_ids=active_client_ids,
        all_client_ids=all_client_ids,
    )

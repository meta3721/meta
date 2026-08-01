"""Shared helpers for controlled public-field matrix adapters."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd

from raven_mcs.data.controlled import (
    build_controlled_client_measurements,
    public_time_features,
    time_of_day_block,
    weekday_label,
)
from raven_mcs.data.schema import normalize_atomic_units
from raven_mcs.data.split import TemporalSplitConfig, assign_temporal_splits


def build_matrix_atomic_units(
    matrix: pd.DataFrame,
    *,
    spatial_col: str = "spatial_id",
    time_col: str = "absolute_time",
    value_col: str = "target_value",
    split_config: TemporalSplitConfig | None = None,
) -> pd.DataFrame:
    """Turn a long spatial×time frame into canonical atomic units."""
    if matrix.empty:
        raise ValueError("Cannot build atomic units from an empty matrix")
    work = matrix[[spatial_col, time_col, value_col]].copy()
    work[time_col] = pd.to_datetime(work[time_col], utc=True, errors="raise")
    work = work.sort_values([time_col, spatial_col], kind="stable").reset_index(drop=True)
    times = pd.Index(work[time_col].drop_duplicates().sort_values())
    time_to_index = {ts: idx for idx, ts in enumerate(times)}
    rows: list[dict[str, Any]] = []
    for record in work.itertuples(index=False):
        spatial_id = str(getattr(record, spatial_col))
        absolute_time = pd.Timestamp(getattr(record, time_col))
        time_index = time_to_index[absolute_time]
        features = public_time_features(absolute_time)
        block = time_of_day_block(absolute_time)
        rows.append(
            {
                "unit_id": f"{spatial_id}_t{time_index:05d}",
                "spatial_id": spatial_id,
                "absolute_time": absolute_time,
                "time_index": int(time_index),
                "target_value": float(getattr(record, value_col)),
                "target_group": f"{spatial_id}::block{block}",
                "opportunity_stratum": (
                    f"{spatial_id}::block{block}::{weekday_label(absolute_time)}"
                ),
                "public_features": features,
                "support_flag": True,
            }
        )
    atomic = assign_temporal_splits(
        pd.DataFrame(rows),
        config=split_config or TemporalSplitConfig(),
    )
    return normalize_atomic_units(atomic)


def select_dense_window(
    long_frame: pd.DataFrame,
    *,
    spatial_col: str,
    time_col: str,
    value_col: str,
    target_spatial: int,
    target_times: int,
    min_coverage: float = 0.85,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    Select a contiguous time window and stations maximizing dense coverage.

    Coverage is the fraction of non-null values in the selected submatrix.
    """
    frame = long_frame[[spatial_col, time_col, value_col]].copy()
    frame[time_col] = pd.to_datetime(frame[time_col], utc=True, errors="raise")
    pivot = frame.pivot_table(
        index=time_col, columns=spatial_col, values=value_col, aggfunc="mean"
    ).sort_index()
    if pivot.empty:
        raise ValueError("No values available for dense-window selection")

    times = list(pivot.index)
    stations = list(pivot.columns)
    if len(times) < 5 or len(stations) < 2:
        raise ValueError(
            f"Insufficient matrix shape for selection: "
            f"{len(stations)} stations × {len(times)} times"
        )

    time_window = min(int(target_times), len(times))
    station_count = min(int(target_spatial), len(stations))
    best: dict[str, Any] | None = None

    present = pivot.notna().to_numpy(dtype="float64")
    # Prefix sums over time for O(1) window completeness per station.
    prefix = np.vstack([np.zeros((1, present.shape[1])), np.cumsum(present, axis=0)])
    # Cap exhaustive search on very long horizons.
    max_starts = len(times) - time_window + 1
    if max_starts > 4000:
        step = max(1, max_starts // 4000)
        starts = range(0, max_starts, step)
    else:
        starts = range(0, max_starts)

    for start in starts:
        window_counts = prefix[start + time_window] - prefix[start]
        completeness = window_counts / float(time_window)
        order = np.argsort(-completeness, kind="stable")
        chosen_idx = order[:station_count]
        coverage = float(completeness[chosen_idx].mean()) if len(chosen_idx) else 0.0
        score = (coverage, len(chosen_idx), time_window, -start)
        if best is None or score > best["score"]:
            chosen = [str(stations[i]) for i in chosen_idx]
            best = {
                "start": start,
                "times": times[start : start + time_window],
                "stations": chosen,
                "coverage": coverage,
                "score": score,
            }

    assert best is not None
    if best["coverage"] < min_coverage:
        raise ValueError(
            f"Best dense window coverage {best['coverage']:.3f} "
            f"is below minimum {min_coverage}"
        )

    selected = pivot.loc[best["times"], best["stations"]]
    long = selected.stack().rename(value_col).reset_index()
    long.columns = [time_col, spatial_col, value_col]
    long[spatial_col] = long[spatial_col].astype(str)
    long = long.dropna(subset=[value_col]).reset_index(drop=True)
    meta = {
        "selected_spatial_count": len(best["stations"]),
        "selected_time_count": len(best["times"]),
        "coverage": best["coverage"],
        "start_time": str(best["times"][0]),
        "end_time": str(best["times"][-1]),
    }
    return long, meta


def target_source_ids_for_units(unit_ids: Iterable[str] | pd.Series) -> set[str]:
    return {f"target::{unit_id}" for unit_id in unit_ids}


def prepare_controlled_from_matrix(
    matrix: pd.DataFrame,
    *,
    seed: int,
    target_spatial: int,
    target_times: int,
    anomaly_records: pd.DataFrame | None = None,
    audit_extra: Mapping[str, Any] | None = None,
    client_count: int = 8,
    min_coverage: float = 0.70,
) -> tuple[pd.DataFrame, pd.DataFrame, set[str], dict[str, Any], pd.DataFrame]:
    """Select dense window and build atomic/client tables for controlled fields."""
    selected, window_meta = select_dense_window(
        matrix,
        spatial_col="spatial_id",
        time_col="absolute_time",
        value_col="target_value",
        target_spatial=target_spatial,
        target_times=target_times,
        min_coverage=min_coverage,
    )
    atomic = build_matrix_atomic_units(selected)
    clients = build_controlled_client_measurements(
        atomic, seed=seed, client_count=client_count
    )
    target_ids = target_source_ids_for_units(atomic["unit_id"])
    anomalies = (
        anomaly_records
        if anomaly_records is not None
        else pd.DataFrame(columns=["source_trace_id", "rule", "action", "value"])
    )
    audit = {
        "seed": int(seed),
        "window": window_meta,
        "raw_rows": int(len(matrix)),
        "selected_rows": int(len(selected)),
        **dict(audit_extra or {}),
    }
    return atomic, clients, target_ids, audit, anomalies

"""Feature extraction for Common-NDMF model input (P10-A).

Extracts spatial_index, hour, weekday, trend from atomic units.
Maps spatial_id to integer index. No client_id embedding.
"""

from __future__ import annotations

import numpy as np
import torch


def utc_weekday_from_unix_hours(hours: np.ndarray) -> np.ndarray:
    """Return Monday=0 UTC weekdays for Unix-hour timestamps."""
    values = np.asarray(hours, dtype=np.float64)
    return (
        np.floor(values / 24.0).astype(np.int64) + 3
    ) % 7


def extract_features(
    spatial_ids: list[str],
    absolute_times: list[float],
    time_indices: list[int],
    spatial_to_idx: dict[str, int],
    total_time_slots: int | None = None,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    """Extract model input features from atomic unit metadata.

    Args:
        spatial_ids: List of spatial identifiers.
        absolute_times: List of absolute timestamps (hours).
        time_indices: List of integer time indices.
        spatial_to_idx: Mapping from spatial_id to integer index.
        total_time_slots: Total number of time slots (for trend normalization).

    Returns:
        Tuple of (spatial_index, hour, weekday, trend) tensors.
    """
    n = len(spatial_ids)
    spatial_index = torch.tensor(
        [spatial_to_idx.get(sid, 0) for sid in spatial_ids],
        dtype=torch.long,
    )

    hours = np.array(absolute_times, dtype=np.float64)
    hour_tensor = torch.tensor(hours % 24.0, dtype=torch.float32)

    # weekday: 0=Monday, ..., 6=Sunday
    weekday_tensor = torch.tensor(
        utc_weekday_from_unix_hours(hours),
        dtype=torch.float32,
    )

    if total_time_slots is not None and total_time_slots > 0:
        trend = np.array(time_indices, dtype=np.float64) / float(total_time_slots)
    else:
        max_t = max(time_indices) if time_indices else 1
        trend = np.array(time_indices, dtype=np.float64) / max(max_t, 1)
    trend_tensor = torch.tensor(trend, dtype=torch.float32)

    return spatial_index, hour_tensor, weekday_tensor, trend_tensor

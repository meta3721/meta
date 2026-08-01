"""System overhead metrics — time, memory, bytes, windows to threshold (paper §十, F7.12)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class SystemMetrics:
    """Per-run system overhead measurements."""

    registration_bytes: float = 0.0
    group_summary_bytes: float = 0.0
    model_bytes: float = 0.0
    total_communication_bytes: float = 0.0

    client_local_runtime_seconds: float = 0.0
    server_correction_runtime_seconds: float = 0.0
    p2_solve_time_seconds: float = 0.0
    total_runtime_seconds: float = 0.0

    peak_ram_mb: float = 0.0
    peak_gpu_mb: float = 0.0

    active_windows: int = 0
    windows_to_target_rmse: int | None = None
    wall_clock_to_target_rmse: float | None = None

    per_window_p2_times: list[float] = field(default_factory=list)
    per_window_client_times: list[float] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "registration_bytes": self.registration_bytes,
            "group_summary_bytes": self.group_summary_bytes,
            "model_bytes": self.model_bytes,
            "total_communication_bytes": self.total_communication_bytes,
            "client_local_runtime_seconds": self.client_local_runtime_seconds,
            "server_correction_runtime_seconds": self.server_correction_runtime_seconds,
            "p2_solve_time_seconds": self.p2_solve_time_seconds,
            "total_runtime_seconds": self.total_runtime_seconds,
            "peak_ram_mb": self.peak_ram_mb,
            "peak_gpu_mb": self.peak_gpu_mb,
            "active_windows": self.active_windows,
            "windows_to_target_rmse": self.windows_to_target_rmse,
            "wall_clock_to_target_rmse": self.wall_clock_to_target_rmse,
        }


class SystemTimer:
    """Context manager for measuring code block runtime."""

    def __init__(self) -> None:
        self.elapsed: float = 0.0
        self._start: float = 0.0

    def __enter__(self) -> "SystemTimer":
        self._start = time.perf_counter()
        return self

    def __exit__(self, *args: object) -> None:
        self.elapsed = time.perf_counter() - self._start


def estimate_model_bytes(num_params: int, dtype_bytes: int = 4) -> float:
    """Estimate model size in bytes (float32 default)."""
    return float(num_params * dtype_bytes)


def communication_bytes_per_window(
    num_clients: int,
    model_bytes: float,
    summary_bytes_per_client: float = 256.0,
    registration_bytes_per_client: float = 128.0,
) -> float:
    """Estimate total communication bytes per window."""
    return float(
        num_clients * (registration_bytes_per_client + summary_bytes_per_client)
        + model_bytes
    )

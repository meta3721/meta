"""Lagged SAG state: completed-window audit rows only (F_{r-})."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SagState:
    """Append-only completed-window history. Current-window R/O/U never enter."""

    history: list[dict[str, Any]] = field(default_factory=list)

    def append_completed(self, row: dict[str, Any]) -> None:
        forbidden = {
            "current_R",
            "current_O",
            "current_U",
            "Z",
            "dataset_id",
            "loss",
            "RMSE",
            "gradient",
            "update_vector",
        }
        leak = set(row).intersection(forbidden)
        if leak:
            raise ValueError(f"SAG history must not store {sorted(leak)}")
        self.history.append(dict(row))

    def completed(self) -> list[dict[str, Any]]:
        return list(self.history)

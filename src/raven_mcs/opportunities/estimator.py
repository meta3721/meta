"""Lagged opportunity EMA estimator (paper F3.3)."""

from __future__ import annotations

from dataclasses import dataclass, field
from collections import Counter
from typing import Iterable, Mapping

import numpy as np
import pandas as pd


@dataclass
class OpportunityEstimator:
    """
    C^opp_{k,s,r} = ρ C^opp_{k,s,r-1} + N^opp_{k,s,r-1}
    π̂ uses lagged counts only (current window outcomes never enter).
    """

    forgetting: float = 0.95
    smoothing: float = 0.0
    c_prior: float = 1.0
    counts: dict[tuple[str, str], float] = field(default_factory=dict)
    diagnostics: list[dict[str, object]] = field(default_factory=list)
    _compat_window: int = 0

    def __post_init__(self) -> None:
        if not 0 < self.forgetting <= 1:
            raise ValueError("forgetting must be in (0, 1]")
        if self.smoothing < 0:
            raise ValueError("smoothing must be nonnegative")
        if self.c_prior < 0:
            raise ValueError("c_prior must be nonnegative")

    def observe_lagged(self, client_id: str, stratum_id: str, count: float) -> None:
        """Compatibility wrapper; formal code must call update_window."""
        self.update_window(
            self._compat_window,
            {(str(client_id), str(stratum_id)): float(count)},
        )
        self._compat_window += 1

    def initialize_support(
        self, support_pairs: Iterable[tuple[str, str]],
    ) -> None:
        """Initialize frozen support without using a current-window outcome."""
        for client_id, stratum_id in support_pairs:
            self.counts.setdefault(
                (str(client_id), str(stratum_id)), float(self.c_prior),
            )

    def update_window(
        self,
        window_id: int,
        window_counts: Mapping[tuple[str, str], float] | Counter,
    ) -> None:
        """Apply exactly one EMA transition per pair for a completed window."""
        normalized = {
            (str(client), str(stratum)): float(count)
            for (client, stratum), count in window_counts.items()
        }
        keys = set(self.counts) | set(normalized)
        if not keys:
            return
        for key in sorted(keys):
            old = float(self.counts.get(key, 0.0))
            current = float(normalized.get(key, 0.0))
            new = float(self.forgetting) * old + current
            self.counts[key] = new
            self.diagnostics.append({
                "window_id": int(window_id),
                "client_id": key[0],
                "stratum_id": key[1],
                "C_old": old,
                "N_current": current,
                "C_new": new,
                "expected_C_new": float(self.forgetting) * old + current,
                "update_count_in_window": 1,
                "zero_count_decay_applied": bool(
                    current == 0.0 and old > 0.0
                ),
            })
        masses = self.pi_hat()
        for row in self.diagnostics[-len(keys):]:
            key = (str(row["client_id"]), str(row["stratum_id"]))
            row["pi_hat_opp"] = float(masses.get(key, 0.0))
            row["formula_error"] = abs(
                float(row["C_new"]) - float(row["expected_C_new"])
            )

    def pi_hat(self) -> pd.Series:
        if not self.counts:
            return pd.Series(dtype="float64")
        index = pd.MultiIndex.from_tuples(self.counts.keys(), names=["client_id", "stratum_id"])
        raw = pd.Series(
            list(self.counts.values()), index=index, dtype="float64",
        ) + float(self.smoothing)
        if float(raw.sum()) <= 0.0:
            raise RuntimeError("opportunity mass is zero")
        return raw / float(raw.sum())

    def zeta_error(
        self,
        pi_tar: pd.Series,
        pi_hat_opp: pd.Series | None = None,
    ) -> float:
        """L1 error between target and estimated opportunity masses (controlled)."""
        hat = self.pi_hat() if pi_hat_opp is None else pi_hat_opp
        aligned = pd.concat([pi_tar.rename("tar"), hat.rename("hat")], axis=1).fillna(0.0)
        return float(np.abs(aligned["tar"] - aligned["hat"]).sum())

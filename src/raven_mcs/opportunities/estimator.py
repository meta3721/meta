"""Lagged opportunity EMA estimator (paper F3.3)."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class OpportunityEstimator:
    """
    C^opp_{k,s,r} = ρ C^opp_{k,s,r-1} + N^opp_{k,s,r-1}
    π̂ uses lagged counts only (current window outcomes never enter).
    """

    forgetting: float = 0.95
    smoothing: float = 1.0
    counts: dict[tuple[str, str], float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0 < self.forgetting <= 1:
            raise ValueError("forgetting must be in (0, 1]")
        if self.smoothing < 0:
            raise ValueError("smoothing must be nonnegative")

    def observe_lagged(self, client_id: str, stratum_id: str, count: float) -> None:
        key = (str(client_id), str(stratum_id))
        prev = self.counts.get(key, 0.0)
        self.counts[key] = float(self.forgetting) * prev + float(count)

    def pi_hat(self) -> pd.Series:
        if not self.counts:
            return pd.Series(dtype="float64")
        index = pd.MultiIndex.from_tuples(self.counts.keys(), names=["client_id", "stratum_id"])
        raw = pd.Series(list(self.counts.values()), index=index, dtype="float64") + float(
            self.smoothing
        )
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

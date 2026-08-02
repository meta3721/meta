#!/usr/bin/env python3
"""Generate controlled FedAsync/FLAMF-TimeAlign-Adapted diagnostics."""
from pathlib import Path

import numpy as np
import pandas as pd

from raven_mcs.aggregation.base import WindowAggregateInput
from raven_mcs.aggregation.methods import (
    FLAMFTimeAlignAdaptedAggregator,
    FedAsyncWindowAggregator,
)


def _payload(coverage, tau):
    return WindowAggregateInput(
        client_ids=["A", "B", "C"],
        raw_counts=np.array([3.0, 2.0, 1.0]),
        total_masses=np.ones(3),
        compositions=np.full((4, 3), 0.25),
        staleness=np.asarray(tau, dtype=np.float64),
        extras={"covered_time_slots": coverage},
    )


def main() -> int:
    fixtures = [
        (
            "same_tau_different_overlap",
            {"A": [1, 2, 3], "B": [1, 2], "C": [4]},
            [0.0, 0.0, 0.0],
        ),
        (
            "different_tau_same_coverage",
            {"A": [1, 2], "B": [1, 2], "C": [1, 2]},
            [0.0, 0.5, 1.0],
        ),
    ]
    rows = []
    for name, coverage, tau in fixtures:
        payload = _payload(coverage, tau)
        adapted = FLAMFTimeAlignAdaptedAggregator()
        alpha_ta = adapted.compute_server_weights(payload)
        alpha_fa = FedAsyncWindowAggregator().compute_server_weights(payload)
        for index, client in enumerate(payload.client_ids):
            rows.append({
                "fixture": name,
                "client_id": client,
                "tau": tau[index],
                "covered_slots": sorted(set(coverage[client])),
                "timestamp_credit": (
                    adapted.diagnostics_history[-1][index]["timestamp_credit"]
                ),
                "alpha_timealign": alpha_ta[index],
                "alpha_fedasync": alpha_fa[index],
                "alpha_diff": alpha_ta[index] - alpha_fa[index],
            })
    frame = pd.DataFrame(rows)
    if frame.groupby("fixture")["alpha_diff"].apply(
        lambda values: float(np.abs(values).sum()),
    ).min() <= 1e-10:
        raise RuntimeError("controlled TimeAlign/FedAsync difference gate failed")
    output = Path(__file__).resolve().parents[1] / "outputs/audits"
    output.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(
        output / "e1_r2_timealign_controlled_diagnostics.parquet",
        index=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

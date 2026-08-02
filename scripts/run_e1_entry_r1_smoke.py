#!/usr/bin/env python3
"""Guarded E1-R1 smoke entry; refuses unresolved method semantics."""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from raven_mcs.aggregation.base import WindowAggregateInput
from raven_mcs.aggregation.methods import FedAsyncWindowAggregator


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=26001)
    parser.add_argument("--windows", type=int, default=20)
    parser.add_argument("--local-steps", type=int, default=2)
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()
    if args.seed != 26001:
        raise ValueError("R1 smoke is single-seed 26001 only")
    root = Path(__file__).resolve().parents[1]
    payload = WindowAggregateInput(
        client_ids=["fixture-a", "fixture-b", "fixture-c"],
        raw_counts=np.array([1.0, 2.0, 4.0]),
        total_masses=np.ones(3),
        compositions=np.full((4, 3), 0.25),
        staleness=np.array([0.0, 0.4, 1.0]),
    )
    fed = FedAsyncWindowAggregator().compute_server_weights(payload)
    # Historical R1 evidence: the then-unresolved implementation was the
    # FedAsync formula. R2 uses a separate adapted coverage aggregator.
    align = fed.copy()
    diagnostic = pd.DataFrame({
        "r": 0,
        "client_id": payload.client_ids,
        "tau": payload.staleness,
        "fedasync_weight": fed,
        "timealign_weight": align,
        "update_alignment_term": np.nan,
        "alpha_diff": np.abs(fed - align),
        "update_diff": 0.0,
        "model_hash_equal": True,
        "status": "BASELINE_UNRESOLVED",
    })
    output = root / "outputs/audits/e1_r1_fedasync_timealign_diagnostic.parquet"
    output.parent.mkdir(parents=True, exist_ok=True)
    diagnostic.to_parquet(output, index=False)
    if np.allclose(fed, align):
        raise RuntimeError(
            "TimeAlign is BASELINE_UNRESOLVED and duplicates FedAsync; "
            "five-method R1 smoke is blocked",
        )
    raise RuntimeError("unreachable until TimeAlign specification is frozen")


if __name__ == "__main__":
    raise SystemExit(main())

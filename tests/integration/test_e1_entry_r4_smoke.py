from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]


def _runs() -> dict[str, Path]:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    result = {}
    for path in (
        ROOT / f"outputs/entry_r4_smoke/runs_{commit[:12]}"
    ).rglob("manifest.json"):
        result[json.loads(path.read_text())["method"]] = path.parent
    return result


def test_r4_five_method_smoke_complete() -> None:
    runs = _runs()
    if not runs:
        pytest.skip("R4 smoke runs after final clean commit")
    assert set(runs) == {
        "fedavg_window", "fedasync_window", "flamf_timealign_adapted",
        "twostage_hajek", "raven",
    }


def test_r4_attempt_and_arrival_artifacts_complete() -> None:
    runs = _runs()
    if not runs:
        pytest.skip("R4 smoke runs after final clean commit")
    for run in runs.values():
        q = pd.read_parquet(run / "q_propensity_history.parquet")
        audit = pd.read_parquet(run / "q_attempt_diagnostics.parquet")
        support = pd.read_parquet(run / "arrival_support_diagnostics.parquet")
        assert len(q) == int(audit["attempted"].sum())
        assert not ((audit["attempted"] == 0) & audit[
            "included_in_q_training"
        ]).any()
        assert float(support.loc[
            support["support_mask"] == 0, "contribution"
        ].sum()) == 0.0


def test_r4_metrics_and_tail_head_gates() -> None:
    runs = _runs()
    if not runs:
        pytest.skip("R4 smoke runs after final clean commit")
    for run in runs.values():
        metrics = json.loads((run / "metrics_run.json").read_text())
        assert abs(
            metrics["Gap_mis"]
            - (metrics["RMSE_mu"] - metrics["RMSE_rho"])
        ) <= 1e-12
        assert metrics["tail_test_support"] > 0
        assert metrics["head_test_support"] > 0


def test_r4_aggregate_exactly_five_rows() -> None:
    path = ROOT / "outputs/aggregate/E1_balanced_entry_r4/per_seed_metrics.parquet"
    if not path.exists():
        pytest.skip("R4 aggregate generated after smoke")
    assert len(pd.read_parquet(path)) == 5

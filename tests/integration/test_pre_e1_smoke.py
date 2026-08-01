from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_pre_e1_smoke_reproducible() -> None:
    if os.environ.get("PRE_E1_RUN1") is None or os.environ.get("PRE_E1_RUN2") is None:
        pytest.skip("run paths supplied during final seal")
    run1 = Path(os.environ["PRE_E1_RUN1"])
    run2 = Path(os.environ["PRE_E1_RUN2"])
    manifest1 = json.loads((run1 / "manifest.json").read_text(encoding="utf-8"))
    manifest2 = json.loads((run2 / "manifest.json").read_text(encoding="utf-8"))
    for key in (
        "git_commit", "config_hash", "data_hash", "event_trace_hash",
        "target_group_hash",
    ):
        assert manifest1[key] == manifest2[key]
    left = pd.read_parquet(run1 / "predictions_test.parquet").sort_values(
        ["method", "unit_id"],
    )
    right = pd.read_parquet(run2 / "predictions_test.parquet").sort_values(
        ["method", "unit_id"],
    )
    assert np.allclose(left["y_pred"], right["y_pred"], rtol=0.0, atol=1e-10)

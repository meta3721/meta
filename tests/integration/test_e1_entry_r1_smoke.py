from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_e1_entry_r1_smoke_refuses_unresolved_timealign(monkeypatch) -> None:
    path = ROOT / "scripts/run_e1_entry_r1_smoke.py"
    spec = importlib.util.spec_from_file_location("run_e1_entry_r1_smoke", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(
        sys, "argv",
        [str(path), "--seed", "26001", "--windows", "20", "--local-steps", "2"],
    )
    with pytest.raises(RuntimeError, match="BASELINE_UNRESOLVED"):
        module.main()
    diagnostic = pd.read_parquet(
        ROOT / "outputs/audits/e1_r1_fedasync_timealign_diagnostic.parquet",
    )
    assert (diagnostic["alpha_diff"] == 0).all()
    assert set(diagnostic["status"]) == {"BASELINE_UNRESOLVED"}

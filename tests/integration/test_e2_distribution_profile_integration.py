"""Integration tests for E2 distribution profile freeze artifacts."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from raven_mcs.e2.distribution.base_streams import build_base_random_streams
from raven_mcs.e2.distribution.topology import build_seed_topology
from raven_mcs.e2.distribution.trace_sampler import generate_validation_mother_trace

ROOT = Path(__file__).resolve().parents[2]


def test_mother_trace_smoke_no_training() -> None:
    topo = build_seed_topology(29101, root=ROOT)
    streams = build_base_random_streams(
        29101,
        n_windows=300,
        n_clients=max(int(topo["meta"]["num_clients"]), 16),
        max_risk_set=50,
    )
    result = generate_validation_mother_trace(
        seed=29101,
        profile_id="PROFILE-S2",
        scenario_id="balanced",
        topology=topo,
        streams=streams,
        root=ROOT,
        output_dir=None,
    )
    d = result["diagnostics"][300]
    assert d["D_TV_arr_emp"] <= 0.02
    assert 0.95 <= d["tail_mass_ratio"] <= 1.05
    assert 0.18 <= d["realized_observation_rate"] <= 0.22
    assert 0.57 <= d["realized_usable_rate"] <= 0.63
    assert result["manifest"]["model_training"] is False


def test_selected_profile_and_window_frozen_if_present() -> None:
    prof = ROOT / "configs/frozen/e2_distribution/selected_strength_profile.yaml"
    win = ROOT / "configs/frozen/e2_distribution/selected_window_length.yaml"
    if not prof.is_file() or not win.is_file():
        pytest.skip("freeze artifacts not present yet")
    p = yaml.safe_load(prof.read_text(encoding="utf-8"))
    w = yaml.safe_load(win.read_text(encoding="utf-8"))
    assert p["selected_profile_id"].startswith("PROFILE-S")
    assert int(w["selected_windows"]) in (100, 200, 300)


def test_trace_matrix_complete_if_present() -> None:
    path = ROOT / "outputs/e2_distribution/E2_TRACE_MATRIX_SUMMARY.json"
    if not path.is_file():
        pytest.skip("matrix not generated yet")
    matrix = json.loads(path.read_text(encoding="utf-8"))
    assert matrix["trace_count"] == 180
    assert matrix["trace_failure_count"] == 0

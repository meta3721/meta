from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import cvxpy as cp
import numpy as np
import pytest
import yaml

from raven_mcs.aggregation.p2_cvxpy import solve_p2
from raven_mcs.propensity.usable import deadline_slack_pre
from raven_mcs.simulation.event_trace import EventTraceError, synthesize_event_trace

ROOT = Path(__file__).resolve().parents[2]


def _p2(**kwargs):
    return solve_p2(
        np.array([[0.8, 0.2], [0.2, 0.8]]),
        np.array([0.5, 0.5]),
        np.array([0.5, 0.5]),
        np.zeros(2),
        np.ones(2),
        np.zeros(2),
        lambda_group=1.0,
        lambda_beta=1.0,
        lambda_variance=0.1,
        lambda_staleness=0.1,
        alpha_max=1.0,
        e_min=2.0,
        max_server_learning_rate=1.0,
        **kwargs,
    )


def test_solver_fallback_on_inaccurate_status(monkeypatch) -> None:
    original = cp.Problem.solve
    calls = 0

    def inaccurate_then_scs(problem, *args, **kwargs):
        nonlocal calls
        calls += 1
        result = original(problem, solver=cp.SCS, eps=1e-8, max_iters=100_000)
        if calls == 1:
            problem._status = "optimal_inaccurate"
        return result

    monkeypatch.setattr(cp.Problem, "solve", inaccurate_then_scs)
    result = _p2()
    assert result.fallback_used
    assert result.primary_status == "optimal_inaccurate"
    assert result.fallback_solver == "SCS"
    assert result.status == "optimal"


def test_solver_residual_hard_gate() -> None:
    result = _p2()
    assert result.simplex_residual <= 1e-7
    assert result.nonnegative_violation <= 1e-8
    assert result.upper_bound_violation <= 1e-7
    assert result.ess_l2_violation <= 1e-7


def test_usable_implies_tau_within_smax() -> None:
    trace = synthesize_event_trace(num_windows=3, num_clients=2)
    trace.validate()
    assert ((trace.events["U"] == 0) | (trace.events["tau"] <= trace.metadata.s_max)).all()


def test_stale_expired_update_is_unusable() -> None:
    trace = synthesize_event_trace(num_windows=7, num_clients=1)
    trace.events.loc[trace.events.index[-1], ["downloaded_version", "model_age", "tau", "U"]] = [0, 6, 6, 1]
    with pytest.raises(EventTraceError, match="s_max"):
        trace.validate()
    trace.events.loc[trace.events.index[-1], "U"] = 0
    trace.validate()


def test_deadline_slack_is_pre_outcome() -> None:
    assert deadline_slack_pre(10.0, 7.25) == pytest.approx(2.75)
    source = (ROOT / "src/raven_mcs/propensity/usable.py").read_text(encoding="utf-8")
    assert "arrival_time" not in source
    assert "network_duration" not in source
    assert "update_norm" not in source


def test_git_worktree_clean_for_e1() -> None:
    if os.environ.get("PRE_E1_ENFORCE_CLEAN") != "1":
        pytest.skip("clean-worktree gate enabled only for final seal")
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True,
        text=True, check=True,
    ).stdout
    assert status == ""


def test_frozen_config_matches_commit() -> None:
    path = ROOT / "configs/frozen/pre_e1_smoke.yaml"
    if not path.exists():
        pytest.skip("generated after formal code commit")
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
        text=True, check=True,
    ).stdout.strip()
    assert config["git_commit"] == head
    assert config["validation_summary"]["completed"] is True
    assert config["s_max"] == 5


def test_pre_e1_manifest_declares_five_methods_and_seeds() -> None:
    path = ROOT / "configs/frozen/FROZEN_CONFIG_MANIFEST.json"
    if not path.exists():
        pytest.skip("generated after formal code commit")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    assert len(manifest["e1_methods"]) == 5
    seeds = manifest.get("seeds", manifest.get("e1_seeds"))
    assert seeds is not None
    assert len(seeds) == 5

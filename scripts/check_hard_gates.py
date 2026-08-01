#!/usr/bin/env python3
"""Executable G1–G5 hard-gate checks (post-E0 / Phase 4–9)."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from raven_mcs.aggregation.methods import get_aggregator
from raven_mcs.correction.effective_sample_size import effective_sample_size
from raven_mcs.correction.hajek import normalized_weights, raw_weights, total_mass, group_mass
from raven_mcs.correction.second_stage import beta_hat, d_weight, two_stage_mass
from raven_mcs.experiments.hard_gates import (
    GATE_STATUS_FAIL,
    GATE_STATUS_PASS,
    HardGate,
)
from raven_mcs.metrics.debt import prefix_debt_bound_holds
from raven_mcs.simulation.event_trace import (
    assert_methods_share_trace,
    freeze_event_trace,
    synthesize_event_trace,
    verify_event_trace_hash,
)
from raven_mcs.training.synthetic_gate_runner import build_synthetic_runner
from raven_mcs.utils.serialization import dump_json


def _g1(tmp: Path) -> dict:
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True, exist_ok=True)
    trace = synthesize_event_trace(num_windows=4, num_clients=3, seed=26001, usable_rate=1.0)
    out = tmp / "eventtrace"
    identity = freeze_event_trace(trace, out)
    errors = verify_event_trace_hash(out, expected_hash=identity["trace_hash"])
    assert_methods_share_trace({"fedavg": identity["trace_hash"], "raven": identity["trace_hash"]})
    # Tamper check
    tampered = False
    payload = (out / "events.parquet").read_bytes()
    (out / "events.parquet").write_bytes(payload + b"\x00")
    tamper_errors = verify_event_trace_hash(out)
    if tamper_errors:
        tampered = True
    # restore not required; temp dir
    ok = not errors and tampered
    return {
        "gate": HardGate.G1_EVENT.value,
        "status": GATE_STATUS_PASS if ok else GATE_STATUS_FAIL,
        "errors": errors,
        "tamper_detected": tampered,
        "trace_hash": identity["trace_hash"],
    }


def _g2(tmp: Path) -> dict:
    trace = synthesize_event_trace(num_windows=4, num_clients=3, seed=26001, usable_rate=1.0)
    runner = build_synthetic_runner(trace, method="raven", n_groups=2)
    metrics = runner.run()
    errors: list[str] = []
    for item in metrics:
        if item.active and item.theta_hash_before == item.theta_hash_after:
            errors.append(f"active window {item.window_id} did not update theta")
        if item.active and abs(sum(item.alpha) - 1.0) > 1e-8:
            errors.append(f"alpha sum invalid at window {item.window_id}")
        if not item.active and item.theta_hash_before != item.theta_hash_after:
            errors.append(f"empty window {item.window_id} changed theta")
    # one update per active window already enforced by WindowClock
    return {
        "gate": HardGate.G2_TIMING.value,
        "status": GATE_STATUS_PASS if not errors else GATE_STATUS_FAIL,
        "errors": errors,
        "windows": len(metrics),
        "active_windows": sum(1 for m in metrics if m.active),
    }


def _g3() -> dict:
    observation = np.ones(5)
    a = raw_weights(np.array([2, 1, 4, 1, 2]), np.array([0.2, 0.1, 0.5, 0.25, 0.2]))
    m_g = group_mass(observation, a, np.array([0, 0, 1, 1, 1]), n_groups=2)
    m = total_mass(m_g)
    a_bar = normalized_weights(observation, a, m)
    n_eff = effective_sample_size(observation, a, total_mass=m, normalized=a_bar)
    d = d_weight(np.array([0.5, 0.25, 0.1]))
    beta = beta_hat(two_stage_mass(np.array([42.0, 30.0, 24.0]), d))
    errors = []
    if abs(m - 42.0) > 1e-9:
        errors.append("mass mismatch")
    if abs(n_eff - (42.0**2) / 380.0) > 1e-9:
        errors.append("ess mismatch")
    if abs(beta.sum() - 1.0) > 1e-12:
        errors.append("beta sum")
    # m is not ESS
    if abs(m - n_eff) < 1e-9:
        errors.append("m and n_eff unexpectedly identical")
    return {
        "gate": HardGate.G3_WEIGHTS.value,
        "status": GATE_STATUS_PASS if not errors else GATE_STATUS_FAIL,
        "errors": errors,
        "m": m,
        "n_eff": n_eff,
        "beta": beta.tolist(),
    }


def _g4() -> dict:
    from raven_mcs.aggregation.p2_cvxpy import solve_p2

    coverage = np.array([[0.7, 0.2, 0.4], [0.3, 0.8, 0.6]])
    result = solve_p2(
        coverage,
        np.array([0.5, 0.5]),
        np.ones(3) / 3.0,
        np.array([0.2, 0.1]),
        np.array([1.0, 1.5, 0.5]),
        np.array([0.0, 0.2, 0.4]),
        lambda_group=1.0,
        lambda_beta=1.0,
        lambda_variance=0.1,
        lambda_staleness=0.1,
        alpha_max=0.5,
        e_min=3.0,
        max_server_learning_rate=1.0,
    )
    errors = []
    if abs(result.alpha.sum() - 1.0) > 1e-6:
        errors.append("alpha sum")
    if np.any(result.alpha < -1e-8):
        errors.append("alpha negative")
    if result.constraint_violation > 1e-5:
        errors.append("constraint violation")
    return {
        "gate": HardGate.G4_P2.value,
        "status": GATE_STATUS_PASS if not errors else GATE_STATUS_FAIL,
        "errors": errors,
        "alpha": result.alpha.tolist(),
        "status_solver": result.status,
    }


def _g5() -> dict:
    trace = synthesize_event_trace(num_windows=5, num_clients=3, seed=26001, usable_rate=1.0)
    runner = build_synthetic_runner(trace, method="raven", n_groups=2)
    runner.run()
    ok = prefix_debt_bound_holds(
        runner.omega_bar(), runner.mu, runner.debt, runner.scale, tol=1e-8
    )
    return {
        "gate": HardGate.G5_DEBT.value,
        "status": GATE_STATUS_PASS if ok else GATE_STATUS_FAIL,
        "errors": [] if ok else ["prefix debt bound failed"],
        "scale": runner.scale,
        "debt_l1": float(np.linalg.norm(runner.debt, ord=1)),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("docs/audits"))
    parser.add_argument("--work-dir", type=Path, default=Path("outputs/gate_work"))
    args = parser.parse_args(argv)
    args.work_dir.mkdir(parents=True, exist_ok=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    reports = [
        _g1(args.work_dir / "g1"),
        _g2(args.work_dir / "g2"),
        _g3(),
        _g4(),
        _g5(),
    ]
    overall = all(item["status"] == GATE_STATUS_PASS for item in reports)
    payload = {"passed": overall, "gates": reports}
    out = args.output_dir / "hard_gates_g1_g5.json"
    dump_json(payload, out)
    for item in reports:
        print(f"{item['gate']}: {item['status']}")
        for error in item.get("errors", []):
            print(f"  ERROR: {error}")
    print(f"report={out}")
    print(f"g1_g5_overall={'PASS' if overall else 'FAIL'}")
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())

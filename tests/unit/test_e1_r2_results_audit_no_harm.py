"""Unit tests for corrected E1-R2 formal no-harm conclusion logic."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from check_e1_formal_gates import _no_harm_gate_ok  # noqa: E402
from statistical_tests import _no_harm_test  # noqa: E402


def _payload(result: dict, *, baseline: str = "flamf_timealign_adapted") -> dict:
    return {
        "no_harm_threshold": 0.03,
        "alpha": 0.05,
        "baseline_method": baseline,
        "no_harm_tests": {"raven": result},
        "formal_no_harm_conclusion": bool(result.get("no_harm_pass") is True),
        "formal_no_harm_conclusion_source": "no_harm_tests.raven.no_harm_pass",
    }


def test_formal_no_harm_true_only_when_actual_pass() -> None:
    baseline = [7.71, 7.72, 7.70, 7.71, 7.72]
    candidate = [7.715, 7.725, 7.705, 7.715, 7.725]
    result = _no_harm_test(baseline, candidate, threshold=0.03, alpha=0.05)
    no_harm = _payload(result)
    assert result["no_harm_pass"] is True
    assert no_harm["formal_no_harm_conclusion"] is True
    assert _no_harm_gate_ok(no_harm)


def test_formal_no_harm_conclusion_uses_actual_pass() -> None:
    test_formal_no_harm_true_only_when_actual_pass()


def test_formal_no_harm_false_when_upper_bound_exceeds_threshold() -> None:
    baseline = [1.0, 1.0, 1.0, 1.0, 1.0]
    candidate = [1.10, 1.10, 1.10, 1.10, 1.10]
    result = _no_harm_test(baseline, candidate, threshold=0.03, alpha=0.05)
    no_harm = _payload(result)
    assert result["no_harm_pass"] is False
    assert no_harm["formal_no_harm_conclusion"] is False
    assert not _no_harm_gate_ok(no_harm)


def test_formal_no_harm_fails_when_upper_bound_exceeds_threshold() -> None:
    test_formal_no_harm_false_when_upper_bound_exceeds_threshold()


def test_formal_no_harm_rejects_nan() -> None:
    no_harm = {
        "no_harm_threshold": 0.03,
        "alpha": 0.05,
        "baseline_method": "flamf_timealign_adapted",
        "no_harm_tests": {
            "raven": {
                "no_harm_pass": True,
                "one_sided_upper_bound": float("nan"),
            }
        },
        "formal_no_harm_conclusion": True,
        "formal_no_harm_conclusion_source": "no_harm_tests.raven.no_harm_pass",
    }
    assert not _no_harm_gate_ok(no_harm)


def test_formal_no_harm_rejects_missing_seed() -> None:
    # Gate payload must not pass when the underlying test reports failure due to incomplete pairs.
    result = {
        "no_harm_pass": False,
        "one_sided_upper_bound": 0.001,
        "candidate_n": 4,
        "baseline_n": 5,
    }
    no_harm = _payload(result)
    assert not _no_harm_gate_ok(no_harm)


def test_formal_no_harm_rejects_wrong_baseline() -> None:
    result = {
        "no_harm_pass": True,
        "one_sided_upper_bound": 0.001,
    }
    no_harm = _payload(result, baseline="fedavg_window")
    assert not _no_harm_gate_ok(no_harm)


def test_sealed_gates_use_corrected_no_harm() -> None:
    from check_e1_r2_results_seal_gates import evaluate_sealed_gates

    gates_path = ROOT / "outputs/gates/E1_R2_SEALED/E1_R2_SEALED_GATES.json"
    if not gates_path.is_file():
        pytest.skip("sealed gates not generated yet")
    result = evaluate_sealed_gates(ROOT)
    assert "SEALED-G4" in result["gates"]
    for stats in (
        ROOT / "outputs/statistics/E1_R2_FINAL_SEALED/no_harm_summary.json",
        ROOT / "outputs/statistics/E1_R2_SEALED/no_harm_summary.json",
    ):
        if stats.is_file():
            import json
            payload = json.loads(stats.read_text(encoding="utf-8"))
            expected = "PASS" if _no_harm_gate_ok(payload) else "FAIL"
            assert result["gates"]["SEALED-G4"] == expected
            return
    pytest.skip("no-harm summary missing")

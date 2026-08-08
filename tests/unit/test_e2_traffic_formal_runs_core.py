"""Unit tests for E2 traffic formal runs integrity."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from raven_mcs.e2.traffic_formal_runs import (
    EXPECTED_RUNS,
    EXPECTED_TRACES,
    FORMAL_SEEDS,
    FORBIDDEN_CANARY_SEED,
    METHODS,
    REGISTRY_SHA256_EXPECTED,
    SCENARIOS,
)

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "artifacts/e2_traffic_formal_runs_r1"
REG = ROOT / "configs/frozen/e2_traffic_profiles_s1/traffic_s1_s6_profile_registry.json"


@pytest.fixture(scope="module")
def ready() -> bool:
    return (ART / "E2_TRAFFIC_FORMAL_RUNS_STOP_STATUS.json").is_file()


def test_formal_seed_list() -> None:
    assert list(FORMAL_SEEDS) == list(range(30001, 30021))
    assert FORBIDDEN_CANARY_SEED == 29001
    assert EXPECTED_RUNS == 600
    assert EXPECTED_TRACES == 120


def test_registry_hash_frozen() -> None:
    import hashlib
    assert hashlib.sha256(REG.read_bytes()).hexdigest() == REGISTRY_SHA256_EXPECTED


def test_orchestrator_has_600_cartesian_product() -> None:
    text = (ROOT / "scripts/_run_e2fr_ledger_sequence.py").read_text(encoding="utf-8")
    assert "for seed in FORMAL_SEEDS" in text
    assert "for scenario in SCENARIOS" in text
    assert "for method in METHODS" in text
    assert "--run-one" in text


def test_results_when_ready(ready: bool) -> None:
    if not ready:
        pytest.skip("formal results not finalized")
    main = pd.read_csv(ART / "formal_results.csv")
    assert len(main) == 600
    assert set(main["seed"].astype(int)) == set(FORMAL_SEEDS)
    assert FORBIDDEN_CANARY_SEED not in set(main["seed"].astype(int))
    assert int(main["completed_windows"].min()) == 100


def test_stop_status_values(ready: bool) -> None:
    if not ready:
        pytest.skip("formal stop missing")
    stop = json.loads((ART / "E2_TRAFFIC_FORMAL_RUNS_STOP_STATUS.json").read_text(encoding="utf-8"))
    assert stop["status"] in {
        "PENDING_FORMAL_GATES",
        "READY_FOR_E2_TRAFFIC_PAPER_ANALYSIS",
        "E2_TRAFFIC_FORMAL_RUNS_R1_BLOCKED",
    }

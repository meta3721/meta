"""Unit tests for strict E2RR-G9 ledger closure."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from raven_mcs.e2.traffic_real_runner.ledger_g9 import (
    EXPECTED_PAIRS,
    METHODS,
    SCENARIOS,
    evaluate_g9,
    evaluate_g9_from_rows,
)

ROOT = Path(__file__).resolve().parents[2]
CANARY = ROOT / "outputs/e2_traffic_real_runner_canary"
SEQ = ROOT / "scripts/_run_e2rr_ledger_sequence.py"
REG = ROOT / "configs/frozen/e2_traffic_profiles_s1/traffic_s1_s6_profile_registry.json"


def _base_finish(scenario: str, method: str, run_id: str) -> dict:
    return {
        "record_type": "FINISH",
        "run_id": run_id,
        "label": f"e2rr_train_seed29001__{scenario}__{method}",
        "command": [
            "python", "scripts/prepare_e2_traffic_real_runner_canary.py",
            "--run-one", "--scenario", scenario, "--method", method,
        ],
        "seed": 29001,
        "scenario": scenario,
        "method": method,
        "profile_id": "PROFILE-S1",
        "run_kind": "training",
        "expected_windows": 100,
        "exit_code": 0,
        "start_time_utc": "2099-01-01T00:00:00+00:00",
        "end_time_utc": "2099-01-01T00:02:00+00:00",
        "stdout_log": "logs/dummy.stdout.log",
        "stderr_log": "logs/dummy.stderr.log",
        "input_hashes": {
            f"outputs/e2_traffic_real_runner_canary/eventtraces/{scenario}/training_eventtrace/trace_identity.json": "abc",
            "configs/frozen/e2_traffic_profiles_s1/traffic_s1_s6_profile_registry.json": "def",
        },
        "output_hashes": {},
        "placeholder": False,
    }


def test_g9_rejects_nonempty_reaudit_only_ledger() -> None:
    rows = [{
        "record_type": "FINISH",
        "run_id": "x",
        "label": "seed29001_real_runner_canary",
        "run_kind": "finalization",
        "command": ["python", "scripts/prepare_e2_traffic_real_runner_canary.py", "--reaudit-only"],
        "exit_code": 0,
        "seed": 29001,
        "profile_id": "PROFILE-S1",
    }]
    diag = evaluate_g9_from_rows(rows, root=ROOT, canary_out=CANARY)
    assert diag["pass"] is False
    assert diag["training_finish_count"] == 0


def test_g9_rejects_summary_replay_as_training() -> None:
    rows = []
    for i, (s, m) in enumerate(sorted(EXPECTED_PAIRS)):
        rid = f"r{i}"
        rows.append({
            "record_type": "START", "run_id": rid, "run_kind": "training",
            "scenario": s, "method": m, "seed": 29001, "profile_id": "PROFILE-S1",
            "expected_windows": 100,
            "command": ["python", "-c", "import json; print(json.load(open('outputs/e2_traffic_real_runner_canary/canary_summary_seed29001.json'))['completed_runs'])"],
            "stdout_log": "logs/dummy.stdout.log", "stderr_log": "logs/dummy.stderr.log",
            "input_hashes": {"x/trace_identity.json": "a", "traffic_s1_s6_profile_registry.json": "b"},
        })
        fin = _base_finish(s, m, rid)
        fin["command"] = rows[-1]["command"]
        rows.append(fin)
    # create dummy logs
    (ROOT / "logs/dummy.stdout.log").write_text("ok\n", encoding="utf-8")
    (ROOT / "logs/dummy.stderr.log").write_text("", encoding="utf-8")
    diag = evaluate_g9_from_rows(rows, root=ROOT, canary_out=CANARY)
    assert diag["pass"] is False
    assert diag["command_not_real_training_count"] > 0


def test_g9_requires_exact_30_unique_pairs() -> None:
    rows = []
    pairs = sorted(EXPECTED_PAIRS)
    # missing one, duplicate one
    pairs = pairs[:-1] + [pairs[0]]
    for i, (s, m) in enumerate(pairs):
        rid = f"r{i}"
        rows.append({"record_type": "START", "run_id": rid, "run_kind": "training",
                     "scenario": s, "method": m, "seed": 29001, "profile_id": "PROFILE-S1",
                     "expected_windows": 100, "command": ["--run-one", "--scenario", s, "--method", m],
                     "stdout_log": "logs/dummy.stdout.log", "stderr_log": "logs/dummy.stderr.log",
                     "input_hashes": {"a/trace_identity.json": "x", "traffic_s1_s6_profile_registry.json": "y"}})
        rows.append(_base_finish(s, m, rid))
    (ROOT / "logs/dummy.stdout.log").write_text("ok\n", encoding="utf-8")
    (ROOT / "logs/dummy.stderr.log").write_text("", encoding="utf-8")
    diag = evaluate_g9_from_rows(rows, root=ROOT, canary_out=CANARY)
    assert diag["pass"] is False
    assert diag["missing_scenario_method_pairs"] or diag["duplicate_scenario_method_pairs"]


def test_g9_requires_start_and_finish_for_each_run() -> None:
    rows = [_base_finish("balanced", "raven", "only-finish")]
    rows[0]["stdout_log"] = "logs/dummy.stdout.log"
    rows[0]["stderr_log"] = "logs/dummy.stderr.log"
    (ROOT / "logs/dummy.stdout.log").write_text("ok\n", encoding="utf-8")
    (ROOT / "logs/dummy.stderr.log").write_text("", encoding="utf-8")
    diag = evaluate_g9_from_rows(rows, root=ROOT, canary_out=CANARY)
    assert diag["pass"] is False
    assert diag["unpaired_run_id_count"] > 0 or diag["training_start_count"] != diag["training_finish_count"]


def test_g9_rejects_output_older_than_training_start() -> None:
    # Uses future ledger START; if real checkpoints exist they predate it.
    rows = []
    for i, (s, m) in enumerate(sorted(EXPECTED_PAIRS)):
        rid = f"old{i}"
        start = {
            "record_type": "START", "run_id": rid, "run_kind": "training",
            "scenario": s, "method": m, "seed": 29001, "profile_id": "PROFILE-S1",
            "expected_windows": 100,
            "start_time_utc": "2099-01-01T00:00:00+00:00",
            "command": ["python", "x.py", "--run-one", "--scenario", s, "--method", m],
            "stdout_log": "logs/dummy.stdout.log", "stderr_log": "logs/dummy.stderr.log",
            "input_hashes": {
                f"outputs/e2_traffic_real_runner_canary/eventtraces/{s}/training_eventtrace/trace_identity.json": "a",
                "configs/frozen/e2_traffic_profiles_s1/traffic_s1_s6_profile_registry.json": "b",
            },
        }
        fin = _base_finish(s, m, rid)
        rows.extend([start, fin])
    (ROOT / "logs/dummy.stdout.log").write_text("ok\n", encoding="utf-8")
    (ROOT / "logs/dummy.stderr.log").write_text("", encoding="utf-8")
    if (CANARY / "runs/balanced/raven/checkpoints/final.pt").is_file():
        diag = evaluate_g9_from_rows(rows, root=ROOT, canary_out=CANARY)
        assert diag["pass"] is False
        assert diag["output_predates_ledger_count"] > 0
    else:
        diag = evaluate_g9_from_rows(rows, root=ROOT, canary_out=CANARY)
        assert diag["pass"] is False  # missing manifests/hashes still fail


def test_g9_checks_manifest_identity() -> None:
    # If canary runs exist, mutate check via synthetic mismatch on seed.
    rows = []
    for i, (s, m) in enumerate(sorted(EXPECTED_PAIRS)):
        rid = f"mm{i}"
        rows.append({
            "record_type": "START", "run_id": rid, "run_kind": "training",
            "scenario": s, "method": m, "seed": 29002, "profile_id": "PROFILE-S1",
            "expected_windows": 100,
            "command": ["--run-one", "--scenario", s, "--method", m],
            "stdout_log": "logs/dummy.stdout.log", "stderr_log": "logs/dummy.stderr.log",
            "input_hashes": {"a/trace_identity.json": "x", "traffic_s1_s6_profile_registry.json": "y"},
        })
        fin = _base_finish(s, m, rid)
        fin["seed"] = 29002
        rows.append(fin)
    (ROOT / "logs/dummy.stdout.log").write_text("ok\n", encoding="utf-8")
    (ROOT / "logs/dummy.stderr.log").write_text("", encoding="utf-8")
    diag = evaluate_g9_from_rows(rows, root=ROOT, canary_out=CANARY)
    assert diag["pass"] is False
    assert diag["manifest_ledger_mismatch_count"] > 0


def test_g9_checks_checkpoint_and_trace_hashes() -> None:
    rows = []
    for i, (s, m) in enumerate(sorted(EXPECTED_PAIRS)):
        rid = f"hash{i}"
        rows.append({
            "record_type": "START", "run_id": rid, "run_kind": "training",
            "scenario": s, "method": m, "seed": 29001, "profile_id": "PROFILE-S1",
            "expected_windows": 100,
            "command": ["--run-one", "--scenario", s, "--method", m],
            "stdout_log": "logs/dummy.stdout.log", "stderr_log": "logs/dummy.stderr.log",
            "input_hashes": {
                f"outputs/e2_traffic_real_runner_canary/eventtraces/{s}/training_eventtrace/trace_identity.json": "TAMPERED",
                "configs/frozen/e2_traffic_profiles_s1/traffic_s1_s6_profile_registry.json": "y",
            },
        })
        fin = _base_finish(s, m, rid)
        fin["input_hashes"] = rows[-1]["input_hashes"]
        fin["output_hashes"] = {
            f"outputs/e2_traffic_real_runner_canary/runs/{s}/{m}/checkpoints/final.pt": "TAMPERED",
            f"outputs/e2_traffic_real_runner_canary/runs/{s}/{m}/runtime_manifest.json": "x",
            f"outputs/e2_traffic_real_runner_canary/runs/{s}/{m}/config_snapshot.json": "x",
            f"outputs/e2_traffic_real_runner_canary/runs/{s}/{m}/window_metrics.parquet": "x",
        }
        rows.append(fin)
    (ROOT / "logs/dummy.stdout.log").write_text("ok\n", encoding="utf-8")
    (ROOT / "logs/dummy.stderr.log").write_text("", encoding="utf-8")
    diag = evaluate_g9_from_rows(rows, root=ROOT, canary_out=CANARY)
    assert diag["pass"] is False
    assert diag["checkpoint_hash_mismatch_count"] > 0 or diag["trace_hash_mismatch_count"] > 0


def test_real_sequence_invokes_30_run_one_commands() -> None:
    text = SEQ.read_text(encoding="utf-8")
    assert text.count("--run-one") >= 1
    assert "for scenario in SCENARIOS" in text
    assert "for method in METHODS" in text
    assert len(SCENARIOS) * len(METHODS) == 30


def test_formal_seeds_are_forbidden() -> None:
    stop = CANARY / "E2_TRAFFIC_REAL_RUNNER_CANARY_STOP_STATUS.json"
    if stop.is_file():
        data = json.loads(stop.read_text(encoding="utf-8"))
        assert int(data.get("validation_seed_reads", 0)) == 0
        assert int(data.get("formal_seed_reads", 0)) == 0
        assert int(data.get("formal_run_count", 0)) == 0
    # sequence must not mention formal seed range as execution targets
    text = SEQ.read_text(encoding="utf-8")
    assert "30001" not in text
    assert "29101" not in text


def test_frozen_profile_unchanged() -> None:
    digest = hashlib.sha256(REG.read_bytes()).hexdigest()
    assert digest == "7d9b8292522b6fbcc15d83ebb065fc8a73b79787ed643aea49c48f30596acbc7"
    reg = json.loads(REG.read_text(encoding="utf-8"))
    assert reg["selected_strength"] == "PROFILE-S1"

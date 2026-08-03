"""Focused checks for the immutable E1 R2 protocol foundations."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def _load_script(name: str) -> ModuleType:
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


archive_script = _load_script("archive_e1_r1_weight_safety_failure")
registry_script = _load_script("build_e1_r2_candidate_registry")
trace_script = _load_script("generate_e1_r2_traces")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_candidate_registry_is_exact_and_self_hashed(tmp_path: Path) -> None:
    path = registry_script.build_registry(tmp_path)
    registry = registry_script.verify_registry(path)

    assert list(registry["candidates"]) == ["C0", "C1", "C2", "C3"]
    assert [
        candidate["a_max"] for candidate in registry["candidates"].values()
    ] == [20.0, 30.0, 40.0, 60.0]
    assert registry["frozen_parameters"] == {
        "p_min": 0.05,
        "pi_min": 1e-6,
        "d_max": 10.0,
        "q_min": 0.05,
    }
    assert registry["informational_parameters"]["opportunity_forgetting"] == {
        "value": 0.95,
        "status": "UNCHANGED_INFORMATIONAL",
        "tunable": False,
    }

    tampered = yaml.safe_load(path.read_text(encoding="utf-8"))
    tampered["candidates"]["C0"]["a_max"] = 21.0
    path.write_text(yaml.safe_dump(tampered, sort_keys=False), encoding="utf-8")
    with pytest.raises(RuntimeError, match="hash mismatch"):
        registry_script.verify_registry(path)


def test_trace_requests_are_role_locked_and_formal_is_structural() -> None:
    for role, seeds in trace_script.ROLE_SEEDS.items():
        trace_script.validate_request(role, seeds, 100)
    with pytest.raises(ValueError, match="exactly"):
        trace_script.validate_request("formal", (28001,), 100)
    with pytest.raises(ValueError, match="100 windows"):
        trace_script.validate_request("calibration", trace_script.ROLE_SEEDS["calibration"], 20)

    config = trace_script._trace_config(
        role="formal",
        seed=28001,
        registry_hash="a" * 64,
        identities={},
    )
    assert config["formal_access_policy"] == "STRUCTURAL_ONLY"
    assert config["candidate_assignment"] is None
    assert config["training_executed"] is False
    assert config["outcome_evaluation_executed"] is False
    assert config["formal_outcomes_accessed"] is False


def test_archive_is_complete_hashed_and_source_preserving(tmp_path: Path) -> None:
    source_paths = []
    for relative in (
        *archive_script.FORMAL_DELIVERABLES,
        *archive_script.DIAG_DELIVERABLES,
    ):
        source = tmp_path / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(f"evidence:{relative}".encode())
        source_paths.append(source)

    run = tmp_path / "outputs/runs/E1_FORMAL_fedavg_window_26001_fixture"
    run.mkdir(parents=True)
    (run / "manifest.json").write_text(
        json.dumps(
            {
                "method": "fedavg_window",
                "seed": 26001,
                "hard_gate_status": "FAIL",
            }
        ),
        encoding="utf-8",
    )
    (run / "RUN_GATE_REPORT.json").write_text(
        json.dumps(
            {
                "all_pass": False,
                "gates": [
                    {"gate": "E1-RUN-G6", "status": "FAIL"},
                    {"gate": "E1-RUN-G1", "status": "PASS"},
                ],
            }
        ),
        encoding="utf-8",
    )
    source_paths.extend(run / name for name in archive_script.FAILED_RUN_FILES)
    before = {path: _sha(path) for path in source_paths}

    archive = archive_script.archive_failure(tmp_path)
    status = json.loads((archive / "E1_R1_FINAL_STATUS.json").read_text())
    hashes = json.loads((archive / "ARCHIVE_HASHES.json").read_text())

    assert status == archive_script.FINAL_STATUS
    assert "ARCHIVE_HASHES.json" not in hashes["files"]
    assert len(hashes["files"]) == len(source_paths) + 1
    for relative, digest in hashes["files"].items():
        assert _sha(archive / relative) == digest
    assert {path: _sha(path) for path in source_paths} == before
    with pytest.raises(FileExistsError, match="immutable archive"):
        archive_script.archive_failure(tmp_path)

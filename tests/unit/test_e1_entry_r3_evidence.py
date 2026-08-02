from __future__ import annotations

import importlib.util
from pathlib import Path

from raven_mcs.utils.hashing import sha256_file

ROOT = Path(__file__).resolve().parents[2]


def _module():
    path = ROOT / "scripts/check_e1_entry_r3_gates.py"
    spec = importlib.util.spec_from_file_location("r3_gates", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _summary(tmp_path: Path) -> dict:
    rows = []
    for name in ("full_pytest", "r3_unit", "r3_integration", "pip_check"):
        path = tmp_path / f"{name}.log"
        path.write_text("PASS", encoding="utf-8")
        rows.append({
            "name": name,
            "exit_code": 0,
            "failed": 0,
            "passed": 1,
            "log_path": path.name,
            "log_sha256": sha256_file(path),
        })
    return {"required_commands": rows}


def test_gate_reads_pytest_exit_code(tmp_path: Path) -> None:
    assert _module().validate_test_and_git_evidence(
        _summary(tmp_path), "CLEAN", tmp_path,
    )


def test_gate_rejects_failed_test_summary(tmp_path: Path) -> None:
    summary = _summary(tmp_path)
    summary["required_commands"][0]["exit_code"] = 1
    assert not _module().validate_test_and_git_evidence(
        summary, "CLEAN", tmp_path,
    )


def test_gate_requires_git_status_clean(tmp_path: Path) -> None:
    assert not _module().validate_test_and_git_evidence(
        _summary(tmp_path), " M STATUS.md", tmp_path,
    )


def test_exact_command_log_contains_exit_codes() -> None:
    source = (
        ROOT / "scripts/run_e1_r3_test_evidence.py"
    ).read_text(encoding="utf-8")
    assert '"exit_code": result.returncode' in source


def test_test_log_hash_matches(tmp_path: Path) -> None:
    summary = _summary(tmp_path)
    log = tmp_path / summary["required_commands"][0]["log_path"]
    log.write_text("tampered", encoding="utf-8")
    assert not _module().validate_test_and_git_evidence(
        summary, "CLEAN", tmp_path,
    )

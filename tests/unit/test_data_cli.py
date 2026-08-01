from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from raven_mcs.utils.serialization import load_json


ROOT = Path(__file__).resolve().parents[2]


def test_prepare_and_audit_cli_smoke(tmp_path) -> None:
    data_root = tmp_path / "data"
    audit_root = tmp_path / "audits"
    prepared = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "prepare_data.py"),
            "--dataset",
            "synthetic",
            "--freeze",
            "--seed",
            "31",
            "--output-dir",
            str(data_root),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "audit_passed=True" in prepared.stdout
    assert "data_hash=None" not in prepared.stdout

    audited = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "audit_data.py"),
            "--dataset",
            "synthetic",
            "--data-root",
            str(data_root),
            "--output-dir",
            str(audit_root),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "passed=True" in audited.stdout
    assert (audit_root / "synthetic_audit.json").exists()


def test_phase1_lifecycle_cli_smoke(tmp_path) -> None:
    output_root = tmp_path / "runs"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "smoke_run_lifecycle.py"),
            "--seed",
            "26001",
            "--output-dir",
            str(output_root),
            "--fail-fast",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "lifecycle_smoke=PASS" in result.stdout
    run_dirs = [path for path in output_root.iterdir() if path.is_dir()]
    assert len(run_dirs) == 1
    manifest = load_json(run_dirs[0] / "manifest.json")
    assert manifest["hard_gate_status"] == "N/A"
    assert manifest["seed"] == manifest["seeds"]["master"] == 26001
    assert len(manifest["seeds"]) == 9
    assert (run_dirs[0] / "checkpoints" / "window_000000.pkl").exists()

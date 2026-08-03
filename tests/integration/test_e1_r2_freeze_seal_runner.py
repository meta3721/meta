from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_r2_scheduler_dry_run_plans_formal_without_execution(
    tmp_path: Path,
) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_e1_formal.py",
            "--dry-run-scheduler",
            "--output-root",
            str(tmp_path / "unused"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(result.stdout)
    assert payload["formal_performance_result"] is False
    assert payload["matrix_size"] == 25
    assert payload["first"]["seed"] == 28001
    assert payload["last"]["seed"] == 28005
    assert not (tmp_path / "unused").exists()


def test_smoke_contract_rejects_non_calibration_seed() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_e1_formal.py",
            "--smoke",
            "--formal",
            "false",
            "--seeds",
            "27002",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "only calibration seed 27001 and 2 windows" in result.stderr

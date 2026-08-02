from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_formal_scheduler_dry_run_does_not_claim_performance(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "scripts/run_e1_formal.py", "--dry-run-scheduler",
         "--output-root", str(tmp_path / "dry_runs")],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    payload = json.loads(result.stdout)
    assert payload["dry_run_scheduler"] is True
    assert payload["formal_performance_result"] is False


def test_formal_harness_gate_checker_exists() -> None:
    assert (ROOT / "scripts/check_e1_formal_harness_gates.py").exists()

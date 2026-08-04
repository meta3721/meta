#!/usr/bin/env python3
"""Orchestrate E2 usable-arrival repair with a real command ledger."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "E2_USABLE_ARRIVAL_INTEGRATION_AND_IDENTITY_REPAIR_R1"
LEDGER = ROOT / f"logs/{PACKAGE}_EXACT_COMMANDS.jsonl"
VENV_PY = ROOT / ".venv" / "Scripts" / "python.exe"
PYTHON = str(VENV_PY if VENV_PY.is_file() else Path(sys.executable))
WRAPPER = [PYTHON, "scripts/run_and_log.py"]


def logged(label: str, command: list[str], outputs: list[str] | None = None) -> int:
    cmd = [
        *WRAPPER,
        "--ledger", str(LEDGER),
        "--label", label,
    ]
    for out in outputs or []:
        cmd.extend(["--output", out])
    cmd.append("--")
    cmd.extend(command)
    return subprocess.run(cmd, cwd=ROOT).returncode


def main() -> int:
    if LEDGER.exists():
        LEDGER.unlink()
    steps = [
        (
            "prepare_identity_topology_smoke",
            [PYTHON, "scripts/prepare_e2_usable_arrival_repair.py"],
            [
                "configs/frozen/e2_numeric/e1_target_identity.json",
                "configs/frozen/e2_numeric/head_tail_identity.json",
                "tests/fixtures/e2_usable_topology.json",
                "outputs/audits/E2_USABLE_ARRIVAL_SEMANTIC_SMOKE.json",
            ],
        ),
        (
            "unit_tests",
            [
                PYTHON, "-m", "pytest", "-q",
                "tests/unit/test_e2_usable_arrival_unit.py",
                "--junitxml=logs/e2_usable_arrival_unit.xml",
            ],
            ["logs/e2_usable_arrival_unit.xml"],
        ),
        (
            "integration_tests",
            [
                PYTHON, "-m", "pytest", "-q",
                "tests/integration/test_e2_usable_arrival_integration.py",
                "--junitxml=logs/e2_usable_arrival_integration.xml",
            ],
            ["logs/e2_usable_arrival_integration.xml"],
        ),
        (
            "full_repository_tests",
            [
                PYTHON, "-m", "pytest", "-q",
                "--junitxml=logs/e2_usable_arrival_full_repository.xml",
            ],
            ["logs/e2_usable_arrival_full_repository.xml"],
        ),
        (
            "pip_check",
            [PYTHON, "-m", "pip", "check"],
            ["logs/e2_usable_arrival_pip_check.txt"],
        ),
    ]
    codes = {}
    for label, command, outputs in steps:
        if label == "pip_check":
            proc = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            (ROOT / "logs/e2_usable_arrival_pip_check.txt").write_text(
                (proc.stdout or "") + (proc.stderr or ""),
                encoding="utf-8",
            )
        codes[label] = logged(label, command, outputs)
        if codes[label] != 0 and label in {
            "prepare_identity_topology_smoke", "unit_tests", "integration_tests",
        }:
            return codes[label]

    # Temporary gates before export (unpacked not yet known).
    codes["gates_pre"] = logged(
        "gates_pre",
        [PYTHON, "scripts/check_e2_usable_arrival_gates.py", "--unpacked-ok"],
        [f"outputs/gates/{PACKAGE}_GATES.json"],
    )
    codes["export"] = logged(
        "export_evidence",
        [PYTHON, "scripts/export_e2_usable_arrival_evidence.py"],
        [
            f"deliverables/TO_SUBMIT_{PACKAGE}/RAVEN_MCS_{PACKAGE}_EVIDENCE.zip",
            f"deliverables/TO_SUBMIT_{PACKAGE}/FINAL_DELIVERABLE_HASHES.json",
        ],
    )
    codes["gates_final"] = logged(
        "gates_final",
        [PYTHON, "scripts/check_e2_usable_arrival_gates.py"],
        [f"outputs/gates/{PACKAGE}_GATES.json"],
    )
    # Refresh report with final numbers.
    codes["refresh_report"] = logged(
        "refresh_report",
        [PYTHON, "scripts/prepare_e2_usable_arrival_repair.py"],
        [f"deliverables/TO_SUBMIT_{PACKAGE}/{PACKAGE}_REPORT.docx"],
    )
    print(json.dumps({"exit_codes": codes}, indent=2))
    return 0 if codes.get("gates_final", 1) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Copy/rename freeze R1 logs into R1.1 required names and build test summary."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from raven_mcs.utils.hashing import sha256_file


def _counts(junit: Path) -> dict[str, int]:
    if not junit.exists():
        return {"passed": 0, "failed": 0, "skipped": 0, "xfailed": 0}
    suite = ET.parse(junit).getroot()
    if suite.tag == "testsuites":
        suite = next(iter(suite))
    tests = int(suite.attrib.get("tests", 0))
    failed = int(suite.attrib.get("failures", 0)) + int(
        suite.attrib.get("errors", 0)
    )
    skipped = int(suite.attrib.get("skipped", 0))
    return {
        "passed": tests - failed - skipped,
        "failed": failed,
        "skipped": skipped,
        "xfailed": 0,
    }


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    logs = root / "logs"
    venv = root / ".venv" / "Scripts" / "python.exe"
    python = str(venv) if venv.exists() else sys.executable

    # Preserve first failed full pytest attempt.
    hist_src = logs / "E1_FORMAL_FREEZE_R1_FULL_PYTEST_STDOUT.log"
    hist_dst = logs / "E1_FORMAL_FREEZE_R1_FULL_PYTEST_STDOUT_FIRST_FAIL.log"
    if hist_src.exists() and not hist_dst.exists():
        text = hist_src.read_text(encoding="utf-8", errors="replace")
        if "FAILED" in text:
            shutil.copy2(hist_src, hist_dst)

    # Re-run final required tests for R1.1 named artifacts.
    unit = sorted(
        str(path.relative_to(root))
        for path in (root / "tests/unit").glob("test_e1_formal_freeze_r1_1_*.py")
    )
    commands = [
        ("full_pytest", [
            python, "-m", "pytest", "-q", "-ra",
            f"--junitxml={logs / 'full_pytest_junit.xml'}",
        ], logs / "full_pytest_stdout.log", logs / "full_pytest_stderr.log",
         logs / "full_pytest_junit.xml"),
        ("freeze_unit", [
            python, "-m", "pytest", "-q", *unit,
            f"--junitxml={logs / 'freeze_unit_junit.xml'}",
        ], logs / "freeze_unit_stdout.log", logs / "freeze_unit_stderr.log",
         logs / "freeze_unit_junit.xml"),
        ("freeze_integration", [
            python, "-m", "pytest", "-q",
            "tests/integration/test_e1_formal_freeze_r1_1.py",
            f"--junitxml={logs / 'freeze_integration_junit.xml'}",
        ], logs / "freeze_integration_stdout.log",
         logs / "freeze_integration_stderr.log",
         logs / "freeze_integration_junit.xml"),
        ("pip_check", [python, "-m", "pip", "check"],
         logs / "pip_check.log", logs / "pip_check_stderr.log", None),
    ]
    summaries = []
    command_rows = []
    for name, command, stdout, stderr, junit in commands:
        start = datetime.now(timezone.utc)
        tick = time.perf_counter()
        result = subprocess.run(
            command, cwd=root, capture_output=True, text=True,
            env={**os.environ, "PYTHONPATH": str(root / "src")},
        )
        end = datetime.now(timezone.utc)
        stdout.write_text(result.stdout, encoding="utf-8")
        stderr.write_text(result.stderr, encoding="utf-8")
        if name == "pip_check":
            # Required single pip_check.log combines streams.
            (logs / "pip_check.log").write_text(
                result.stdout + result.stderr, encoding="utf-8",
            )
        counts = _counts(junit) if junit else {
            "passed": 0, "failed": 0, "skipped": 0, "xfailed": 0,
        }
        summary = {
            "name": name,
            "command": subprocess.list2cmdline(command),
            "exit_code": result.returncode,
            **counts,
            "duration_sec": time.perf_counter() - tick,
            "stdout_sha256": sha256_file(stdout),
            "stderr_sha256": sha256_file(stderr),
            "junit_sha256": sha256_file(junit) if junit and junit.exists() else None,
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
        }
        summaries.append(summary)
        command_rows.append({
            "stage": name,
            "command": summary["command"],
            "cwd": str(root),
            "start_time": summary["start_time"],
            "end_time": summary["end_time"],
            "exit_code": result.returncode,
            "stdout_log": str(stdout.relative_to(root)).replace("\\", "/"),
            "stderr_log": str(stderr.relative_to(root)).replace("\\", "/"),
            "output_paths": [
                str(stdout.relative_to(root)).replace("\\", "/"),
                str(stderr.relative_to(root)).replace("\\", "/"),
            ],
            "output_hashes": [summary["stdout_sha256"], summary["stderr_sha256"]],
            "historical_or_current": "current",
        })

    report = {
        "required_commands": summaries,
        "all_exit_zero": all(row["exit_code"] == 0 for row in summaries),
        "failed": sum(row["failed"] for row in summaries),
        "historical_attempts": [
            {
                "attempt_id": "R1_full_pytest_first_fail",
                "exit_code": 1,
                "failure_reason": (
                    "test_protocol_status_not_authorized and "
                    "test_pre_e1_manifest_declares_five_methods_and_seeds"
                ),
                "superseded_by": "tests_rerun / R1.1 full_pytest",
                "retained_log": (
                    "logs/E1_FORMAL_FREEZE_R1_FULL_PYTEST_STDOUT_FIRST_FAIL.log"
                    if hist_dst.exists()
                    else "logs/E1_FORMAL_FREEZE_R1_FULL_PYTEST_STDOUT.log"
                ),
            }
        ],
    }
    (logs / "E1_FORMAL_FREEZE_R1_1_TEST_SUMMARY.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8",
    )
    with (logs / "E1_FORMAL_FREEZE_R1_1_EXACT_COMMANDS.jsonl").open(
        "a", encoding="utf-8",
    ) as handle:
        for row in command_rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
        # Disclose unavailable original candidate commit command.
        handle.write(json.dumps({
            "stage": "git_commit_candidate_original",
            "command": (
                "original candidate commit command unavailable / not captured"
            ),
            "cwd": str(root),
            "start_time": None,
            "end_time": None,
            "exit_code": None,
            "stdout_log": "evidence/git/EXECUTION_CANDIDATE_SHOW.txt",
            "stderr_log": None,
            "output_paths": [
                "evidence/git/EXECUTION_CANDIDATE_SHOW.txt",
                "evidence/git/EXECUTION_CANDIDATE_CAT_FILE.txt",
            ],
            "output_hashes": [],
            "historical_or_current": "historical",
            "note": (
                "bb597a1 already existed before R1.1; do not fabricate "
                "the original git commit invocation"
            ),
        }, sort_keys=True) + "\n")
    print(json.dumps({
        "all_exit_zero": report["all_exit_zero"],
        "failed": report["failed"],
    }, indent=2))
    return 0 if report["all_exit_zero"] and report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

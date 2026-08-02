#!/usr/bin/env python3
"""Run Phase A tests and emit machine-readable evidence."""
from __future__ import annotations

import json
import os
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
        "passed": max(tests - failed - skipped, 0),
        "failed": failed,
        "skipped": skipped,
        "xfailed": 0,
    }


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    logs = root / "logs"
    logs.mkdir(exist_ok=True)
    python = str(root / ".venv/Scripts/python.exe")
    if not Path(python).exists():
        python = sys.executable
    env = {**os.environ, "PYTHONPATH": str(root / "src")}
    commands = [
        ("full_pytest", [python, "-m", "pytest", "-q", "-ra"]),
        ("formal_unit", [
            python, "-m", "pytest", "-q",
            "tests/unit/test_e1_formal_execution_r1.py",
        ]),
        ("formal_integration", [
            python, "-m", "pytest", "-q",
            "tests/integration/test_e1_formal_execution_r1.py",
        ]),
        ("pip_check", [python, "-m", "pip", "check"]),
    ]
    summaries = []
    rows = []
    for name, base in commands:
        junit = logs / f"E1_FORMAL_EXECUTION_R1_{name.upper()}_JUNIT.xml"
        command = list(base)
        if name != "pip_check":
            command.append(f"--junitxml={junit}")
        start = datetime.now(timezone.utc)
        tick = time.perf_counter()
        result = subprocess.run(
            command, cwd=root, capture_output=True, text=True, env=env,
        )
        end = datetime.now(timezone.utc)
        stdout = logs / f"E1_FORMAL_EXECUTION_R1_{name.upper()}_STDOUT.log"
        stderr = logs / f"E1_FORMAL_EXECUTION_R1_{name.upper()}_STDERR.log"
        stdout.write_text(result.stdout, encoding="utf-8")
        stderr.write_text(result.stderr, encoding="utf-8")
        counts = _counts(junit) if name != "pip_check" else {
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
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
        }
        summaries.append(summary)
        rows.append({
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
            "output_hashes": [
                summary["stdout_sha256"], summary["stderr_sha256"],
            ],
        })
    report = {
        "required_commands": summaries,
        "all_exit_zero": all(row["exit_code"] == 0 for row in summaries),
        "failed": sum(row["failed"] for row in summaries),
    }
    (logs / "E1_FORMAL_EXECUTION_R1_TEST_SUMMARY.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8",
    )
    with (logs / "E1_FORMAL_EXECUTION_R1_EXACT_COMMANDS.jsonl").open(
        "a", encoding="utf-8",
    ) as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    print(json.dumps({
        "all_exit_zero": report["all_exit_zero"],
        "failed": report["failed"],
    }, indent=2))
    return 0 if report["all_exit_zero"] and report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

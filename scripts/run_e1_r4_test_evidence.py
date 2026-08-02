#!/usr/bin/env python3
"""Run R4 test suites and emit machine-readable evidence."""
from __future__ import annotations

import json
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from raven_mcs.utils.hashing import sha256_file
from raven_mcs.utils.serialization import dump_json


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    logs = root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    unit_paths = sorted(str(path.relative_to(root)) for path in (
        root / "tests/unit"
    ).glob("test_e1_entry_r4_*.py"))
    commands = [
        ("full_pytest", [sys.executable, "-m", "pytest", "-q", "-ra"]),
        ("r4_unit", [sys.executable, "-m", "pytest", "-q", *unit_paths]),
        ("r4_integration", [
            sys.executable, "-m", "pytest", "-q",
            "tests/integration/test_e1_entry_r4_smoke.py",
        ]),
        ("pip_check", [sys.executable, "-m", "pip", "check"]),
    ]
    summaries = []
    command_rows = []
    for name, base_command in commands:
        junit = logs / f"E1_ENTRY_R4_{name.upper()}_JUNIT.xml"
        command = list(base_command)
        if name != "pip_check":
            command.append(f"--junitxml={junit}")
        start = datetime.now(timezone.utc)
        tick = time.perf_counter()
        result = subprocess.run(
            command, cwd=root, capture_output=True, text=True,
        )
        end = datetime.now(timezone.utc)
        stdout = logs / f"E1_ENTRY_R4_{name.upper()}_STDOUT.log"
        stderr = logs / f"E1_ENTRY_R4_{name.upper()}_STDERR.log"
        stdout.write_text(result.stdout, encoding="utf-8")
        stderr.write_text(result.stderr, encoding="utf-8")
        counts = {"passed": 0, "failed": 0, "skipped": 0, "xfailed": 0}
        if junit.exists():
            suite = ET.parse(junit).getroot()
            if suite.tag == "testsuites":
                suite = next(iter(suite))
            tests = int(suite.attrib.get("tests", 0))
            failed = int(suite.attrib.get("failures", 0)) + int(
                suite.attrib.get("errors", 0)
            )
            skipped = int(suite.attrib.get("skipped", 0))
            counts.update({
                "passed": tests - failed - skipped,
                "failed": failed,
                "skipped": skipped,
            })
        summary = {
            "name": name,
            "command": subprocess.list2cmdline(command),
            "start_time": start.isoformat(), "end_time": end.isoformat(),
            "exit_code": result.returncode, **counts,
            "duration_sec": time.perf_counter() - tick,
            "stdout_log": str(stdout.relative_to(root)),
            "stderr_log": str(stderr.relative_to(root)),
            "stdout_hash": sha256_file(stdout),
            "stderr_hash": sha256_file(stderr),
        }
        summaries.append(summary)
        command_rows.append({
            "stage": name, "command": summary["command"], "cwd": str(root),
            "start_time": summary["start_time"], "end_time": summary["end_time"],
            "exit_code": result.returncode,
            "stdout_log": summary["stdout_log"],
            "stderr_log": summary["stderr_log"],
            "output_paths": [summary["stdout_log"], summary["stderr_log"]],
            "output_hashes": [summary["stdout_hash"], summary["stderr_hash"]],
        })
    report = {
        "required_commands": summaries,
        "all_exit_zero": all(row["exit_code"] == 0 for row in summaries),
        "failed": sum(row["failed"] for row in summaries),
    }
    dump_json(report, logs / "E1_ENTRY_R4_TEST_SUMMARY.json")
    with (logs / "E1_ENTRY_R4_EXACT_COMMANDS.jsonl").open(
        "w", encoding="utf-8",
    ) as handle:
        for row in command_rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    return 0 if report["all_exit_zero"] and report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

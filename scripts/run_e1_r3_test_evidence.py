#!/usr/bin/env python3
"""Run required R3 checks and emit machine-verifiable evidence."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from raven_mcs.utils.hashing import sha256_file
from raven_mcs.utils.serialization import dump_json


def _count(output: str, label: str) -> int:
    matches = re.findall(rf"(\d+)\s+{label}", output)
    return int(matches[-1]) if matches else 0


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    logs = root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    unit_paths = sorted(
        str(path.relative_to(root))
        for path in (root / "tests/unit").glob("test_e1_entry_r3_*.py")
    )
    commands = [
        ("full_pytest", [sys.executable, "-m", "pytest", "-q", "-ra"]),
        ("r3_unit", [sys.executable, "-m", "pytest", "-q", *unit_paths]),
        (
            "r3_integration",
            [
                sys.executable, "-m", "pytest", "-q",
                "tests/integration/test_e1_entry_r3_smoke.py",
            ],
        ),
        ("pip_check", [sys.executable, "-m", "pip", "check"]),
    ]
    summaries = []
    command_rows = []
    for name, command in commands:
        start = datetime.now(timezone.utc)
        tick = time.perf_counter()
        result = subprocess.run(
            command, cwd=root, capture_output=True, text=True,
        )
        end = datetime.now(timezone.utc)
        stdout_path = logs / f"E1_ENTRY_R3_{name.upper()}_STDOUT.log"
        stderr_path = logs / f"E1_ENTRY_R3_{name.upper()}_STDERR.log"
        stdout_path.write_text(result.stdout, encoding="utf-8")
        stderr_path.write_text(result.stderr, encoding="utf-8")
        combined = result.stdout + "\n" + result.stderr
        summary = {
            "name": name,
            "command": subprocess.list2cmdline(command),
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
            "exit_code": result.returncode,
            "passed": _count(combined, "passed"),
            "failed": _count(combined, "failed"),
            "skipped": _count(combined, "skipped"),
            "xfailed": _count(combined, "xfailed"),
            "duration_sec": time.perf_counter() - tick,
            "log_path": str(stdout_path.relative_to(root)),
            "log_sha256": sha256_file(stdout_path),
            "stderr_log_path": str(stderr_path.relative_to(root)),
            "stderr_log_sha256": sha256_file(stderr_path),
        }
        summaries.append(summary)
        command_rows.append({
            "command": summary["command"],
            "cwd": str(root),
            "start_time": summary["start_time"],
            "end_time": summary["end_time"],
            "exit_code": result.returncode,
            "stdout_log": summary["log_path"],
            "stderr_log": summary["stderr_log_path"],
            "output_path": summary["log_path"],
            "output_hash": summary["log_sha256"],
        })
    report = {
        "required_commands": summaries,
        "all_exit_zero": all(row["exit_code"] == 0 for row in summaries),
        "failed": sum(row["failed"] for row in summaries),
    }
    dump_json(report, logs / "E1_ENTRY_R3_TEST_SUMMARY.json")
    with (logs / "E1_ENTRY_R3_EXACT_COMMANDS.jsonl").open(
        "w", encoding="utf-8",
    ) as handle:
        for row in command_rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    return 0 if report["all_exit_zero"] and report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

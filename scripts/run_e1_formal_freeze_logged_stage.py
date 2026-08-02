#!/usr/bin/env python3
"""Append one freeze workflow stage to the exact-command JSONL."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from raven_mcs.utils.hashing import sha256_file


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", required=True)
    parser.add_argument("--output", action="append", default=[])
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise ValueError("command required")
    root = Path(__file__).resolve().parents[1]
    venv_python = root / ".venv" / "Scripts" / "python.exe"
    if command[0] in {"python", "python3", "py"}:
        command[0] = (
            str(venv_python) if venv_python.exists() else sys.executable
        )
    logs = root / "logs"
    logs.mkdir(exist_ok=True)
    env = {**os.environ, "PYTHONPATH": str(root / "src")}
    start = datetime.now(timezone.utc)
    tick = time.perf_counter()
    result = subprocess.run(
        command, cwd=root, capture_output=True, text=True, env=env,
    )
    end = datetime.now(timezone.utc)
    stdout = logs / f"E1_FORMAL_FREEZE_R1_{args.stage.upper()}_STDOUT.log"
    stderr = logs / f"E1_FORMAL_FREEZE_R1_{args.stage.upper()}_STDERR.log"
    stdout.write_text(result.stdout, encoding="utf-8")
    stderr.write_text(result.stderr, encoding="utf-8")
    outputs = [stdout, stderr, *[root / value for value in args.output]]
    row = {
        "stage": args.stage,
        "command": subprocess.list2cmdline(command),
        "cwd": str(root),
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
        "duration_sec": time.perf_counter() - tick,
        "exit_code": result.returncode,
        "stdout_log": str(stdout.relative_to(root)),
        "stderr_log": str(stderr.relative_to(root)),
        "output_paths": [
            str(path.relative_to(root)) for path in outputs if path.exists()
        ],
        "output_hashes": [
            sha256_file(path) for path in outputs if path.is_file()
        ],
    }
    with (logs / "E1_FORMAL_FREEZE_R1_EXACT_COMMANDS.jsonl").open(
        "a", encoding="utf-8",
    ) as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")
    print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())

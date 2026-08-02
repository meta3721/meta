#!/usr/bin/env python3
"""Run one R4 workflow stage and append exact-command evidence."""
from __future__ import annotations

import argparse
import json
import subprocess
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
    if not args.command:
        raise ValueError("stage command is required")
    root = Path(__file__).resolve().parents[1]
    logs = root / "logs"
    logs.mkdir(exist_ok=True)
    start = datetime.now(timezone.utc)
    tick = time.perf_counter()
    result = subprocess.run(
        args.command, cwd=root, capture_output=True, text=True,
    )
    end = datetime.now(timezone.utc)
    stdout = logs / f"E1_ENTRY_R4_{args.stage.upper()}_STDOUT.log"
    stderr = logs / f"E1_ENTRY_R4_{args.stage.upper()}_STDERR.log"
    stdout.write_text(result.stdout, encoding="utf-8")
    stderr.write_text(result.stderr, encoding="utf-8")
    output_paths = [stdout, stderr]
    output_paths.extend(root / value for value in args.output)
    hashes = [
        sha256_file(path) if path.is_file() else None for path in output_paths
    ]
    row = {
        "stage": args.stage,
        "command": subprocess.list2cmdline(args.command),
        "cwd": str(root),
        "start_time": start.isoformat(), "end_time": end.isoformat(),
        "duration_sec": time.perf_counter() - tick,
        "exit_code": result.returncode,
        "stdout_log": str(stdout.relative_to(root)),
        "stderr_log": str(stderr.relative_to(root)),
        "output_paths": [
            str(path.relative_to(root)) for path in output_paths
        ],
        "output_hashes": hashes,
    }
    with (logs / "E1_ENTRY_R4_EXACT_COMMANDS.jsonl").open(
        "a", encoding="utf-8",
    ) as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")
    print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())

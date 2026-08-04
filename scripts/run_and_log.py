#!/usr/bin/env python3
"""Real command wrapper that appends timed ledger records."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER = ROOT / (
    "logs/E2_USABLE_ARRIVAL_INTEGRATION_AND_IDENTITY_REPAIR_R1_EXACT_COMMANDS.jsonl"
)


def _commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
        ).strip()
    except Exception:
        return "UNKNOWN"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a command and append ledger row")
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--label", required=True)
    parser.add_argument("--stdout-log", type=Path, default=None)
    parser.add_argument("--stderr-log", type=Path, default=None)
    parser.add_argument("--output", action="append", default=[], dest="outputs")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise SystemExit("missing command after --")

    stdout_log = args.stdout_log or (
        ROOT / f"logs/e2ua_cmd_{args.label}.stdout.log"
    )
    stderr_log = args.stderr_log or (
        ROOT / f"logs/e2ua_cmd_{args.label}.stderr.log"
    )
    stdout_log.parent.mkdir(parents=True, exist_ok=True)
    args.ledger.parent.mkdir(parents=True, exist_ok=True)

    start = datetime.now(timezone.utc)
    t0 = time.perf_counter()
    proc = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    duration = time.perf_counter() - t0
    end = datetime.now(timezone.utc)
    stdout_log.write_text(proc.stdout or "", encoding="utf-8")
    stderr_log.write_text(proc.stderr or "", encoding="utf-8")

    hashes = {}
    for relative in args.outputs:
        path = ROOT / relative if not Path(relative).is_absolute() else Path(relative)
        if path.is_file():
            hashes[Path(relative).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()

    record = {
        "label": args.label,
        "command": command,
        "cwd": str(ROOT.resolve()),
        "start_time_utc": start.isoformat(),
        "end_time_utc": end.isoformat(),
        "duration_sec": round(duration, 6),
        "exit_code": proc.returncode,
        "stdout_log": stdout_log.relative_to(ROOT).as_posix(),
        "stderr_log": stderr_log.relative_to(ROOT).as_posix(),
        "output_paths": args.outputs,
        "output_hashes": hashes,
        "runtime_commit": _commit(),
        "placeholder": False,
    }
    with args.ledger.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    sys.stdout.write(proc.stdout or "")
    sys.stderr.write(proc.stderr or "")
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())

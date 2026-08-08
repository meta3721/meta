#!/usr/bin/env python3
"""Real command wrapper that appends timed ledger START/FINISH records."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _append_fsync(ledger_path: Path, record: dict[str, Any]) -> None:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False) + "\n"
    with ledger_path.open("a", encoding="utf-8") as fh:
        fh.write(line)
        fh.flush()
        os.fsync(fh.fileno())


def _resolve(path_str: str) -> Path:
    path = Path(path_str)
    return path if path.is_absolute() else ROOT / path


def _hash_paths(paths: list[str]) -> tuple[dict[str, str], list[str]]:
    hashes: dict[str, str] = {}
    missing: list[str] = []
    for relative in paths:
        path = _resolve(relative)
        key = Path(relative).as_posix()
        if path.is_file():
            hashes[key] = _sha256_file(path)
        else:
            missing.append(key)
    return hashes, missing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a command and append ledger rows")
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--label", required=True)
    parser.add_argument("--stdout-log", type=Path, default=None)
    parser.add_argument("--stderr-log", type=Path, default=None)
    parser.add_argument("--output", action="append", default=[], dest="outputs")
    parser.add_argument("--input", action="append", default=[], dest="inputs")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--scenario", type=str, default=None)
    parser.add_argument("--method", type=str, default=None)
    parser.add_argument("--profile-id", type=str, default=None)
    parser.add_argument("--run-kind", type=str, default=None)
    parser.add_argument("--expected-windows", type=int, default=None)
    parser.add_argument("--metadata-json", type=str, default=None)
    parser.add_argument("--run-id", type=str, default=None)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise SystemExit("missing command after --")

    stdout_log = args.stdout_log or (ROOT / f"logs/e2ua_cmd_{args.label}.stdout.log")
    stderr_log = args.stderr_log or (ROOT / f"logs/e2ua_cmd_{args.label}.stderr.log")
    if not stdout_log.is_absolute():
        stdout_log = ROOT / stdout_log
    if not stderr_log.is_absolute():
        stderr_log = ROOT / stderr_log
    ledger_path = args.ledger if args.ledger.is_absolute() else ROOT / args.ledger
    stdout_log.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)

    meta_extra: dict[str, Any] = {}
    if args.metadata_json:
        meta_extra = json.loads(args.metadata_json)

    run_id = args.run_id or str(uuid.uuid4())
    run_kind = args.run_kind or meta_extra.get("run_kind")
    seed = args.seed if args.seed is not None else meta_extra.get("seed")
    scenario = args.scenario if args.scenario is not None else meta_extra.get("scenario")
    method = args.method if args.method is not None else meta_extra.get("method")
    profile_id = args.profile_id if args.profile_id is not None else meta_extra.get("profile_id")
    expected_windows = (
        args.expected_windows
        if args.expected_windows is not None
        else meta_extra.get("expected_windows")
    )

    input_hashes, missing_inputs = _hash_paths(list(args.inputs))
    start = datetime.now(timezone.utc)
    start_record = {
        "record_type": "START",
        "run_id": run_id,
        "label": args.label,
        "command": command,
        "cwd": str(ROOT.resolve()),
        "start_time_utc": start.isoformat(),
        "stdout_log": stdout_log.relative_to(ROOT).as_posix(),
        "stderr_log": stderr_log.relative_to(ROOT).as_posix(),
        "input_paths": list(args.inputs),
        "input_hashes": input_hashes,
        "missing_inputs": missing_inputs,
        "output_paths": list(args.outputs),
        "seed": seed,
        "scenario": scenario,
        "method": method,
        "profile_id": profile_id,
        "run_kind": run_kind,
        "expected_windows": expected_windows,
        "runtime_commit": _commit(),
        "placeholder": False,
    }
    _append_fsync(ledger_path, start_record)

    t0 = time.perf_counter()
    proc = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    duration = time.perf_counter() - t0
    end = datetime.now(timezone.utc)
    stdout_log.write_text(proc.stdout or "", encoding="utf-8")
    stderr_log.write_text(proc.stderr or "", encoding="utf-8")

    output_hashes, missing_outputs = _hash_paths(list(args.outputs))
    finish_record = {
        "record_type": "FINISH",
        "run_id": run_id,
        "label": args.label,
        "command": command,
        "cwd": str(ROOT.resolve()),
        "start_time_utc": start.isoformat(),
        "end_time_utc": end.isoformat(),
        "duration_sec": round(duration, 6),
        "exit_code": proc.returncode,
        "stdout_log": stdout_log.relative_to(ROOT).as_posix(),
        "stderr_log": stderr_log.relative_to(ROOT).as_posix(),
        "input_paths": list(args.inputs),
        "input_hashes": input_hashes,
        "missing_inputs": missing_inputs,
        "output_paths": list(args.outputs),
        "output_hashes": output_hashes,
        "missing_outputs": missing_outputs,
        "seed": seed,
        "scenario": scenario,
        "method": method,
        "profile_id": profile_id,
        "run_kind": run_kind,
        "expected_windows": expected_windows,
        "runtime_commit": _commit(),
        "placeholder": False,
    }
    _append_fsync(ledger_path, finish_record)

    sys.stdout.write(proc.stdout or "")
    sys.stderr.write(proc.stderr or "")

    # Missing declared outputs fail the wrapper even if subprocess returned 0.
    if missing_outputs and run_kind == "training":
        return proc.returncode if proc.returncode != 0 else 2
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())

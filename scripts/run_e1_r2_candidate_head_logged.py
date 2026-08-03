#!/usr/bin/env python3
"""Run one candidate-head command and append its exact audit record."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", required=True)
    parser.add_argument("--outputs", nargs="*", default=[])
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = list(args.command)
    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        parser.error("a command is required after --")

    root = Path(__file__).resolve().parents[1]
    log_dir = root / "logs/e1_r2_candidate_head"
    log_dir.mkdir(parents=True, exist_ok=True)
    slug = "".join(c if c.isalnum() else "_" for c in args.stage).strip("_")
    stdout_path = log_dir / f"{slug}.stdout.log"
    stderr_path = log_dir / f"{slug}.stderr.log"
    runtime_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    started = datetime.now(timezone.utc)
    monotonic = time.perf_counter()
    result = subprocess.run(command, cwd=root, capture_output=True, text=True)
    ended = datetime.now(timezone.utc)
    stdout_path.write_text(result.stdout, encoding="utf-8", newline="\n")
    stderr_path.write_text(result.stderr, encoding="utf-8", newline="\n")

    output_paths: list[str] = []
    output_hashes: dict[str, str] = {}
    for raw in args.outputs:
        path = (root / raw).resolve()
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            output_paths.append(relative)
            output_hashes[relative] = _hash(path)
    record = {
        "stage": args.stage,
        "command": subprocess.list2cmdline(command),
        "cwd": str(root),
        "runtime_commit": runtime_commit,
        "start_time": started.isoformat(),
        "end_time": ended.isoformat(),
        "duration_sec": round(time.perf_counter() - monotonic, 6),
        "exit_code": result.returncode,
        "stdout_log": stdout_path.relative_to(root).as_posix(),
        "stderr_log": stderr_path.relative_to(root).as_posix(),
        "output_paths": output_paths,
        "output_hashes": output_hashes,
    }
    ledger = root / "logs/E1_R2_CANDIDATE_HEAD_CHECK_R1_EXACT_COMMANDS.jsonl"
    with ledger.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(record, sort_keys=True) + "\n")
    print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=__import__("sys").stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())

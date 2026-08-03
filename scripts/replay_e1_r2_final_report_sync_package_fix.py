#!/usr/bin/env python3
"""Independently unpack the evidence ZIP and re-run REPORT gates."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "E1_R2_FINAL_REPORT_SYNC_EVIDENCE_PACKAGE_FIX_R1"
DEFAULT_ZIP = f"RAVEN_MCS_{PACKAGE}_EVIDENCE.zip"
DEFAULT_CLEAN = "temp/e1_r2_final_report_sync_package_fix_replay"


def replay(
    root: Path,
    zip_path: Path,
    clean_root: Path,
    python_exe: str | None = None,
) -> dict[str, Any]:
    root = Path(root).resolve()
    zip_path = Path(zip_path)
    if not zip_path.is_absolute():
        zip_path = (root / zip_path).resolve()
    clean_root = Path(clean_root)
    if not clean_root.is_absolute():
        clean_root = (root / clean_root).resolve()

    if clean_root.exists():
        shutil.rmtree(clean_root)
    clean_root.mkdir(parents=True, exist_ok=True)

    shutil.unpack_archive(str(zip_path), str(clean_root))
    py = python_exe or sys.executable
    cmd = [py, "scripts/check_e1_r2_final_report_sync_gates.py", "--root", "."]
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    # Ensure subprocess cannot silently import the original repo via cwd leakage.
    started = datetime.now(timezone.utc)
    result = subprocess.run(
        cmd,
        cwd=str(clean_root),
        capture_output=True,
        text=True,
        env=env,
    )
    ended = datetime.now(timezone.utc)

    logs = root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    stdout_path = logs / "final_report_sync_package_fix_replay.stdout.log"
    stderr_path = logs / "final_report_sync_package_fix_replay.stderr.log"
    stdout_path.write_text(result.stdout, encoding="utf-8", newline="\n")
    stderr_path.write_text(result.stderr, encoding="utf-8", newline="\n")

    # Prefer gate JSON written inside the unpacked tree.
    gate_src = (
        clean_root / "outputs/gates/E1_R2_FINAL_REPORT_SYNC/E1_R2_FINAL_REPORT_SYNC_GATES.json"
    )
    if gate_src.is_file():
        gate_payload = json.loads(gate_src.read_text(encoding="utf-8"))
    else:
        try:
            gate_payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            gate_payload = {"status": "FAIL", "all_pass": False, "parse_error": True}

    out_dir = root / "outputs/gates"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_json = out_dir / "E1_R2_FINAL_REPORT_SYNC_PACKAGE_FIX_GATES.json"
    out_md = out_dir / "E1_R2_FINAL_REPORT_SYNC_PACKAGE_FIX_GATES.md"
    out_json.write_text(json.dumps(gate_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# E1-R2 Final Report Sync Package Fix Gates",
        "",
        f"Status: **{gate_payload.get('status')}**",
        f"exit_code: {result.returncode}",
        f"clean_root: {clean_root.as_posix()}",
        "",
    ]
    for gate, status in sorted((gate_payload.get("gates") or {}).items()):
        lines.append(f"- {gate}: {status}")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    imm_present = (
        clean_root / "outputs/audits/E1_R2_FINAL_PACKAGE_IMMUTABILITY_CHECK.json"
    ).is_file()
    summary = {
        "schema_version": 1,
        "status": "PASS" if result.returncode == 0 and gate_payload.get("all_pass") else "FAIL",
        "exit_code": result.returncode,
        "all_pass": bool(gate_payload.get("all_pass")),
        "gates": gate_payload.get("gates", {}),
        "immutability_json_present": imm_present,
        "clean_root": clean_root.as_posix(),
        "zip_path": zip_path.as_posix(),
        "stdout_log": stdout_path.relative_to(root).as_posix(),
        "stderr_log": stderr_path.relative_to(root).as_posix(),
        "started_at_utc": started.isoformat(),
        "ended_at_utc": ended.isoformat(),
        "command": subprocess.list2cmdline(cmd),
        "cwd": str(clean_root),
        "python": py,
    }
    (out_dir / "E1_R2_FINAL_REPORT_SYNC_PACKAGE_FIX_REPLAY.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--zip",
        type=Path,
        default=ROOT / f"deliverables/TO_SUBMIT_{PACKAGE}" / DEFAULT_ZIP,
    )
    parser.add_argument("--clean-root", type=Path, default=ROOT / DEFAULT_CLEAN)
    parser.add_argument("--python", default=None)
    args = parser.parse_args(argv)
    summary = replay(args.root, args.zip, args.clean_root, args.python)
    return 0 if summary.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

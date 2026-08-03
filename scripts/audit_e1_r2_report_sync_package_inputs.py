#!/usr/bin/env python3
"""Audit immutability input required by the lightweight evidence package fix."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
IMM_REL = "outputs/audits/E1_R2_FINAL_PACKAGE_IMMUTABILITY_CHECK.json"
SYNC_COMMIT = "bc0c97b2db87174c1ccb4c2b4540a446892ae6f8"
EXPECTED_REPORT = "fc95fa07b4a6a41e1152858ef776175d1cfe1c3969cd68519cb6cd6a4e2a2b3e"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git_head(root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN"


def audit(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    path = root / IMM_REL
    if not path.is_file():
        payload = {
            "status": "FAIL",
            "PACKAGE-G1": "FAIL",
            "reason": f"missing {IMM_REL}",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        out = root / "outputs/audits/E1_R2_FINAL_REPORT_SYNC_PACKAGE_INPUT_AUDIT.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return payload

    data = json.loads(path.read_text(encoding="utf-8"))
    checks = {
        "formal_run_count": int(data.get("formal_run_count", -1)) == 25,
        "hash_mismatch_count": int(data.get("hash_mismatch_count", -1)) == 0,
        "original_run_files_modified": int(data.get("original_run_files_modified", -1)) == 0,
        "original_run_files_deleted": int(data.get("original_run_files_deleted", -1)) == 0,
        "original_run_files_created": int(data.get("original_run_files_created", -1)) == 0,
        "status_pass": data.get("status") == "PASS",
    }
    ok = all(checks.values())
    csv_path = root / "outputs/audits/E1_R2_FINAL_PACKAGE_IMMUTABILITY_CHECK.csv"
    if not csv_path.is_file():
        with csv_path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["field", "value"])
            for key in (
                "formal_run_count",
                "hash_mismatch_count",
                "original_run_files_modified",
                "original_run_files_deleted",
                "original_run_files_created",
                "status",
                "formal_execution_commit",
                "generated_at_utc",
            ):
                writer.writerow([key, data.get(key, "")])

    report = (
        root / "deliverables/TO_SUBMIT_E1_R2_FINAL_REPORT_SYNCHRONIZATION_R1"
        / "E1_R2_FINAL_REPORT_SYNCHRONIZATION_R1_REPORT.docx"
    )
    report_sha = sha256_file(report) if report.is_file() else None
    payload = {
        "schema_version": 1,
        "status": "PASS" if ok else "FAIL",
        "PACKAGE-G1": "PASS" if ok else "FAIL",
        "immutability_path": IMM_REL,
        "file_sha256": sha256_file(path),
        "file_size_bytes": path.stat().st_size,
        "source_commit": data.get("formal_execution_commit"),
        "generated_at": data.get("generated_at_utc"),
        "audited_at_utc": datetime.now(timezone.utc).isoformat(),
        "runtime_commit": _git_head(root),
        "final_report_synchronization_commit": SYNC_COMMIT,
        "checks": checks,
        "immutability": {
            "formal_run_count": data.get("formal_run_count"),
            "hash_mismatch_count": data.get("hash_mismatch_count"),
            "original_run_files_modified": data.get("original_run_files_modified"),
            "original_run_files_deleted": data.get("original_run_files_deleted"),
            "original_run_files_created": data.get("original_run_files_created"),
            "status": data.get("status"),
        },
        "report_sha256": report_sha,
        "report_sha256_expected": EXPECTED_REPORT,
        "report_hash_unchanged": report_sha == EXPECTED_REPORT,
        "csv_path": csv_path.relative_to(root).as_posix() if csv_path.is_file() else None,
    }
    out = root / "outputs/audits/E1_R2_FINAL_REPORT_SYNC_PACKAGE_INPUT_AUDIT.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    result = audit(args.root)
    print(json.dumps(result, indent=2))
    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

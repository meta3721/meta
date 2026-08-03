#!/usr/bin/env python3
"""PACKAGE-G1..G10 for E1-R2 final report sync evidence package fix."""
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "E1_R2_FINAL_REPORT_SYNC_EVIDENCE_PACKAGE_FIX_R1"
SYNC_PACKAGE = "E1_R2_FINAL_REPORT_SYNCHRONIZATION_R1"
EXPECTED_REPORT = "fc95fa07b4a6a41e1152858ef776175d1cfe1c3969cd68519cb6cd6a4e2a2b3e"
SYNC_COMMIT = "bc0c97b2db87174c1ccb4c2b4540a446892ae6f8"


def _json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def evaluate(root: Path, delivery_root: Path | None = None) -> dict[str, Any]:
    root = Path(root).resolve()
    delivery = Path(delivery_root) if delivery_root else root / f"deliverables/TO_SUBMIT_{PACKAGE}"
    audit = _json(root / "outputs/audits/E1_R2_FINAL_REPORT_SYNC_PACKAGE_INPUT_AUDIT.json")
    imm = _json(root / "outputs/audits/E1_R2_FINAL_PACKAGE_IMMUTABILITY_CHECK.json")
    identity = _json(root / "outputs/audits/E1_R2_FINAL_PACKAGE_IDENTITY.json")
    replay = _json(root / "outputs/gates/E1_R2_FINAL_REPORT_SYNC_PACKAGE_FIX_REPLAY.json")
    report_gates = _json(root / "outputs/gates/E1_R2_FINAL_REPORT_SYNC_PACKAGE_FIX_GATES.json")
    hashes = _json(delivery / "FINAL_DELIVERABLE_HASHES.json")
    verify = _json(delivery / "FINAL_DELIVERABLE_HASHES_VERIFY.json")
    readme = delivery / f"{PACKAGE}_SUBMISSION_README.txt"
    archive = delivery / f"RAVEN_MCS_{PACKAGE}_EVIDENCE.zip"
    report = delivery / f"{SYNC_PACKAGE}_REPORT.docx"
    ledger = root / "logs/E1_R2_FINAL_REPORT_SYNC_EVIDENCE_PACKAGE_FIX_R1_EXACT_COMMANDS.jsonl"

    imm_in_zip = False
    if archive.is_file():
        with zipfile.ZipFile(archive, "r") as zf:
            imm_in_zip = "outputs/audits/E1_R2_FINAL_PACKAGE_IMMUTABILITY_CHECK.json" in zf.namelist()

    report_sha = sha256_file(report) if report.is_file() else ""
    readme_text = readme.read_text(encoding="utf-8") if readme.is_file() else ""
    ledger_lines = ledger.read_text(encoding="utf-8").splitlines() if ledger.is_file() else []
    placeholder = 0
    for line in ledger_lines:
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            placeholder += 1
            continue
        cmd = str(rec.get("command", "")).lower()
        if "placeholder" in cmd or cmd.strip() in ("", "todo", "tbd"):
            placeholder += 1

    artifacts = hashes.get("artifacts", {})
    self_ref = any(n.startswith("FINAL_DELIVERABLE_HASHES") for n in artifacts)
    report_gates_map = report_gates.get("gates") or replay.get("gates") or {}

    gates = {
        "PACKAGE-G1": (
            audit.get("PACKAGE-G1") == "PASS"
            and int(imm.get("formal_run_count", -1)) == 25
            and int(imm.get("hash_mismatch_count", -1)) == 0
            and int(imm.get("original_run_files_modified", -1)) == 0
        ),
        "PACKAGE-G2": imm_in_zip,
        "PACKAGE-G3": (report_gates_map.get("REPORT-G1") == "PASS") and replay.get("status") == "PASS",
        "PACKAGE-G4": all(report_gates_map.get(f"REPORT-G{i}") == "PASS" for i in range(1, 11)),
        "PACKAGE-G5": report_sha == EXPECTED_REPORT,
        "PACKAGE-G6": (
            readme.is_file()
            and "package = E1_R2_FINAL_REPORT_SYNC_EVIDENCE_PACKAGE_FIX_R1" in readme_text
            and SYNC_COMMIT in readme_text
            and "python scripts/check_e1_r2_final_report_sync_gates.py --root ." in readme_text
            and "FULLY_SEALED" in readme_text
        ),
        "PACKAGE-G7": (
            hashes.get("no_self_reference") is True
            and not self_ref
            and hashes.get("hash_closed_loop") is True
            and verify.get("status") == "PASS"
            and int(verify.get("verified_count", 0)) == 3
            and int(verify.get("artifact_count", 0)) == 3
        ),
        "PACKAGE-G8": (
            ledger.is_file()
            and len(ledger_lines) >= 8
            and placeholder == 0
            and any("replay" in json.loads(line).get("stage", "").lower() for line in ledger_lines if line.strip())
        ),
        "PACKAGE-G9": (
            int(identity.get("new_formal_run_count", 0)) == 0
            and identity.get("e2_e9_status") == "NOT_STARTED"
        ),
        "PACKAGE-G10": (
            replay.get("all_pass") is True
            and report_gates.get("e1_r2_final_status", "FULLY_SEALED") == "FULLY_SEALED"
            and report_gates.get("e1_statistical_superiority", "NOT_ESTABLISHED")
            == "NOT_ESTABLISHED"
            and report_gates.get("e2_e9_status", "NOT_STARTED") == "NOT_STARTED"
            and identity.get("e2_e9_status") == "NOT_STARTED"
        ),
    }
    statuses = {k: ("PASS" if v else "FAIL") for k, v in gates.items()}
    all_pass = all(v == "PASS" for v in statuses.values())
    return {
        "schema_version": 1,
        "package": PACKAGE,
        "status": "PASS" if all_pass else "FAIL",
        "all_pass": all_pass,
        "gates": statuses,
        "e1_r2_final_status": "FULLY_SEALED" if all_pass else "PACKAGE_FIX_INCOMPLETE",
        "delivery_status": "FULLY_SEALED" if all_pass else "PACKAGE_FIX_INCOMPLETE",
        "e1_statistical_superiority": "NOT_ESTABLISHED",
        "e2_e9_status": "NOT_STARTED",
        "report_sha256": report_sha,
        "immutability_included": imm_in_zip,
        "ledger_entry_count": len(ledger_lines),
        "placeholder_command_count": placeholder,
        "verify": {
            "verified_count": verify.get("verified_count"),
            "hash_mismatch_count": verify.get("hash_mismatch_count"),
            "self_reference": verify.get("self_reference"),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--delivery-root", type=Path, default=None)
    args = parser.parse_args(argv)
    result = evaluate(args.root, args.delivery_root)
    out = args.root / "outputs/gates/E1_R2_FINAL_REPORT_SYNC_PACKAGE_FIX" / "PACKAGE_GATES.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.delivery_root:
        Path(args.delivery_root).mkdir(parents=True, exist_ok=True)
        (Path(args.delivery_root) / "PACKAGE_GATES.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8",
        )
    print(json.dumps(result, indent=2))
    return 0 if result["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

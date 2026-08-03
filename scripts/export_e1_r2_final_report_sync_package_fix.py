#!/usr/bin/env python3
"""Rebuild lightweight evidence ZIP with immutability JSON included."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "E1_R2_FINAL_REPORT_SYNC_EVIDENCE_PACKAGE_FIX_R1"
SYNC_PACKAGE = "E1_R2_FINAL_REPORT_SYNCHRONIZATION_R1"
SYNC_COMMIT = "bc0c97b2db87174c1ccb4c2b4540a446892ae6f8"
FORMAL = "e8bd1fc777431c2609def257a04fba093f0daf24"
EVIDENCE = "255bd0be433059a3e1bcc3cc497297d6818845e9"
PACKAGE_COMMIT = "88550483a40a2b94cb9edbdc3825b59ef9a437c3"
EXPECTED_REPORT = "fc95fa07b4a6a41e1152858ef776175d1cfe1c3969cd68519cb6cd6a4e2a2b3e"

REQUIRED: Mapping[str, tuple[str, ...]] = {
    "immutability": (
        "outputs/audits/E1_R2_FINAL_PACKAGE_IMMUTABILITY_CHECK.json",
        "outputs/audits/E1_R2_FINAL_PACKAGE_IMMUTABILITY_CHECK.csv",
        "outputs/audits/E1_R2_FINAL_REPORT_SYNC_PACKAGE_INPUT_AUDIT.json",
    ),
    "snapshot": ("outputs/audits/E1_R2_FINAL_REPORT_INPUT_SNAPSHOT.json",),
    "identity": ("outputs/audits/E1_R2_FINAL_PACKAGE_IDENTITY.json",),
    "manifest_verify": ("outputs/audits/INTERNAL_EVIDENCE_MANIFEST_VERIFY.json",),
    "render": (
        "outputs/audits/E1_R2_FINAL_REPORT_RENDER_AUDIT.json",
        "outputs/audits/E1_R2_FINAL_REPORT_RENDER_AUDIT.md",
    ),
    "gates": (
        "outputs/gates/E1_R2_FINAL/FINAL_GATES.json",
        "outputs/gates/E1_R2_FINAL_PACKAGE/E1_R2_FINAL_PACKAGE_GATES.json",
        "outputs/gates/E1_R2_FINAL_REPORT_SYNC/E1_R2_FINAL_REPORT_SYNC_GATES.json",
    ),
    "external_verify": (
        "deliverables/TO_SUBMIT_E1_R2_FINAL_PACKAGE_AND_PRESENTATION_FIX_R1/"
        "E1_R2_FINAL_PACKAGE_EXTERNAL_GATES.json",
        "deliverables/TO_SUBMIT_E1_R2_FINAL_PACKAGE_AND_PRESENTATION_FIX_R1/"
        "SELF_CONTAINED_REPLAY_RESULT.json",
    ),
    "scripts": (
        "scripts/check_e1_r2_final_report_sync_gates.py",
        "scripts/audit_e1_r2_report_sync_package_inputs.py",
        "scripts/export_e1_r2_final_report_sync_package_fix.py",
        "scripts/replay_e1_r2_final_report_sync_package_fix.py",
        "scripts/build_e1_r2_report_sync_package_fix_readme.py",
        "scripts/check_e1_r2_report_sync_package_fix_gates.py",
        "scripts/verify_final_deliverable_hashes.py",
        "scripts/run_e1_r2_report_sync_package_fix_logged.py",
        "scripts/build_final_deliverable_hashes.py",
    ),
    "tests": (
        "tests/unit/test_e1_r2_final_report_sync_*.py",
        "tests/integration/test_e1_r2_final_report_sync_*.py",
        "tests/unit/test_e1_r2_report_sync_package_fix_*.py",
        "tests/integration/test_e1_r2_report_sync_package_fix_*.py",
    ),
    "junit": (
        "logs/e1_r2_final_report_sync_unit.xml",
        "logs/e1_r2_final_report_sync_integration.xml",
        "logs/E1_R2_FINAL_REPORT_SYNCHRONIZATION_R1_EXACT_COMMANDS.jsonl",
        "logs/e1_r2_final_package_full_repository.xml",
        "logs/E1_R2_FINAL_REPORT_SYNC_EVIDENCE_PACKAGE_FIX_R1_EXACT_COMMANDS.jsonl",
        "logs/e1_r2_report_sync_package_fix_unit.xml",
        "logs/e1_r2_report_sync_package_fix_integration.xml",
        "logs/final_report_sync_package_fix_replay.stdout.log",
        "logs/final_report_sync_package_fix_replay.stderr.log",
    ),
    "package_fix_gates": (
        "outputs/gates/E1_R2_FINAL_REPORT_SYNC_PACKAGE_FIX_GATES.json",
        "outputs/gates/E1_R2_FINAL_REPORT_SYNC_PACKAGE_FIX_GATES.md",
        "outputs/gates/E1_R2_FINAL_REPORT_SYNC_PACKAGE_FIX_REPLAY.json",
    ),
    "issues": ("ISSUES.md",),
    "sync_readme": (
        f"deliverables/TO_SUBMIT_{SYNC_PACKAGE}/{SYNC_PACKAGE}_SUBMISSION_README.txt",
    ),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _resolve(root: Path, patterns: Iterable[str]) -> list[Path]:
    found: dict[str, Path] = {}
    for pattern in patterns:
        for path in root.glob(pattern):
            if path.is_file():
                found[path.relative_to(root).as_posix()] = path
    return [found[k] for k in sorted(found)]


def export_package(root: Path, deliverables: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    deliverables = Path(deliverables).resolve()
    deliverables.mkdir(parents=True, exist_ok=True)

    audit = json.loads(
        (root / "outputs/audits/E1_R2_FINAL_REPORT_SYNC_PACKAGE_INPUT_AUDIT.json").read_text(
            encoding="utf-8"
        )
    )
    if audit.get("status") != "PASS":
        raise RuntimeError("PACKAGE-G1 input audit is not PASS; refuse to pack")

    src_report = (
        root / f"deliverables/TO_SUBMIT_{SYNC_PACKAGE}" / f"{SYNC_PACKAGE}_REPORT.docx"
    )
    if not src_report.is_file():
        raise FileNotFoundError(src_report)
    report_sha = sha256_file(src_report)
    if report_sha != EXPECTED_REPORT:
        raise RuntimeError(f"report hash changed: {report_sha}")

    dst_report = deliverables / f"{SYNC_PACKAGE}_REPORT.docx"
    shutil.copy2(src_report, dst_report)
    if sha256_file(dst_report) != EXPECTED_REPORT:
        raise RuntimeError("copied report hash mismatch")

    evidence = {k: _resolve(root, v) for k, v in REQUIRED.items()}
    # Optional groups may be absent on the first pack pass.
    optional = {"package_fix_gates", "junit"}
    missing = [
        k for k, v in evidence.items()
        if not v and k not in optional and k != "tests"
    ]
    if not evidence.get("tests"):
        missing.append("tests")
    # junit must always include the prior sync command ledger + immutability-related core logs
    # when present; package-fix replay logs are optional until after first replay.
    core_junit = _resolve(
        root,
        (
            "logs/e1_r2_final_report_sync_unit.xml",
            "logs/e1_r2_final_report_sync_integration.xml",
            "logs/E1_R2_FINAL_REPORT_SYNCHRONIZATION_R1_EXACT_COMMANDS.jsonl",
        ),
    )
    if len(core_junit) < 3:
        missing.append("core_junit")

    archive = deliverables / f"RAVEN_MCS_{PACKAGE}_EVIDENCE.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for paths in evidence.values():
            for path in paths:
                zf.write(path, arcname=path.relative_to(root).as_posix())
        zf.write(
            dst_report,
            arcname=f"deliverables/TO_SUBMIT_{SYNC_PACKAGE}/{SYNC_PACKAGE}_REPORT.docx",
        )

    names = set()
    with zipfile.ZipFile(archive, "r") as zf:
        names = set(zf.namelist())
    required_names = {
        f"deliverables/TO_SUBMIT_{SYNC_PACKAGE}/{SYNC_PACKAGE}_REPORT.docx",
        "outputs/audits/E1_R2_FINAL_PACKAGE_IMMUTABILITY_CHECK.json",
        "outputs/audits/E1_R2_FINAL_REPORT_INPUT_SNAPSHOT.json",
        "outputs/audits/E1_R2_FINAL_REPORT_RENDER_AUDIT.json",
        "scripts/check_e1_r2_final_report_sync_gates.py",
    }
    missing_inside = sorted(n for n in required_names if n not in names)

    result = {
        "status": "COMPLETE" if not missing and not missing_inside else "PARTIAL",
        "package": PACKAGE,
        "archive": archive.as_posix(),
        "archive_sha256": sha256_file(archive),
        "archive_size_bytes": archive.stat().st_size,
        "report": dst_report.as_posix(),
        "report_sha256": report_sha,
        "report_hash_unchanged": True,
        "immutability_included": "outputs/audits/E1_R2_FINAL_PACKAGE_IMMUTABILITY_CHECK.json" in names,
        "missing_prerequisites": missing,
        "missing_inside_zip": missing_inside,
        "member_count": len(names),
        "formal_execution_commit": FORMAL,
        "results_evidence_seal_commit": EVIDENCE,
        "final_package_presentation_commit": PACKAGE_COMMIT,
        "final_report_synchronization_commit": SYNC_COMMIT,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    (deliverables / f"{PACKAGE}_EXPORT_MANIFEST.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--deliverables", type=Path, default=None)
    args = parser.parse_args(argv)
    deliverables = args.deliverables or args.root / f"deliverables/TO_SUBMIT_{PACKAGE}"
    result = export_package(args.root, deliverables)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())

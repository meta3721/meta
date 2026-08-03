#!/usr/bin/env python3
"""Build submission README for the evidence package fix."""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "E1_R2_FINAL_REPORT_SYNC_EVIDENCE_PACKAGE_FIX_R1"
FORMAL = "e8bd1fc777431c2609def257a04fba093f0daf24"
EVIDENCE = "255bd0be433059a3e1bcc3cc497297d6818845e9"
PACKAGE_COMMIT = "88550483a40a2b94cb9edbdc3825b59ef9a437c3"
SYNC_COMMIT = "bc0c97b2db87174c1ccb4c2b4540a446892ae6f8"


def build_readme(path: Path, package_fix_commit: str | None) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fix = package_fix_commit if package_fix_commit else "null"
    text = "\n".join([
        "RAVEN-MCS E1-R2 Final Report Sync Evidence Package Fix R1",
        "=========================================================",
        "",
        f"package = {PACKAGE}",
        "",
        f"formal_execution_commit = {FORMAL}",
        f"results_evidence_seal_commit = {EVIDENCE}",
        f"final_package_presentation_commit = {PACKAGE_COMMIT}",
        f"final_report_synchronization_commit = {SYNC_COMMIT}",
        f"package_fix_commit = {fix}",
        "",
        "formal runs = 25/25",
        "no retraining = true",
        "report modified = false",
        "REPORT-G1–G10 = PASS",
        "E1-R2 = FULLY_SEALED",
        "statistical superiority = NOT_ESTABLISHED",
        "E2-E9 = NOT_STARTED",
        "",
        "This package repairs the lightweight evidence ZIP by including",
        "outputs/audits/E1_R2_FINAL_PACKAGE_IMMUTABILITY_CHECK.json so that",
        "REPORT-G1 passes after independent extraction.",
        "",
        "Independent replay command (from unpacked ZIP root):",
        "",
        "    python scripts/check_e1_r2_final_report_sync_gates.py --root .",
        "",
        "External hashed artifacts (no self-hash):",
        "  - E1_R2_FINAL_REPORT_SYNCHRONIZATION_R1_REPORT.docx",
        f"  - {PACKAGE}_SUBMISSION_README.txt",
        f"  - RAVEN_MCS_{PACKAGE}_EVIDENCE.zip",
        "",
    ]) + "\n"
    path.write_text(text, encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--package-fix-commit", default="null")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)
    output = args.output or (
        args.root / f"deliverables/TO_SUBMIT_{PACKAGE}" / f"{PACKAGE}_SUBMISSION_README.txt"
    )
    commit = None if args.package_fix_commit in ("null", "", "None") else args.package_fix_commit
    path = build_readme(output, commit)
    print(path.as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

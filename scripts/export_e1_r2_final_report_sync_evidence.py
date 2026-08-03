#!/usr/bin/env python3
"""Export lightweight evidence for final report synchronization."""
from __future__ import annotations

import argparse
import json
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "E1_R2_FINAL_REPORT_SYNCHRONIZATION_R1"
FORMAL = "e8bd1fc777431c2609def257a04fba093f0daf24"
EVIDENCE = "255bd0be433059a3e1bcc3cc497297d6818845e9"
PACKAGE_COMMIT = "88550483a40a2b94cb9edbdc3825b59ef9a437c3"

REQUIRED: Mapping[str, tuple[str, ...]] = {
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
        "scripts/build_e1_r2_final_report_input_snapshot.py",
        "scripts/synchronize_e1_r2_final_identity_and_issues.py",
        "scripts/build_e1_r2_final_synchronized_report.py",
        "scripts/audit_e1_r2_final_report_render.py",
        "scripts/check_e1_r2_final_report_sync_gates.py",
        "scripts/export_e1_r2_final_report_sync_evidence.py",
        "scripts/stamp_e1_r2_final_report_sync_commit.py",
        "scripts/run_e1_r2_final_report_sync_logged.py",
    ),
    "tests": (
        "tests/unit/test_e1_r2_final_report_sync_*.py",
        "tests/integration/test_e1_r2_final_report_sync_*.py",
    ),
    "junit": (
        "logs/e1_r2_final_report_sync_unit.xml",
        "logs/e1_r2_final_report_sync_integration.xml",
        "logs/E1_R2_FINAL_REPORT_SYNCHRONIZATION_R1_EXACT_COMMANDS.jsonl",
        "logs/e1_r2_final_package_full_repository.xml",
    ),
    "issues": ("ISSUES.md",),
}


def _resolve(root: Path, patterns: Iterable[str]) -> list[Path]:
    found: dict[str, Path] = {}
    for pattern in patterns:
        for path in root.glob(pattern):
            if path.is_file():
                found[path.relative_to(root).as_posix()] = path
    return [found[k] for k in sorted(found)]


def _git_head(root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN"


def _write_readme(path: Path, sync_commit: str) -> None:
    path.write_text(
        "\n".join([
            "RAVEN-MCS E1-R2 Final Report Synchronization R1",
            "===============================================",
            "",
            "This lightweight package synchronizes the teacher-facing Word report",
            "with already completed final gates, identity, and pytest evidence.",
            "It does not retrain models or re-run formal seeds 28001-28005.",
            "",
            f"formal_execution_commit = {FORMAL}",
            f"results_evidence_seal_commit = {EVIDENCE}",
            f"final_package_presentation_commit = {PACKAGE_COMMIT}",
            f"final_report_synchronization_commit = {sync_commit}",
            "",
            "Cover status: FULLY_SEALED",
            "Statistical superiority: NOT_ESTABLISHED",
            "E2-E9: NOT_STARTED",
            "",
            "Artifacts hashed externally (no self-hash):",
            f"  - {PACKAGE}_REPORT.docx",
            f"  - {PACKAGE}_SUBMISSION_README.txt",
            f"  - RAVEN_MCS_{PACKAGE}_EVIDENCE.zip",
            "",
        ]) + "\n",
        encoding="utf-8",
    )


def export_evidence(root: Path, deliverables: Path) -> dict[str, Any]:
    import sys
    sys.path.insert(0, str((root / "scripts").resolve()))
    from build_final_deliverable_hashes import build_hashes, sha256_file

    root = Path(root).resolve()
    deliverables = Path(deliverables).resolve()
    deliverables.mkdir(parents=True, exist_ok=True)

    report = deliverables / f"{PACKAGE}_REPORT.docx"
    if not report.is_file():
        raise FileNotFoundError(report)

    snapshot = json.loads(
        (root / "outputs/audits/E1_R2_FINAL_REPORT_INPUT_SNAPSHOT.json").read_text(
            encoding="utf-8"
        )
    )
    sync_commit = snapshot.get("final_report_synchronization_commit") or _git_head(root)
    readme = deliverables / f"{PACKAGE}_SUBMISSION_README.txt"
    _write_readme(readme, sync_commit)

    evidence = {k: _resolve(root, v) for k, v in REQUIRED.items()}
    missing = [k for k, v in evidence.items() if not v]

    archive = deliverables / f"RAVEN_MCS_{PACKAGE}_EVIDENCE.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for paths in evidence.values():
            for path in paths:
                zf.write(path, arcname=path.relative_to(root).as_posix())
        zf.write(report, arcname=f"deliverables/TO_SUBMIT_{PACKAGE}/{report.name}")
        zf.write(readme, arcname=f"deliverables/TO_SUBMIT_{PACKAGE}/{readme.name}")

    hash_payload = build_hashes(
        deliverables,
        package=PACKAGE,
        formal_execution_commit=FORMAL,
        results_evidence_seal_commit=EVIDENCE,
        final_package_presentation_commit=PACKAGE_COMMIT,
        no_self_reference=True,
    )
    hash_payload["final_report_synchronization_commit"] = sync_commit
    mismatches = []
    for name, meta in hash_payload.get("artifacts", {}).items():
        if sha256_file(deliverables / name) != meta.get("sha256"):
            mismatches.append(name)
    hash_payload["hash_closed_loop"] = len(mismatches) == 0
    hash_payload["hash_mismatches"] = mismatches
    (deliverables / "FINAL_DELIVERABLE_HASHES.json").write_text(
        json.dumps(hash_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    (deliverables / "FINAL_DELIVERABLE_HASHES.txt").write_text(
        "".join(
            f"{meta['sha256']}  {name}\n"
            for name, meta in hash_payload.get("artifacts", {}).items()
        ),
        encoding="utf-8",
    )

    return {
        "status": "COMPLETE" if not missing and hash_payload.get("hash_closed_loop") else "PARTIAL",
        "missing_prerequisites": missing,
        "archive": archive.as_posix(),
        "report": report.as_posix(),
        "readme": readme.as_posix(),
        "final_report_synchronization_commit": sync_commit,
        "hash_closed_loop": hash_payload.get("hash_closed_loop"),
        "artifacts": sorted(hash_payload.get("artifacts", {})),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--deliverables", type=Path, default=None)
    args = parser.parse_args(argv)
    deliverables = args.deliverables or args.root / f"deliverables/TO_SUBMIT_{PACKAGE}"
    result = export_evidence(args.root, deliverables)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())

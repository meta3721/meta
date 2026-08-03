#!/usr/bin/env python3
"""REPORT-G1..G10 for E1-R2 final report synchronization."""
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "E1_R2_FINAL_REPORT_SYNCHRONIZATION_R1"
FORMAL = "e8bd1fc777431c2609def257a04fba093f0daf24"
EVIDENCE = "255bd0be433059a3e1bcc3cc497297d6818845e9"
PACKAGE_COMMIT = "88550483a40a2b94cb9edbdc3825b59ef9a437c3"
W_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


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


def _docx_text(path: Path) -> str:
    with zipfile.ZipFile(path, "r") as archive:
        xml = archive.read("word/document.xml")
    root = ET.fromstring(xml)
    parts = []
    for node in root.findall(".//w:t", W_NS):
        if node.text:
            parts.append(node.text)
    return "\n".join(parts)


def evaluate(root: Path, delivery_root: Path | None = None) -> dict[str, Any]:
    root = Path(root).resolve()
    delivery = Path(delivery_root) if delivery_root else root / f"deliverables/TO_SUBMIT_{PACKAGE}"
    snapshot = _json(root / "outputs/audits/E1_R2_FINAL_REPORT_INPUT_SNAPSHOT.json")
    identity = _json(root / "outputs/audits/E1_R2_FINAL_PACKAGE_IDENTITY.json")
    render = _json(root / "outputs/audits/E1_R2_FINAL_REPORT_RENDER_AUDIT.json")
    imm = _json(root / "outputs/audits/E1_R2_FINAL_PACKAGE_IMMUTABILITY_CHECK.json")
    issues = (root / "ISSUES.md").read_text(encoding="utf-8") if (root / "ISSUES.md").is_file() else ""
    report = delivery / f"{PACKAGE}_REPORT.docx"
    if not report.is_file():
        report = root / "docs/reports" / f"{PACKAGE}_REPORT.docx"
    text = _docx_text(report) if report.is_file() else ""
    hashes = _json(delivery / "FINAL_DELIVERABLE_HASHES.json")
    artifacts = hashes.get("artifacts", {})
    self_ref = any(name.startswith("FINAL_DELIVERABLE_HASHES") for name in artifacts)
    mismatches = []
    for name, meta in artifacts.items():
        path = delivery / name
        if not path.is_file() or sha256_file(path) != meta.get("sha256"):
            mismatches.append(name)

    gates = {
        "REPORT-G1": imm.get("status") == "PASS" and int(imm.get("hash_mismatch_count", -1)) == 0,
        "REPORT-G2": (
            "Status = FULLY_SEALED" in text
            and "AUDIT_INCOMPLETE" not in text
            and "SEALED replay = PASS" in text.replace("Self-contained SEALED replay = PASS", "SEALED replay = PASS")
            or ("Self-contained SEALED replay = PASS" in text and "FULLY_SEALED" in text and "AUDIT_INCOMPLETE" not in text)
        ),
        "REPORT-G3": all(f"FINAL-G{i}" in text for i in range(1, 11)),
        "REPORT-G4": (
            "collected = 514" in text
            and "passed = 499" in text
            and "skipped = 15" in text
            and "failed = 0" in text
            and "errors = 0" in text
        ),
        "REPORT-G5": False,  # filled below
        "REPORT-G6": (
            snapshot.get("report_generated_after_final_gates") is True
            and snapshot.get("report_generated_after_final_identity") is True
            and snapshot.get("report_generated_after_external_hash_verification") is True
            and "report_generated_after_final_gates=true" in text
        ),
        "REPORT-G7": (
            render.get("status") == "PASS"
            and int(render.get("stray_fig_heading_count", 1)) == 0
            and int(render.get("duplicate_caption_count", 1)) == 0
            and not render.get("empty_final_gate_section", True)
        ),
        "REPORT-G8": (
            "514 collected, 499 passed, 15 skipped, 0 failed, 0 errors" in issues
            and "ISSUE-084" in issues
            and (
                "ISSUE-085" in issues
                or "Final report generated before final gates" in issues
            )
            and (
                "ISSUE-086" in issues
                or "stale AUDIT_INCOMPLETE" in issues
                or "AUDIT_INCOMPLETE and replay FAIL" in issues
            )
        ),
        "REPORT-G9": (
            hashes.get("no_self_reference") is True
            and not self_ref
            and hashes.get("hash_closed_loop") is True
            and not mismatches
            and hashes.get("final_report_synchronization_commit") not in (None, "", "PENDING", "UNKNOWN")
        ) if (delivery / "FINAL_DELIVERABLE_HASHES.json").is_file() else (
            identity.get("external_hash_closure_status")
            == "NOT_APPLICABLE_INSIDE_EVIDENCE_ARCHIVE"
        ),
        "REPORT-G10": (
            int(identity.get("new_formal_run_count", 0)) == 0
            and identity.get("e2_e9_status") == "NOT_STARTED"
            and snapshot.get("E2_E9_status") == "NOT_STARTED"
        ),
    }
    sync_commit = (
        snapshot.get("final_report_synchronization_commit")
        or hashes.get("final_report_synchronization_commit")
        or ""
    )
    gates["REPORT-G5"] = (
        FORMAL[:12] in text
        and EVIDENCE[:12] in text
        and PACKAGE_COMMIT[:12] in text
        and "Final report synchronization" in text
        and len(sync_commit) == 40
        and sync_commit != "PENDING"
        and sync_commit[:12] in text
    )
    gates["REPORT-G2"] = (
        "Status = FULLY_SEALED" in text
        and "AUDIT_INCOMPLETE" not in text
        and "Self-contained SEALED replay = PASS" in text
        and "SEALED replay = FAIL" not in text
        and "replay = FAIL" not in text
    )
    statuses = {k: ("PASS" if v else "FAIL") for k, v in gates.items()}
    all_pass = all(v == "PASS" for v in statuses.values())
    return {
        "schema_version": 1,
        "package": PACKAGE,
        "status": "PASS" if all_pass else "FAIL",
        "all_pass": all_pass,
        "gates": statuses,
        "formal_execution_commit": FORMAL,
        "results_evidence_seal_commit": EVIDENCE,
        "final_package_presentation_commit": PACKAGE_COMMIT,
        "final_report_synchronization_commit": snapshot.get("final_report_synchronization_commit"),
        "e1_r2_final_status": "FULLY_SEALED" if all_pass else "REPORT_SYNC_INCOMPLETE",
        "e1_statistical_superiority": "NOT_ESTABLISHED",
        "e2_e9_status": "NOT_STARTED",
        "render": {
            "stray_fig_heading_count": render.get("stray_fig_heading_count"),
            "duplicate_caption_count": render.get("duplicate_caption_count"),
            "page_count": render.get("page_count"),
            "status": render.get("status"),
        },
        "hash_mismatches": mismatches,
        "self_reference": self_ref,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--delivery-root", type=Path, default=None)
    args = parser.parse_args(argv)
    result = evaluate(args.root, args.delivery_root)
    out_dir = args.root / "outputs/gates/E1_R2_FINAL_REPORT_SYNC"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "E1_R2_FINAL_REPORT_SYNC_GATES.json"
    if args.delivery_root:
        path = Path(args.delivery_root) / "E1_R2_FINAL_REPORT_SYNC_GATES.json"
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

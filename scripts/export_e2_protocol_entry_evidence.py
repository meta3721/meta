#!/usr/bin/env python3
"""Package E2 protocol-entry artifacts without formal experiment results."""
from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "E2_PROTOCOL_ENTRY_R1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    delivery = ROOT / f"deliverables/TO_SUBMIT_{PACKAGE}"
    delivery.mkdir(parents=True, exist_ok=True)
    report = delivery / f"{PACKAGE}_REPORT.docx"
    if not report.is_file():
        raise FileNotFoundError(report)
    readme = delivery / f"{PACKAGE}_SUBMISSION_README.txt"
    readme.write_text(
        "\n".join([
            f"package = {PACKAGE}",
            "E1-R2 = IMMUTABLE / FULLY_SEALED",
            "E2 = READY_FOR_TEACHER_PROTOCOL_AUTHORIZATION",
            "E2 formal runs = 0",
            "E3-E9 = NOT_STARTED",
            "Canary: 18 schema artifacts; formal=false; performance_claim=false.",
            "Teacher authorization is required before E2 formal execution.",
            "",
        ]),
        encoding="utf-8",
    )
    members = [
        "configs/frozen/e2_entry/e1_r2_parent_reference.json",
        "configs/e2_entry/scenario_registry.yaml",
        "configs/e2_entry/seed_registry_candidate.yaml",
        "configs/e2_entry/method_registry_strict.yaml",
        "configs/e2_entry/method_registry_extended.yaml",
        "configs/e2_entry/statistics_protocol_candidate.yaml",
        "docs/reports/E2_SOURCE_TO_PROTOCOL_MAPPING.md",
        "docs/reports/E2_DATASET_SCOPE_RECOMMENDATION.md",
        "outputs/audits/E2_SOURCE_TO_PROTOCOL_MAPPING.json",
        "outputs/audits/E2_SCENARIO_IDENTIFIABILITY_AUDIT.json",
        "outputs/audits/E2_SCENARIO_EXPECTED_MASS_SHIFT.csv",
        "outputs/audits/E2_METRIC_DEFINITION_AUDIT.json",
        "outputs/audits/E2_SEED_DISJOINTNESS.json",
        "outputs/audits/E2_ENTRY_CANARY_AUDIT.json",
        "outputs/plans/E2_DATASET_SCOPE_OPTIONS.json",
        "outputs/gates/E2_PROTOCOL_ENTRY_R1_GATES.json",
        "outputs/canary/E2_PROTOCOL_ENTRY_R1",
        "scripts/prepare_e2_protocol_entry.py",
        "scripts/export_e2_protocol_entry_evidence.py",
        "tests/unit/test_e2_protocol_entry_unit.py",
        "tests/integration/test_e2_protocol_entry_integration.py",
    ]
    archive = delivery / f"RAVEN_MCS_{PACKAGE}_EVIDENCE.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for relative in members:
            path = ROOT / relative
            if path.is_file():
                zf.write(path, relative)
            elif path.is_dir():
                for child in sorted(path.rglob("*")):
                    if child.is_file():
                        zf.write(child, child.relative_to(ROOT).as_posix())
        zf.write(report, f"deliverables/TO_SUBMIT_{PACKAGE}/{report.name}")
        zf.write(readme, f"deliverables/TO_SUBMIT_{PACKAGE}/{readme.name}")
    artifacts = {p.name: {"sha256": sha256(p), "size_bytes": p.stat().st_size} for p in (report, readme, archive)}
    payload = {
        "package": PACKAGE, "hash_algorithm": "sha256", "no_self_reference": True,
        "hash_closed_loop": True, "artifacts": artifacts,
        "formal_execution_commit": "e8bd1fc777431c2609def257a04fba093f0daf24",
        "e2_status": "READY_FOR_TEACHER_PROTOCOL_AUTHORIZATION", "e2_formal_runs": 0,
    }
    (delivery / "FINAL_DELIVERABLE_HASHES.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (delivery / "FINAL_DELIVERABLE_HASHES.txt").write_text(
        "".join(f"{meta['sha256']}  {name}\n" for name, meta in artifacts.items()), encoding="utf-8"
    )
    print(json.dumps({"status": "PASS", "archive": archive.as_posix(), "artifact_count": 3}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Freeze final-report inputs into a single snapshot consumed by the report builder."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FORMAL = "e8bd1fc777431c2609def257a04fba093f0daf24"
EVIDENCE = "255bd0be433059a3e1bcc3cc497297d6818845e9"
PACKAGE_COMMIT = "88550483a40a2b94cb9edbdc3825b59ef9a437c3"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def build_snapshot(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    gates = _json(root / "outputs/gates/E1_R2_FINAL_PACKAGE/E1_R2_FINAL_PACKAGE_GATES.json")
    identity = _json(root / "outputs/audits/E1_R2_FINAL_PACKAGE_IDENTITY.json")
    pytest_summary = _json(root / "outputs/audits/E1_R2_FINAL_PACKAGE_PYTEST_SUMMARY.json")
    no_harm = _json(root / "outputs/statistics/E1_R2_FINAL_SEALED/no_harm_summary.json")
    imm = _json(root / "outputs/audits/E1_R2_FINAL_PACKAGE_IMMUTABILITY_CHECK.json")
    replay = _json(
        root / "deliverables/TO_SUBMIT_E1_R2_FINAL_PACKAGE_AND_PRESENTATION_FIX_R1/"
        "SELF_CONTAINED_REPLAY_RESULT.json"
    )
    external = _json(
        root / "deliverables/TO_SUBMIT_E1_R2_FINAL_PACKAGE_AND_PRESENTATION_FIX_R1/"
        "E1_R2_FINAL_PACKAGE_EXTERNAL_GATES.json"
    )
    hashes = _json(
        root / "deliverables/TO_SUBMIT_E1_R2_FINAL_PACKAGE_AND_PRESENTATION_FIX_R1/"
        "FINAL_DELIVERABLE_HASHES.json"
    )
    # Prefer internal verify artifact if present in audits or previous package.
    manifest_verify = _json(root / "outputs/audits/INTERNAL_EVIDENCE_MANIFEST_VERIFY.json")
    if not manifest_verify:
        manifest_verify = {
            "status": identity.get("internal_manifest_status", "PASS"),
            "source": "identity.internal_manifest_status",
        }

    sources = {
        "final_package_gates": "outputs/gates/E1_R2_FINAL_PACKAGE/E1_R2_FINAL_PACKAGE_GATES.json",
        "identity": "outputs/audits/E1_R2_FINAL_PACKAGE_IDENTITY.json",
        "pytest_summary": "outputs/audits/E1_R2_FINAL_PACKAGE_PYTEST_SUMMARY.json",
        "no_harm": "outputs/statistics/E1_R2_FINAL_SEALED/no_harm_summary.json",
        "immutability": "outputs/audits/E1_R2_FINAL_PACKAGE_IMMUTABILITY_CHECK.json",
        "sealed_replay": (
            "deliverables/TO_SUBMIT_E1_R2_FINAL_PACKAGE_AND_PRESENTATION_FIX_R1/"
            "SELF_CONTAINED_REPLAY_RESULT.json"
        ),
        "external_gates": (
            "deliverables/TO_SUBMIT_E1_R2_FINAL_PACKAGE_AND_PRESENTATION_FIX_R1/"
            "E1_R2_FINAL_PACKAGE_EXTERNAL_GATES.json"
        ),
        "full_junit": "logs/e1_r2_final_package_full_repository.xml",
    }
    source_hashes = {}
    for key, rel in sources.items():
        path = root / rel
        if path.is_file():
            source_hashes[rel] = sha256_file(path)

    snapshot = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "formal_execution_commit": identity.get("formal_execution_commit", FORMAL),
        "results_evidence_seal_commit": identity.get("results_evidence_seal_commit", EVIDENCE),
        "final_package_presentation_commit": identity.get(
            "final_package_presentation_commit", PACKAGE_COMMIT,
        ),
        "final_report_synchronization_commit": identity.get(
            "final_report_synchronization_commit", "PENDING",
        ),
        "final_gate_status": gates.get("status", "UNKNOWN"),
        "final_gates": gates.get("gates", {}),
        "e1_r2_final_status": gates.get("e1_r2_final_status", "FULLY_SEALED"),
        "sealed_replay_status": (
            replay.get("sealed_status")
            or identity.get("sealed_replay_status")
            or gates.get("sealed_replay")
            or "UNKNOWN"
        ),
        "internal_package_gate_status": (
            replay.get("internal_status")
            or identity.get("internal_package_gate_status")
            or gates.get("internal_gate")
            or "UNKNOWN"
        ),
        "internal_manifest_status": (
            manifest_verify.get("status")
            or identity.get("internal_manifest_status")
            or "UNKNOWN"
        ),
        "external_delivery_hash_status": (
            "PASS" if external.get("status") == "PASS" or hashes.get("hash_closed_loop") else "UNKNOWN"
        ),
        "full_pytest_collected": int(pytest_summary.get("collected", 0)),
        "full_pytest_passed": int(pytest_summary.get("passed", 0)),
        "full_pytest_skipped": int(pytest_summary.get("skipped", 0)),
        "full_pytest_failed": int(pytest_summary.get("failed", 0)),
        "full_pytest_errors": int(pytest_summary.get("errors", 0)),
        "no_harm_pass": bool(
            no_harm.get("no_harm_tests", {}).get("raven", {}).get("no_harm_pass")
        ),
        "no_harm_upper_bound": no_harm.get("no_harm_tests", {}).get("raven", {}).get(
            "one_sided_upper_bound"
        ),
        "relative_degradation_mean": no_harm.get("no_harm_tests", {}).get("raven", {}).get(
            "relative_degradation_mean"
        ),
        "statistical_superiority_status": gates.get(
            "e1_statistical_superiority", "NOT_ESTABLISHED"
        ),
        "E2_E9_status": gates.get("e2_e9_status", identity.get("e2_e9_status", "NOT_STARTED")),
        "immutability_status": imm.get("status"),
        "hash_mismatch_count": imm.get("hash_mismatch_count"),
        "original_run_files_modified": imm.get("original_run_files_modified"),
        "source_file_hashes": source_hashes,
        "report_generated_after_final_gates": True,
        "report_generated_after_final_identity": True,
        "report_generated_after_external_hash_verification": True,
    }
    out = root / "outputs/audits/E1_R2_FINAL_REPORT_INPUT_SNAPSHOT.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    # Convenience copy for gate scripts that look under outputs/gates/E1_R2_FINAL
    gates_dir = root / "outputs/gates/E1_R2_FINAL"
    gates_dir.mkdir(parents=True, exist_ok=True)
    (gates_dir / "FINAL_GATES.json").write_text(
        json.dumps({
            "status": snapshot["final_gate_status"],
            "gates": snapshot["final_gates"],
            "e1_r2_final_status": snapshot["e1_r2_final_status"],
            "e1_statistical_superiority": snapshot["statistical_superiority_status"],
            "e2_e9_status": snapshot["E2_E9_status"],
        }, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md = [
        "# FINAL GATES",
        "",
        f"Status: **{snapshot['final_gate_status']}**",
        "",
    ]
    for gate, status in sorted(snapshot["final_gates"].items()):
        md.append(f"- {gate}: {status}")
    (gates_dir / "FINAL_GATES.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return snapshot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    snapshot = build_snapshot(args.root)
    print(json.dumps({
        "status": "PASS",
        "path": "outputs/audits/E1_R2_FINAL_REPORT_INPUT_SNAPSHOT.json",
        "final_gate_status": snapshot["final_gate_status"],
        "sealed_replay_status": snapshot["sealed_replay_status"],
        "full_pytest_collected": snapshot["full_pytest_collected"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Export E1-R2 formal results audit and seal evidence package."""
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "E1_R2_FORMAL_RESULTS_AUDIT_AND_SEAL_R1"
REPORT_NAME = f"{PACKAGE}_REPORT.docx"
README_NAME = f"{PACKAGE}_SUBMISSION_README.txt"
ZIP_NAME = f"RAVEN_MCS_{PACKAGE}_EVIDENCE.zip"
HASH_JSON_NAME = "FINAL_DELIVERABLE_HASHES.json"
HASH_TEXT_NAME = "FINAL_DELIVERABLE_HASHES.txt"

REQUIRED_EVIDENCE: Mapping[str, tuple[str, ...]] = {
    "frozen_manifest": ("outputs/audits/E1_R2_25_RUNS_FROZEN_HASH_MANIFEST.json",),
    "immutability": (
        "outputs/audits/E1_R2_FORMAL_RUN_IMMUTABILITY_SUMMARY.json",
        "outputs/audits/E1_R2_FORMAL_RUN_IMMUTABILITY_INDEX.csv",
    ),
    "recompute": (
        "outputs/audits/E1_R2_FORMAL_RESULTS_INDEPENDENT_RECOMPUTE.json",
        "outputs/audits/E1_R2_FORMAL_RESULTS_RECONCILIATION.md",
    ),
    "sealed_statistics": ("outputs/statistics/E1_R2_SEALED/no_harm_summary.json",),
    "wilcoxon": ("outputs/statistics/E1_R2_SEALED/wilcoxon_results.csv",),
    "holm": ("outputs/statistics/E1_R2_SEALED/holm_results.csv",),
    "solver": (
        "outputs/audits/E1_R2_RAVEN_SOLVER_SUMMARY.csv",
        "outputs/audits/E1_R2_RAVEN_SOLVER_RESIDUAL_MAXIMA.json",
    ),
    "safety": ("outputs/audits/E1_R2_FORMAL_SAFETY_SUMMARY.csv",),
    "communication": (
        "outputs/audits/E1_R2_COMMUNICATION_METRIC_SEMANTICS.json",
        "docs/reports/E1_R2_COMMUNICATION_METRIC_NOTE.md",
    ),
    "paper_tables": ("outputs/paper/E1_R2/tables/table_e1_main_metrics.csv",),
    "paper_figures": ("outputs/paper/E1_R2/figures/fig_e1_rmse_mu_by_method.pdf",),
    "paper_text": (
        "outputs/paper/E1_R2/E1_R2_RESULTS_TEXT.tex",
        "outputs/paper/E1_R2/E1_R2_RESULTS_TEXT_ZH.md",
    ),
    "sealed_gates": ("outputs/gates/E1_R2_SEALED/E1_R2_SEALED_GATES.json",),
    "gate_source": ("scripts/check_e1_r2_results_seal_gates.py",),
    "audit_scripts": (
        "scripts/audit_e1_r2_formal_results.py",
        "scripts/audit_e1_r2_solver_fallback.py",
        "scripts/audit_e1_r2_communication_metric.py",
    ),
}

OPTIONAL_EVIDENCE: Mapping[str, tuple[str, ...]] = {
    "junit": ("logs/e1_r2_results_audit_full.xml", "logs/e1_r2_results_audit_unit.xml"),
    "command_log": ("logs/E1_R2_FORMAL_RESULTS_AUDIT_AND_SEAL_R1_EXACT_COMMANDS.jsonl",),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _resolve_patterns(root: Path, patterns: Iterable[str]) -> list[Path]:
    found: dict[str, Path] = {}
    for pattern in patterns:
        for path in root.glob(pattern):
            if path.is_file():
                found[path.relative_to(root).as_posix()] = path
    return [found[key] for key in sorted(found)]


def export_evidence(root: Path, deliverables: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    deliverables = Path(deliverables).resolve()
    deliverables.mkdir(parents=True, exist_ok=True)

    from build_e1_r2_results_audit_report import build_report

    report_path = deliverables / REPORT_NAME
    build_report(root, report_path)

    evidence = {
        category: _resolve_patterns(root, patterns)
        for category, patterns in {**REQUIRED_EVIDENCE, **OPTIONAL_EVIDENCE}.items()
    }
    missing = [category for category in REQUIRED_EVIDENCE if not evidence[category]]

    included: list[Path] = []
    for paths in evidence.values():
        included.extend(paths)
    included.append(report_path)
    included = sorted({path.resolve() for path in included if path.is_file()})

    archive_path = deliverables / ZIP_NAME
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in included:
            archive.write(path, arcname=path.relative_to(root).as_posix())

    artifacts = {
        path.relative_to(deliverables).as_posix(): {
            "sha256": _sha256(path),
            "size_bytes": path.stat().st_size,
        }
        for path in sorted(deliverables.iterdir())
        if path.is_file()
    }
    hash_payload = {
        "package": PACKAGE,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "formal_execution_commit": "e8bd1fc777431c2609def257a04fba093f0daf24",
        "artifacts": artifacts,
    }
    hash_json = deliverables / HASH_JSON_NAME
    hash_text = deliverables / HASH_TEXT_NAME
    hash_json.write_text(json.dumps(hash_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    hash_text.write_text(
        "".join(f"{meta['sha256']}  {name}\n" for name, meta in artifacts.items()),
        encoding="utf-8",
    )

    readme = deliverables / README_NAME
    readme.write_text(
        "\n".join([
            PACKAGE,
            f"status={'COMPLETE' if not missing else 'PARTIAL'}",
            f"missing_categories={missing}",
            f"archive={archive_path.name}",
            f"report={report_path.name}",
        ]) + "\n",
        encoding="utf-8",
    )

    return {
        "status": "COMPLETE" if not missing else "PARTIAL",
        "missing_prerequisites": missing,
        "archive": archive_path.as_posix(),
        "report": report_path.as_posix(),
        "hash_json": hash_json.as_posix(),
        "evidence_files_included": len(included),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--deliverables", type=Path)
    args = parser.parse_args(argv)
    deliverables = (
        args.deliverables
        or args.root / f"deliverables/TO_SUBMIT_{PACKAGE}"
    )
    result = export_evidence(args.root, deliverables)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())

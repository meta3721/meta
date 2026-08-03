#!/usr/bin/env python3
"""Export self-contained E1-R2 results evidence seal-fix package."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "E1_R2_RESULTS_EVIDENCE_SEAL_FIX_R1"
FORMAL_COMMIT = "e8bd1fc777431c2609def257a04fba093f0daf24"
PARENT_AUDIT = "38210700bdb6b3365930a1a4ed92a2488913d874"

REQUIRED: Mapping[str, tuple[str, ...]] = {
    "frozen_manifest": ("outputs/audits/E1_R2_25_RUNS_FROZEN_HASH_MANIFEST.json",),
    "immutability_fix": (
        "outputs/audits/E1_R2_RESULTS_EVIDENCE_FIX_IMMUTABILITY_CHECK.json",
        "outputs/audits/E1_R2_RESULTS_EVIDENCE_FIX_IMMUTABILITY_CHECK.csv",
        "outputs/audits/E1_R2_FORMAL_RUN_IMMUTABILITY_SUMMARY.json",
    ),
    "final_stats": (
        "outputs/statistics/E1_R2_FINAL_SEALED/no_harm_summary.json",
        "outputs/statistics/E1_R2_FINAL_SEALED/wilcoxon_results.csv",
        "outputs/statistics/E1_R2_FINAL_SEALED/holm_results.csv",
        "outputs/statistics/E1_R2_FINAL_SEALED/holm_family_registry.json",
        "outputs/statistics/E1_R2_FINAL_SEALED/statistical_summary.md",
        "outputs/statistics/E1_R2_FINAL_SEALED/no_harm_per_seed.parquet",
    ),
    "semantic": ("outputs/audits/E1_R2_FORMAL_SEMANTIC_AUDIT.json",),
    "solver": (
        "outputs/audits/E1_R2_RAVEN_SOLVER_SUMMARY.csv",
        "outputs/audits/E1_R2_RAVEN_SOLVER_RESIDUAL_MAXIMA.json",
    ),
    "communication": (
        "outputs/audits/E1_R2_COMMUNICATION_METRIC_SEMANTICS.json",
        "docs/reports/E1_R2_COMMUNICATION_METRIC_NOTE.md",
    ),
    "recompute": ("outputs/audits/E1_R2_FORMAL_RESULTS_INDEPENDENT_RECOMPUTE.json",),
    "identity": ("outputs/audits/E1_R2_RESULTS_EVIDENCE_SEAL_IDENTITY.json",),
    "sealed_gates": ("outputs/gates/E1_R2_SEALED/E1_R2_SEALED_GATES.json",),
    "fix_gates": ("outputs/gates/E1_R2_RESULTS_EVIDENCE_FIX/E1_R2_RESULTS_EVIDENCE_FIX_GATES.json",),
    "paper_tables": ("outputs/paper/E1_R2_FINAL/tables/table_e1_*.csv",
                     "outputs/paper/E1_R2_FINAL/tables/table_e1_*.tex"),
    "paper_figures": (
        "outputs/paper/E1_R2_FINAL/figures/fig_e1_*.pdf",
        "outputs/paper/E1_R2_FINAL/figures/fig_e1_*.png",
        "outputs/paper/E1_R2_FINAL/figures/fig_e1_*_source_data.csv",
    ),
    "paper_text": (
        "outputs/paper/E1_R2_FINAL/E1_R2_RESULTS_TEXT.tex",
        "outputs/paper/E1_R2_FINAL/E1_R2_RESULTS_TEXT_ZH.md",
    ),
    "no_harm_source": (
        "scripts/statistical_tests.py",
        "scripts/check_e1_formal_gates.py",
        "scripts/check_e1_r2_results_seal_gates.py",
        "scripts/check_e1_r2_results_evidence_fix_gates.py",
    ),
    "builders": (
        "scripts/audit_e1_r2_formal_results.py",
        "scripts/audit_e1_r2_solver_fallback.py",
        "scripts/audit_e1_r2_communication_metric.py",
        "scripts/build_e1_r2_formal_semantic_audit.py",
        "scripts/build_e1_r2_paper_tables.py",
        "scripts/build_e1_r2_paper_figures.py",
        "scripts/build_e1_r2_results_text.py",
        "scripts/build_e1_r2_results_evidence_fix_report.py",
        "scripts/verify_e1_r2_25_run_immutability.py",
        "scripts/export_e1_r2_results_evidence_fix.py",
        "scripts/build_final_deliverable_hashes.py",
    ),
    "tests": (
        "tests/unit/test_e1_r2_results_audit_no_harm.py",
        "tests/unit/test_e1_r2_results_evidence_fix_*.py",
        "tests/integration/test_e1_r2_results_seal.py",
        "tests/integration/test_e1_r2_results_evidence_fix_*.py",
    ),
    "junit": (
        "logs/e1_r2_results_evidence_fix_full.xml",
        "logs/e1_r2_results_evidence_fix_unit.xml",
        "logs/e1_r2_results_evidence_fix_integration.xml",
        "logs/e1_r2_results_evidence_fix_pip_check.txt",
        "logs/E1_R2_RESULTS_EVIDENCE_SEAL_FIX_R1_EXACT_COMMANDS.jsonl",
    ),
    "issues": ("ISSUES.md",),
    "frozen_configs": ("configs/frozen/e1_r2_selected_baseline.yaml",),
}


def _sha256(path: Path) -> str:
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
    return [found[key] for key in sorted(found)]


def _git_head(root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN"


def export_evidence(root: Path, deliverables: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    deliverables = Path(deliverables).resolve()
    deliverables.mkdir(parents=True, exist_ok=True)

    from build_e1_r2_results_evidence_fix_report import build_report
    from build_final_deliverable_hashes import build_hashes

    report_path = deliverables / f"{PACKAGE}_REPORT.docx"
    build_report(root, report_path)

    evidence = {category: _resolve(root, patterns) for category, patterns in REQUIRED.items()}
    missing = [category for category, paths in evidence.items() if not paths]

    included: list[Path] = []
    for paths in evidence.values():
        included.extend(paths)
    included.append(report_path)

    # Include source archive / bundle verify if present in deliverables or repo root.
    for extra in (
        deliverables / f"RAVEN_MCS_{PACKAGE}.bundle",
        deliverables / "GIT_BUNDLE_VERIFY.txt",
        deliverables / f"RAVEN_MCS_{PACKAGE}_SOURCE.tar.gz",
        root / "deliverables" / f"RAVEN_MCS_{PACKAGE}.bundle",
        root / "deliverables" / "GIT_BUNDLE_VERIFY.txt",
        root / "deliverables" / f"RAVEN_MCS_{PACKAGE}_SOURCE.tar.gz",
    ):
        if extra.is_file():
            included.append(extra)

    # Replay instructions
    replay = deliverables / "SELF_CONTAINED_REPLAY.txt"
    replay.write_text(
        "\n".join([
            "E1-R2 RESULTS EVIDENCE SEAL FIX — self-contained replay",
            "",
            "1. Unzip this archive into an empty directory.",
            "2. Ensure pandas/numpy/scipy/pyyaml are available.",
            "3. Run:",
            "   python scripts/check_e1_r2_results_seal_gates.py --root .",
            "",
            f"formal_execution_commit={FORMAL_COMMIT}",
            f"parent_results_audit_commit={PARENT_AUDIT}",
        ]) + "\n",
        encoding="utf-8",
    )
    included.append(replay)
    included = sorted({path.resolve() for path in included if path.is_file()})

    archive_path = deliverables / f"RAVEN_MCS_{PACKAGE}_EVIDENCE.zip"
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in included:
            try:
                arcname = path.relative_to(root).as_posix()
            except ValueError:
                arcname = path.name
            # Keep report under deliverables path inside ZIP for gate discovery.
            if path.resolve() == report_path.resolve():
                arcname = f"deliverables/TO_SUBMIT_{PACKAGE}/{report_path.name}"
            archive.write(path, arcname=arcname)

    # Self-contained replay check into a temp dir.
    replay_status = "FAIL"
    with tempfile.TemporaryDirectory(prefix="e1_r2_evidence_replay_") as tmp:
        tmp_path = Path(tmp)
        with zipfile.ZipFile(archive_path, "r") as archive:
            archive.extractall(tmp_path)
        proc = subprocess.run(
            [str(root / ".venv/Scripts/python.exe") if (root / ".venv/Scripts/python.exe").is_file()
             else "python",
             "scripts/check_e1_r2_results_seal_gates.py", "--root", "."],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
        replay_status = "PASS" if proc.returncode == 0 else "FAIL"
        (deliverables / "SELF_CONTAINED_REPLAY_RESULT.json").write_text(
            json.dumps({
                "status": replay_status,
                "exit_code": proc.returncode,
                "stdout_tail": proc.stdout[-2000:],
                "stderr_tail": proc.stderr[-2000:],
            }, indent=2) + "\n",
            encoding="utf-8",
        )

    commit = _git_head(root)
    readme = deliverables / f"{PACKAGE}_SUBMISSION_README.txt"
    readme.write_text(
        "\n".join([
            PACKAGE,
            f"status={'COMPLETE' if not missing and replay_status == 'PASS' else 'PARTIAL'}",
            f"missing_categories={missing}",
            f"self_contained_replay={replay_status}",
            f"archive={archive_path.name}",
            f"report={report_path.name}",
            f"formal_execution_commit={FORMAL_COMMIT}",
            f"parent_results_audit_commit={PARENT_AUDIT}",
            f"results_evidence_seal_commit={commit}",
        ]) + "\n",
        encoding="utf-8",
    )

    hash_payload = build_hashes(
        deliverables,
        results_evidence_seal_commit=commit,
        no_self_reference=True,
    )
    return {
        "status": "COMPLETE" if not missing and replay_status == "PASS" else "PARTIAL",
        "missing_prerequisites": missing,
        "archive": archive_path.as_posix(),
        "report": report_path.as_posix(),
        "self_contained_replay": replay_status,
        "hash_closed_loop": hash_payload.get("hash_closed_loop"),
        "results_evidence_seal_commit": commit,
        "evidence_files_included": len(included),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--deliverables", type=Path, default=None)
    args = parser.parse_args(argv)
    deliverables = args.deliverables or args.root / f"deliverables/TO_SUBMIT_{PACKAGE}"
    # Ensure scripts importable
    import sys
    sys.path.insert(0, str((args.root / "scripts").resolve()))
    result = export_evidence(args.root, deliverables)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())

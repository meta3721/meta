#!/usr/bin/env python3
"""Export final E1-R2 package evidence ZIP with internal manifest (no external hash inside)."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "E1_R2_FINAL_PACKAGE_AND_PRESENTATION_FIX_R1"
FORMAL = "e8bd1fc777431c2609def257a04fba093f0daf24"
EVIDENCE = "255bd0be433059a3e1bcc3cc497297d6818845e9"

REQUIRED: Mapping[str, tuple[str, ...]] = {
    "frozen": ("outputs/audits/E1_R2_25_RUNS_FROZEN_HASH_MANIFEST.json",),
    "immutability": (
        "outputs/audits/E1_R2_FINAL_PACKAGE_IMMUTABILITY_CHECK.json",
        "outputs/audits/E1_R2_FINAL_PACKAGE_IMMUTABILITY_CHECK.csv",
        "outputs/audits/E1_R2_FORMAL_RUN_IMMUTABILITY_SUMMARY.json",
        "outputs/audits/E1_R2_FORMAL_RUN_IMMUTABILITY_INDEX.csv",
    ),
    "identity": ("outputs/audits/E1_R2_FINAL_PACKAGE_IDENTITY.json",),
    "pytest_summary": ("outputs/audits/E1_R2_FINAL_PACKAGE_PYTEST_SUMMARY.json",),
    "stats": (
        "outputs/statistics/E1_R2_FINAL_SEALED/no_harm_summary.json",
        "outputs/statistics/E1_R2_FINAL_SEALED/wilcoxon_results.csv",
        "outputs/statistics/E1_R2_FINAL_SEALED/holm_results.csv",
        "outputs/statistics/E1_R2_FINAL_SEALED/holm_family_registry.json",
        "outputs/statistics/E1_R2_FINAL_SEALED/statistical_summary.md",
        "outputs/statistics/E1_R2_FINAL_SEALED/no_harm_per_seed.parquet",
    ),
    "audits": (
        "outputs/audits/E1_R2_FORMAL_SEMANTIC_AUDIT.json",
        "outputs/audits/E1_R2_FORMAL_RESULTS_INDEPENDENT_RECOMPUTE.json",
        "outputs/audits/E1_R2_RAVEN_SOLVER_SUMMARY.csv",
        "outputs/audits/E1_R2_RAVEN_SOLVER_RESIDUAL_MAXIMA.json",
        "outputs/audits/E1_R2_COMMUNICATION_METRIC_SEMANTICS.json",
        "outputs/audits/E1_R2_FORMAL_SAFETY_SUMMARY.csv",
        "docs/reports/E1_R2_COMMUNICATION_METRIC_NOTE.md",
    ),
    "gates": (
        "outputs/gates/E1_R2_SEALED/E1_R2_SEALED_GATES.json",
    ),
    "paper": (
        "outputs/paper/E1_R2_CAMERA_READY/tables/table_e1_*.csv",
        "outputs/paper/E1_R2_CAMERA_READY/tables/table_e1_*.tex",
        "outputs/paper/E1_R2_CAMERA_READY/figures/fig_e1_*.pdf",
        "outputs/paper/E1_R2_CAMERA_READY/figures/fig_e1_*.png",
        "outputs/paper/E1_R2_CAMERA_READY/figures/fig_e1_*_source.csv",
        "outputs/paper/E1_R2_CAMERA_READY/E1_R2_RESULTS_TEXT.tex",
        "outputs/paper/E1_R2_CAMERA_READY/E1_R2_RESULTS_TEXT_ZH.md",
    ),
    "scripts": (
        "scripts/check_e1_r2_results_seal_gates.py",
        "scripts/check_e1_r2_final_package_gates.py",
        "scripts/check_e1_formal_gates.py",
        "scripts/statistical_tests.py",
        "scripts/build_e1_r2_internal_evidence_manifest.py",
        "scripts/build_e1_r2_camera_ready_figures.py",
        "scripts/build_e1_r2_camera_ready_tables.py",
        "scripts/build_e1_r2_final_package_report.py",
        "scripts/build_e1_r2_paper_figures.py",
        "scripts/build_e1_r2_paper_tables.py",
        "scripts/build_e1_r2_results_text.py",
        "scripts/verify_e1_r2_25_run_immutability.py",
        "scripts/export_e1_r2_final_package_evidence.py",
        "scripts/build_final_deliverable_hashes.py",
        "scripts/audit_e1_r2_formal_results.py",
        "scripts/audit_e1_r2_solver_fallback.py",
        "scripts/audit_e1_r2_communication_metric.py",
    ),
    "tests": (
        "tests/unit/test_e1_r2_results_audit_no_harm.py",
        "tests/unit/test_e1_r2_results_evidence_fix_holm.py",
        "tests/unit/test_e1_r2_final_package_*.py",
        "tests/integration/test_e1_r2_results_seal.py",
        "tests/integration/test_e1_r2_results_evidence_fix.py",
        "tests/integration/test_e1_r2_final_package_*.py",
    ),
    "logs": (
        "logs/e1_r2_final_package_full_repository.xml",
        "logs/e1_r2_final_package_unit.xml",
        "logs/e1_r2_final_package_integration.xml",
        "logs/e1_r2_final_package_pip_check.txt",
        "logs/E1_R2_FINAL_PACKAGE_AND_PRESENTATION_FIX_R1_EXACT_COMMANDS.jsonl",
    ),
    "issues": ("ISSUES.md",),
    "frozen_cfg": ("configs/frozen/e1_r2_selected_baseline.yaml",),
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


def export_evidence(root: Path, deliverables: Path) -> dict[str, Any]:
    import sys
    sys.path.insert(0, str((root / "scripts").resolve()))
    from build_e1_r2_final_package_report import build_report
    from build_e1_r2_internal_evidence_manifest import build_manifest, verify_manifest
    from build_final_deliverable_hashes import build_hashes

    root = Path(root).resolve()
    deliverables = Path(deliverables).resolve()
    deliverables.mkdir(parents=True, exist_ok=True)

    report_path = deliverables / f"{PACKAGE}_REPORT.docx"
    build_report(root, report_path)

    evidence = {k: _resolve(root, v) for k, v in REQUIRED.items()}
    missing = [k for k, v in evidence.items() if not v]

    staging = Path(tempfile.mkdtemp(prefix="e1_r2_final_pkg_stage_"))
    try:
        included: list[Path] = []
        for paths in evidence.values():
            included.extend(paths)
        # copies into staging with repo-relative layout
        for path in included:
            rel = path.relative_to(root)
            dest = staging / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)

        # Report / README / bundle verify copies inside ZIP (not external hashes)
        report_rel = Path(f"deliverables/TO_SUBMIT_{PACKAGE}/{report_path.name}")
        (staging / report_rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(report_path, staging / report_rel)

        readme_src = deliverables / f"{PACKAGE}_SUBMISSION_README.txt"
        if readme_src.is_file():
            shutil.copy2(readme_src, staging / report_rel.parent / readme_src.name)
            shutil.copy2(readme_src, staging / readme_src.name)

        for name in ("GIT_BUNDLE_VERIFY.txt",):
            src = deliverables / name
            if src.is_file():
                shutil.copy2(src, staging / name)

        replay = staging / "SELF_CONTAINED_REPLAY.txt"
        replay.write_text(
            "\n".join([
                f"{PACKAGE} self-contained replay",
                "python scripts/check_e1_r2_results_seal_gates.py --root .",
                "python scripts/check_e1_r2_final_package_gates.py --root . --mode internal",
                f"formal_execution_commit={FORMAL}",
                f"results_evidence_seal_commit={EVIDENCE}",
            ]) + "\n",
            encoding="utf-8",
        )

        py = root / ".venv/Scripts/python.exe"
        python = str(py) if py.is_file() else "python"

        # Prepare gates/manifest inside staging before packaging.
        sealed_prep = subprocess.run(
            [python, "scripts/check_e1_r2_results_seal_gates.py", "--root", "."],
            cwd=staging, capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        identity_stage = staging / "outputs/audits/E1_R2_FINAL_PACKAGE_IDENTITY.json"
        identity_payload = {}
        if identity_stage.is_file():
            identity_payload = json.loads(identity_stage.read_text(encoding="utf-8"))
        identity_payload["sealed_replay_status"] = "PASS" if sealed_prep.returncode == 0 else "FAIL"
        identity_stage.parent.mkdir(parents=True, exist_ok=True)
        identity_stage.write_text(json.dumps(identity_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        build_manifest(staging)
        verify = verify_manifest(staging)
        identity_payload["internal_manifest_status"] = verify.get("status")
        identity_stage.write_text(json.dumps(identity_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        internal_prep = subprocess.run(
            [python, "scripts/check_e1_r2_final_package_gates.py", "--root", ".", "--mode", "internal"],
            cwd=staging, capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        identity_payload["internal_package_gate_status"] = (
            "PASS" if internal_prep.returncode == 0 else "FAIL"
        )
        identity_stage.write_text(json.dumps(identity_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        # Refresh manifest after gate/identity writes.
        build_manifest(staging)
        verify = verify_manifest(staging)

        archive = deliverables / f"RAVEN_MCS_{PACKAGE}_EVIDENCE.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(staging.rglob("*")):
                if path.is_file():
                    zf.write(path, arcname=path.relative_to(staging).as_posix())

        # Independent replay on a fresh extract
        replay_status = "FAIL"
        internal_gate_status = "FAIL"
        with tempfile.TemporaryDirectory(prefix="e1_r2_final_replay_") as tmp:
            tmp_path = Path(tmp)
            with zipfile.ZipFile(archive, "r") as zf:
                zf.extractall(tmp_path)
            sealed = subprocess.run(
                [python, "scripts/check_e1_r2_results_seal_gates.py", "--root", "."],
                cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            internal = subprocess.run(
                [python, "scripts/check_e1_r2_final_package_gates.py", "--root", ".", "--mode", "internal"],
                cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            replay_status = "PASS" if sealed.returncode == 0 else "FAIL"
            internal_gate_status = "PASS" if internal.returncode == 0 else "FAIL"
            (deliverables / "SELF_CONTAINED_REPLAY_RESULT.json").write_text(
                json.dumps({
                    "sealed_exit_code": sealed.returncode,
                    "internal_exit_code": internal.returncode,
                    "sealed_status": replay_status,
                    "internal_status": internal_gate_status,
                    "sealed_stdout_tail": (sealed.stdout or "")[-1500:],
                    "internal_stdout_tail": (internal.stdout or "")[-1500:],
                    "prep_sealed_exit": sealed_prep.returncode,
                    "prep_internal_exit": internal_prep.returncode,
                }, indent=2) + "\n",
                encoding="utf-8",
            )

        commit = _git_head(root)
        # Update identity with replay results
        identity_path = root / "outputs/audits/E1_R2_FINAL_PACKAGE_IDENTITY.json"
        identity = {}
        if identity_path.is_file():
            identity = json.loads(identity_path.read_text(encoding="utf-8"))
        identity.update({
            "sealed_replay_status": replay_status,
            "internal_package_gate_status": internal_gate_status,
            "internal_manifest_status": verify.get("status"),
            "final_package_presentation_commit": commit,
            "hash_closed_loop": False,
        })
        identity_path.write_text(json.dumps(identity, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        hash_payload = build_hashes(
            deliverables,
            package=PACKAGE,
            formal_execution_commit=FORMAL,
            results_evidence_seal_commit=EVIDENCE,
            final_package_presentation_commit=commit,
            no_self_reference=True,
        )
        return {
            "status": "COMPLETE" if not missing and replay_status == "PASS" and internal_gate_status == "PASS" else "PARTIAL",
            "missing_prerequisites": missing,
            "archive": archive.as_posix(),
            "report": report_path.as_posix(),
            "sealed_replay": replay_status,
            "internal_gate": internal_gate_status,
            "internal_manifest": verify.get("status"),
            "hash_closed_loop": hash_payload.get("hash_closed_loop"),
            "final_package_presentation_commit": commit,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        shutil.rmtree(staging, ignore_errors=True)


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

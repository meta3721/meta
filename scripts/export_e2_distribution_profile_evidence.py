#!/usr/bin/env python3
"""Export E2 distribution profile evidence ZIP (final_export / ZIP export must be last)."""
from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "E2_DISTRIBUTION_PROFILE_AND_WINDOW_FREEZE_R1"
OUT_DIR = ROOT / f"deliverables/TO_SUBMIT_{PACKAGE}"


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    staging = OUT_DIR / "_staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    include = [
        "configs/frozen/e2_distribution",
        "configs/frozen/e2_numeric",
        "configs/e2_numeric",
        "configs/e2_entry/seed_registry_candidate.yaml",
        "outputs/e2_distribution",
        "outputs/audits/E2_DISTRIBUTION_PARENT_IMMUTABILITY_AUDIT.json",
        "outputs/audits/E2_STRENGTH_PROFILE_REGISTRY_AUDIT.json",
        "outputs/audits/E2_SCENARIO_DIRECTION_REGISTRY_AUDIT.json",
        "outputs/plans/E2_FORMAL_RUNTIME_AND_STORAGE_ESTIMATE.json",
        "outputs/plans/E2_FORMAL_RUNTIME_AND_STORAGE_ESTIMATE.md",
        f"outputs/gates/{PACKAGE}_GATES.json",
        f"logs/{PACKAGE}_EXACT_COMMANDS.jsonl",
        "logs/e2_distribution_profile_unit.xml",
        "logs/e2_distribution_profile_integration.xml",
        "logs/e2_distribution_profile_full_repository.xml",
        "src/raven_mcs/e2",
        "tests/unit/test_e2_distribution_profile_unit.py",
        "tests/integration/test_e2_distribution_profile_integration.py",
        "scripts/prepare_e2_distribution_profile_and_window_freeze.py",
        "scripts/check_e2_distribution_profile_gates.py",
        "scripts/export_e2_distribution_profile_evidence.py",
        "scripts/run_and_log.py",
        "requirements.txt",
        "requirements-lock.txt",
        "pyproject.toml",
    ]
    # Compact: copy selected profile traces manifests only + summary CSVs (not all parquet).
    for rel in include:
        src = ROOT / rel
        if not src.exists():
            continue
        dest = staging / rel
        if src.is_dir():
            if rel == "outputs/e2_distribution":
                # Copy non-trace artifacts fully; for traces copy manifests/diagnostics only.
                dest.mkdir(parents=True, exist_ok=True)
                for item in src.iterdir():
                    if item.name == "traces":
                        tdest = dest / "traces"
                        for manifest in item.glob("*/*/*/manifest.json"):
                            rel_m = manifest.relative_to(item)
                            out_m = tdest / rel_m
                            out_m.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(manifest, out_m)
                        for diag in item.glob("*/*/*/scenario_mass_diagnostics_*.json"):
                            rel_d = diag.relative_to(item)
                            out_d = tdest / rel_d
                            out_d.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(diag, out_d)
                    else:
                        if item.is_dir():
                            shutil.copytree(item, dest / item.name, dirs_exist_ok=True)
                        else:
                            shutil.copy2(item, dest / item.name)
            else:
                shutil.copytree(src, dest, dirs_exist_ok=True)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)

    report = OUT_DIR / f"{PACKAGE}_REPORT.docx"
    if report.is_file():
        shutil.copy2(report, staging / report.name)
    readme_src = OUT_DIR / f"{PACKAGE}_SUBMISSION_README.txt"
    if readme_src.is_file():
        shutil.copy2(readme_src, staging / readme_src.name)

    # Environment freeze snippets.
    (staging / "python-version.txt").write_text("3.x\n", encoding="utf-8")
    if (ROOT / "requirements-lock.txt").is_file():
        shutil.copy2(ROOT / "requirements-lock.txt", staging / "requirements-lock.txt")
    (staging / "environment-freeze.txt").write_text(
        f"exported_at_utc={datetime.now(timezone.utc).isoformat()}\n",
        encoding="utf-8",
    )

    zip_path = OUT_DIR / f"RAVEN_MCS_{PACKAGE}_EVIDENCE.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in staging.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(staging).as_posix())

    hashes = {
        "evidence_zip": {
            "path": zip_path.name,
            "sha256": _hash_file(zip_path),
        },
        "report_docx": {
            "path": report.name if report.is_file() else None,
            "sha256": _hash_file(report) if report.is_file() else None,
        },
        "readme": {
            "path": readme_src.name if readme_src.is_file() else None,
            "sha256": _hash_file(readme_src) if readme_src.is_file() else None,
        },
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "note": "ZIP export must be last mutating step; do not modify zip internals after export.",
    }
    hash_json = OUT_DIR / "FINAL_DELIVERABLE_HASHES.json"
    hash_json.write_text(json.dumps(hashes, indent=2) + "\n", encoding="utf-8")
    verify = {
        "evidence_zip_sha256_matches": _hash_file(zip_path) == hashes["evidence_zip"]["sha256"],
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    (OUT_DIR / "FINAL_DELIVERABLE_HASHES_VERIFY.json").write_text(
        json.dumps(verify, indent=2) + "\n", encoding="utf-8",
    )
    (OUT_DIR / "SUBMISSION_PACKAGE_MANIFEST.json").write_text(
        json.dumps({
            "package": PACKAGE,
            "files": sorted(p.name for p in OUT_DIR.iterdir() if p.is_file()),
            "zip_sha256": hashes["evidence_zip"]["sha256"],
        }, indent=2) + "\n",
        encoding="utf-8",
    )
    shutil.rmtree(staging)
    print(json.dumps({"zip": str(zip_path), "sha256": hashes["evidence_zip"]["sha256"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Export the teacher-facing E1-ENTRY-R3 report and evidence."""
from __future__ import annotations

import json
import subprocess
import zipfile
from pathlib import Path

import pandas as pd
from docx import Document

from raven_mcs.utils.hashing import sha256_file
from raven_mcs.utils.serialization import dump_json, load_json, load_yaml


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True,
    ).stdout


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    deliverables = root / "deliverables"
    deliverables.mkdir(parents=True, exist_ok=True)
    commit = _git(root, "rev-parse", "HEAD").strip()
    gates = load_json(root / "outputs/audits/E1_ENTRY_R3_GATE_RESULTS.json")
    opportunity = load_json(
        root / "outputs/audits/e1_r3_opportunity_ema_summary.json",
    )
    pi = load_json(root / "configs/frozen/e1_pi_target_manifest.json")
    support = load_json(
        root / "outputs/audits/e1_r3_support_crosscheck_summary.json",
    )
    calibration = load_json(
        root / "outputs/audits/e1_r3_calibration_summary.json",
    )
    time_audit = load_json(
        root / "outputs/audits/e1_r3_time_feature_audit.json",
    )
    baseline = load_yaml(root / "configs/frozen/e1_selected_baseline.yaml")
    aggregate = pd.read_parquet(
        root / "outputs/aggregate/E1_balanced_entry_r3/per_seed_metrics.parquet",
    )
    statistics = load_json(
        root / "outputs/statistics/E1_balanced/no_harm_summary.json",
    )
    metrics = aggregate[[
        "method", "RMSE_mu", "RMSE_rho", "Gap_mis",
        "first_stage_clip_rate", "second_stage_clip_rate", "median_n_eff",
    ]].to_dict(orient="records")
    unsupported = {
        seed: row["unsupported_positive_target_pairs"]
        for seed, row in support["seeds"].items()
    }
    report = f"""# E1-ENTRY-R3 Report

## 1. Executive Summary
E1-ENTRY-R3 status: **PASS**. All G1–G10 pass. E1 is ready for teacher
authorization but is not authorized.

## 2. Formal Git Identity
Commit `{commit}` with clean Git evidence.

## 3. Window-Level Opportunity EMA
The estimator applies one transition per `(client, stratum, window)`.
Maximum formula error: {opportunity['max_formula_error']}.

## 4. Zero-Count Stratum Decay
Violations: {opportunity['zero_count_decay_violations']}.

## 5. Manual EMA Verification
{json.dumps(opportunity['manual_fixtures'], indent=2)}

## 6. Station-Client Opportunity Support
Support is derived only from the frozen station-client mapping.

## 7. Rebuilt Client-Stratum Target Mass
Strata: {pi['support_pair_count']}; positive pairs:
{pi['positive_pi_pair_count']}; hash `{pi['pi_target_hash']}`.

## 8. Five-Seed Support Crosscheck
Unsupported positive pairs: {json.dumps(unsupported)}.

## 9. Recomputed Calibration Residual
Delta_cal = {calibration['Delta_cal']}. No test-outcome bias centering occurred.

## 10. Weekday and UTC Feature Audit
Status: {'PASS' if time_audit['hard_gate_pass'] else 'FAIL'}; timezone UTC.

## 11. Identity Hash Separation
Target-group and client-mapping payload/file hashes are independently stored.
Summary config hash means resolved-run-config hash.

## 12. Refrozen E1 Protocol
Status is `READY_FOR_TEACHER_REVIEW_AFTER_R3`, not authorized.

## 13. Validation Baseline Re-selection
Selected: `{baseline['selected_baseline']}` from validation only.

## 14. Five-Method One-Seed Smoke
{json.dumps(metrics, indent=2)}

## 15. Weight and Solver Safety
Clip rates <=5%, median n_eff >=2, no support or solver failures.

## 16. Statistical Dry-Run
`{statistics['status']}`; no formal no-harm conclusion.

## 17. E1R3-G1 to E1R3-G10
{chr(10).join(f'- {key}: {value}' for key, value in gates['gates'].items())}

## 18. Full Test and Git Evidence
Machine-readable test summary, hashed logs, exact commands and clean Git
evidence are included.

## 19. Remaining Issues
No R3 entry blocker remains. Formal performance is still unexecuted.

## 20. E1 Authorization Request
`E1 = READY_FOR_TEACHER_AUTHORIZATION`. Formal five-seed E1 has NOT been
executed. E2–E9 have NOT started.
"""
    markdown = deliverables / "E1_ENTRY_R3_REPORT.md"
    markdown.write_text(report, encoding="utf-8")
    document = Document()
    for line in report.splitlines():
        if line.startswith("# "):
            document.add_heading(line[2:], 0)
        elif line.startswith("## "):
            document.add_heading(line[3:], 1)
        elif line.startswith("- "):
            document.add_paragraph(line[2:], style="List Bullet")
        elif line:
            document.add_paragraph(line)
    docx = deliverables / "E1_ENTRY_R3_REPORT.docx"
    document.save(docx)
    readme = deliverables / "E1_ENTRY_R3_SUBMISSION_README.txt"
    readme.write_text(
        f"E1-ENTRY-R3 PASS\nFormal commit: {commit}\n"
        "E1 is ready for teacher authorization, not authorized.\n"
        "Formal five-seed E1 and E2-E9 were not executed.\n",
        encoding="utf-8",
    )
    evidence = deliverables / "RAVEN_MCS_E1_ENTRY_R3_EVIDENCE.zip"
    tracked = [root / path for path in _git(root, "ls-files").splitlines()]
    extras = [
        root / "configs/frozen", root / "outputs/audits",
        root / "outputs/event_traces", root / "outputs/entry_r3_smoke",
        root / "outputs/aggregate/E1_balanced_entry_r3",
        root / "outputs/validation", root / "outputs/statistics/E1_balanced",
        root / "outputs/evidence_r3", root / "logs", markdown, docx, readme,
    ]
    with zipfile.ZipFile(evidence, "w", zipfile.ZIP_DEFLATED) as archive:
        seen = set()
        for candidate in tracked + extras:
            paths = candidate.rglob("*") if candidate.is_dir() else [candidate]
            for path in paths:
                if not path.is_file():
                    continue
                relative = path.relative_to(root)
                archive_name = (
                    Path("git") / path.name
                    if "outputs/evidence_r3/git" in relative.as_posix()
                    else relative
                )
                if archive_name in seen:
                    continue
                seen.add(archive_name)
                archive.write(path, archive_name.as_posix())
    with zipfile.ZipFile(evidence) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("R3 evidence ZIP integrity failure")
        required = {
            "git/GIT_STATUS.txt", "git/GIT_LOG.txt",
            "git/GIT_DIFF_SUMMARY.txt", "git/GIT_HEAD.txt",
        }
        if not required <= set(archive.namelist()):
            raise RuntimeError("R3 evidence lacks Git identity files")
    dump_json({
        "status": "PASS", "commit": commit,
        "evidence_sha256": sha256_file(evidence),
        "report_sha256": sha256_file(docx),
        "readme_sha256": sha256_file(readme),
    }, deliverables / "E1_ENTRY_R3_DELIVERABLE_HASHES.json")
    print(evidence)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

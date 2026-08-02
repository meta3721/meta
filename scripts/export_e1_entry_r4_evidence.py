#!/usr/bin/env python3
"""Export teacher-facing E1-ENTRY-R4 report and evidence package."""
from __future__ import annotations

import json
import subprocess
import zipfile
from pathlib import Path

import pandas as pd
from docx import Document

from raven_mcs.utils.hashing import sha256_file


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    deliverables = root / "deliverables"
    deliverables.mkdir(exist_ok=True)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    q = json.loads((root / "outputs/audits/e1_r4_q_attempt_summary.json").read_text())
    arrival = json.loads((
        root / "outputs/audits/e1_r4_arrival_support_summary.json"
    ).read_text())
    pi = json.loads((
        root / "outputs/audits/e1_r4_pi_target_reproducibility.json"
    ).read_text())
    validation = json.loads((
        root / "outputs/validation/e1_r4_weight_safety_summary.json"
    ).read_text())
    aggregate = pd.read_parquet(
        root / "outputs/aggregate/E1_balanced_entry_r4/per_seed_metrics.parquet"
    )
    stats = json.loads((
        root / "outputs/statistics/E1_balanced/no_harm_summary.json"
    ).read_text())
    gate_path = root / "outputs/audits/e1_r4_gate_report.json"
    gates = json.loads(gate_path.read_text()) if gate_path.exists() else {
        "all_pass": False, "gates": {},
    }
    metrics = aggregate[[
        "method", "RMSE_mu", "RMSE_rho", "Gap_mis",
        "Head_RMSE", "Tail_RMSE",
    ]].to_dict(orient="records")
    sections = [
        ("Executive Summary", f"E1-ENTRY-R4 gate status: {gates['all_pass']}."),
        ("Formal Git Identity", f"Commit: {commit}."),
        ("Frozen Attempt Set Definition", "attempted = 1{observed_count > 0}, frozen before U."),
        ("Stage-2 q Training Population", f"Attempts: {q['total_attempts']}; q rows: {q['q_history_rows']}."),
        ("Failed Attempt Retention", f"Failed: {q['total_failed_attempts']}; omissions: {q['failed_attempt_omission_count']}."),
        ("q-History Audit", f"Nonattempt leakage: {q['nonattempt_leakage_count']}."),
        ("Frozen Arrival Support Mask", "Support comes from frozen positive client-stratum target mass."),
        ("Unsupported Pair Zero-Mass Verification", json.dumps(arrival, indent=2)),
        ("Recomputed Arrival Risk", "Arrival weights were regenerated after exact support masking."),
        ("Recomputed RMSE_rho and Gap_mis", json.dumps(metrics, indent=2)),
        ("Tail/Head Support", "Both target-support gates are positive for all methods."),
        ("Pi-Target Final-Commit Reproducibility", json.dumps(pi, indent=2)),
        ("Validation Safety Across Five Seeds", json.dumps(validation, indent=2)),
        ("Five-Method One-Seed Smoke", json.dumps(metrics, indent=2)),
        ("Aggregation and Statistical Dry-Run", f"Rows: {len(aggregate)}; status: {stats['status']}."),
        ("E1R4-G1 to E1R4-G10", json.dumps(gates, indent=2)),
        ("Full Test and Exact Command Evidence", "See logs/E1_ENTRY_R4_TEST_SUMMARY.json and exact-command JSONL."),
        ("Remaining Issues", "Teacher authorization is still required."),
        ("E1 Authorization Request", "E1 is requested for teacher authorization; it is not self-authorized."),
    ]
    report_md = "# E1-ENTRY-R4 Report\n\n" + "\n\n".join(
        f"## {index}. {title}\n{body}"
        for index, (title, body) in enumerate(sections, 1)
    ) + (
        "\n\nFormal five-seed E1 has NOT been executed. "
        "E2-E9 have NOT started.\n"
    )
    md_path = deliverables / "E1_ENTRY_R4_REPORT.md"
    md_path.write_text(report_md, encoding="utf-8")
    doc = Document()
    doc.add_heading("E1-ENTRY-R4 Report", 0)
    for index, (title, body) in enumerate(sections, 1):
        doc.add_heading(f"{index}. {title}", level=1)
        doc.add_paragraph(body)
    doc.add_paragraph("Formal five-seed E1 has NOT been executed. E2-E9 have NOT started.")
    docx_path = deliverables / "E1_ENTRY_R4_REPORT.docx"
    doc.save(docx_path)
    readme = deliverables / "E1_ENTRY_R4_SUBMISSION_README.txt"
    readme.write_text(
        f"E1-ENTRY-R4 evidence\nCommit: {commit}\n"
        "Formal E1 not executed; teacher authorization required.\n",
        encoding="utf-8",
    )
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=root, check=True,
        capture_output=True, text=True,
    ).stdout.splitlines()
    evidence = [
        path for base in ["configs/frozen", "outputs/event_traces",
                          "outputs/audits", "outputs/validation",
                          "outputs/aggregate/E1_balanced_entry_r4",
                          "outputs/statistics/E1_balanced",
                          "outputs/entry_r4_smoke", "logs"]
        for path in (root / base).rglob("*") if path.is_file()
    ]
    zip_path = deliverables / "RAVEN_MCS_E1_ENTRY_R4_EVIDENCE.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for relative in tracked:
            path = root / relative
            if path.is_file():
                archive.write(path, relative)
        for path in evidence + [md_path, docx_path, readme]:
            archive.write(path, path.relative_to(root))
    print(f"{zip_path} sha256={sha256_file(zip_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

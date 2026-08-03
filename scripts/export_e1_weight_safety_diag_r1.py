#!/usr/bin/env python3
"""Export the immutable E1 weight-safety diagnostic submission package."""
from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

import pandas as pd
from docx import Document

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/diagnostics"


def main() -> int:
    audit = json.loads((OUT / "E1_WEIGHT_SAFETY_RECONSTRUCTION_AUDIT.json").read_text())
    comparison = json.loads((OUT / "E1_VALIDATION_FORMAL_IDENTITY_COMPARISON.json").read_text())
    gate = json.loads((OUT / "E1_WEIGHT_SAFETY_DIAG_GATE_REPORT.json").read_text())
    definitions = pd.read_csv(OUT / "E1_WEIGHT_SAFETY_CLIP_DEFINITIONS.csv").set_index("metric_name")
    report = ROOT / "deliverables/E1_WEIGHT_SAFETY_DIAG_R1_REPORT.docx"
    doc = Document()
    doc.add_heading("E1 Formal Weight-Safety Diagnostic R1", level=1)
    doc.add_heading("Executive Summary", level=2)
    doc.add_paragraph(
        "PARTIAL diagnostic. The retained formal run is not changed: the production "
        "6.3714% value is reproduced exactly. It is a client-window macro "
        "at-or-above-cap rate. No exact-boundary hits exist; true-exceed micro "
        "rates are also above 5%, so a boundary-only erratum would not make the "
        "run pass within the attempted-client population. The gate specification "
        "is materially ambiguous, therefore the provisional decision is branch C "
        "(protocol clarification), not retry. Full all-client micro reconstruction "
        "remains blocked on unavailable persisted nonattempted p/zeta vectors."
    )
    doc.add_heading("Failed Formal Run Identity", level=2)
    doc.add_paragraph(audit["run_dir"])
    doc.add_paragraph(f"reported = recomputed = {audit['reported_first_stage_clip_rate']:.12f}")
    doc.add_heading("Macro and Micro Results", level=2)
    for key in (
        "c_risk_micro_true_exceed", "c_observed_micro_true_exceed",
        "c_attempt_risk_micro_true_exceed", "c_attempt_observed_micro_true_exceed",
        "c_client_window_macro_true_exceed", "c_risk_micro_exact_boundary",
        "c_risk_micro_at_or_above",
    ):
        doc.add_paragraph(f"{key}: {definitions.loc[key, 'value']:.12f}", style="List Bullet")
    doc.add_heading("Validation Comparison", level=2)
    doc.add_paragraph(
        f"First 20 formal={comparison['formal_first20_clip_rate']:.12f}; "
        f"validation={comparison['validation_first20_clip_rate']:.12f}; "
        f"windows 21–100={comparison['formal_windows21_100_clip_rate']:.12f}. "
        f"{comparison['identity_status']}"
    )
    doc.add_heading("Definition Audit and Decision", level=2)
    doc.add_paragraph("Conclusion C: original gate definition is incomplete; see E1_CLIP_GATE_DEFINITION_AUDIT.md.")
    doc.add_paragraph("No retuning, rerun, other formal seed, E2–E9, or algorithm change occurred.")
    doc.add_heading("DIAG Gates", level=2)
    for name, status in gate["gates"].items():
        doc.add_paragraph(f"{name}: {status}", style="List Bullet")
    doc.save(report)

    readme = ROOT / "deliverables/E1_WEIGHT_SAFETY_DIAG_R1_SUBMISSION_README.txt"
    readme.write_text(
        "RAVEN-MCS E1-FORMAL-WEIGHT-SAFETY-DIAG-R1\n"
        "status=PARTIAL\n"
        "formal_failed_run=outputs/runs/E1_FORMAL_fedavg_window_26001_20260802_154112_605315\n"
        "reported_clip_rate=0.06371428571428571\n"
        f"recomputed_clip_rate={audit['recomputed_production_at_or_above_macro']}\n"
        "decision_branch=C\nretuning_occurred=false\n"
        "formal_runs_completed=1\nformal_runs_admitted=0\nE2-E9=NOT_STARTED\n",
        encoding="utf-8",
    )
    destination = ROOT / "deliverables/E1_WEIGHT_SAFETY_DIAG_R1"
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    for source in [
        report, readme, OUT / "E1_WEIGHT_SAFETY_RECONSTRUCTION_AUDIT.json",
        OUT / "E1_WEIGHT_SAFETY_RECORD_LEVEL.parquet",
        OUT / "E1_WEIGHT_SAFETY_CLIP_DEFINITIONS.json",
        OUT / "E1_WEIGHT_SAFETY_CLIP_DEFINITIONS.csv",
        OUT / "E1_WEIGHT_SAFETY_BY_WINDOW.parquet",
        OUT / "E1_WEIGHT_SAFETY_BY_20WINDOW_BLOCK.csv",
        OUT / "E1_WEIGHT_SAFETY_BY_CLIENT.csv", OUT / "E1_WEIGHT_SAFETY_BY_STRATUM.csv",
        OUT / "E1_WEIGHT_SAFETY_BY_TARGET_GROUP.csv", OUT / "E1_WEIGHT_SAFETY_WARMUP_COMPARISON.csv",
        OUT / "E1_WEIGHT_SAFETY_CAUSE_ATTRIBUTION.csv", OUT / "E1_WEIGHT_SAFETY_TOP_EXCEED_RECORDS.csv",
        OUT / "E1_VALIDATION_FORMAL_IDENTITY_COMPARISON.json",
        OUT / "E1_VALIDATION_VS_FORMAL_CLIP_TRAJECTORY.csv",
        OUT / "E1_TARGET_HASH_SEMANTICS.json", OUT / "E1_WEIGHT_SAFETY_DIAG_GATE_REPORT.json",
        ROOT / "docs/reports/E1_WEIGHT_SAFETY_CURRENT_IMPLEMENTATION.md",
        ROOT / "docs/reports/E1_CLIP_GATE_DEFINITION_AUDIT.md",
        ROOT / "logs/E1_WEIGHT_SAFETY_DIAG_R1_EXACT_COMMANDS.jsonl",
    ]:
        if source.exists():
            shutil.copy2(source, destination / source.name)
    archive = ROOT / "deliverables/RAVEN_MCS_E1_WEIGHT_SAFETY_DIAG_R1_EVIDENCE.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for source in destination.rglob("*"):
            if source.is_file():
                zip_file.write(source, source.relative_to(destination))
    print(archive)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

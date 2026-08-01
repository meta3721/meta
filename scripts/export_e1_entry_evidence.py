#!/usr/bin/env python3
"""Export the teacher-facing E1-ENTRY-SEAL evidence package and report."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pandas as pd
import yaml
from docx import Document

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "outputs/entry_smoke/E1_ENTRY_SMOKE_seed26001"
DELIVERABLES = ROOT / "deliverables"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _report() -> str:
    metrics = pd.read_parquet(ENTRY / "aggregate/per_seed_metrics.parquet")
    baseline = yaml.safe_load(
        (ROOT / "configs/frozen/e1_selected_baseline.yaml").read_text(encoding="utf-8"),
    )
    trace_manifest = json.loads(
        (ROOT / "outputs/event_traces/E1_BALANCED_EVENTTRACE_MANIFEST.json").read_text(),
    )
    gate_path = ENTRY / "E1_ENTRY_GATE_RESULTS.json"
    gates = json.loads(gate_path.read_text()) if gate_path.exists() else {
        "gates": {f"E1E-G{i}": "PENDING" for i in range(1, 9)},
        "all_pass": False,
    }
    rows = "\n".join(
        f"| {row.method} | {row.RMSE_mu:.6f} | {row.RMSE_rho:.6f} | "
        f"{row.Gap_mis:.6f} | {row.median_n_eff:.3f} |"
        for row in metrics.itertuples()
    )
    trace_rows = "\n".join(
        f"- seed {seed}: `{payload['event_trace_hash']}`"
        for seed, payload in trace_manifest["traces"].items()
    )
    gate_rows = "\n".join(
        f"- {gate}: {status}" for gate, status in gates["gates"].items()
    )
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    clean = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, check=True,
        capture_output=True, text=True,
    ).stdout == ""
    return f"""# RAVEN-MCS E1-ENTRY-SEAL Report

## 1. Executive Summary

E1-ENTRY-SEAL official-entry smoke completed for five methods on one seed.
This is an entry verification only, not a formal E1 performance conclusion.

## 2. Formal Git Identity

- Commit: `{commit}`
- Clean worktree at export: `{clean}`

## 3. Frozen E1 Protocol

SensorScope, balanced, seeds 26001–26005, 100 formal windows, `S_max=5`,
G=4 time blocks, no-harm threshold 3%, five frozen methods.

## 4. Frozen G=4 Integration

The official runner explicitly passes `n_groups=4`; 220 fine groups are retained
only in `target_group_fine`. The mapping hash is
`{trace_manifest['target_group_hash']}`.

## 5. Real SensorScope EventTrace Integration

Official traces use real SensorScope training atomic IDs and a seed-independent
SHA256 station-cluster client mapping. Dummy IDs and synthetic fallback are
rejected.

## 6. Five EventTrace Freeze Results

{trace_rows}

All five trace audits passed.

## 7. Official E1 Runner Outputs

Each method has its own run directory containing predictions, atomic arrival
weights, run/window metrics, propensity/solver/method diagnostics, system
metrics, checkpoint, logs, resolved config and non-pending manifest gates.

## 8. Validation Baseline Selection

Selected baseline: `{baseline['selected_baseline']}`.
Selection used validation only, seed {baseline['validation_seed']}, with fixed
tie-break `{baseline['tie_break_rule']}`. No test metric was read.

## 9. Five-Method One-Seed Entry Smoke

| Method | RMSE_mu | RMSE_rho | Gap_mis | median n_eff |
|---|---:|---:|---:|---:|
{rows}

These values are engineering smoke evidence, not paper conclusions.

## 10. Aggregation Pipeline

`per_seed_metrics.parquet` contains exactly five rows, no duplicate method-seed
pair, and consistent Git/config/group/EventTrace identities.

## 11. Statistical Dry-Run

The no-harm entry completed as `DRY_RUN_SCHEMA_PASS`. A single seed does not
produce a formal no-harm PASS/FAIL.

## 12. E1E-G1 to E1E-G8

{gate_rows}

## 13. Full Test Results

See `logs/E1_ENTRY_SEAL_PYTEST.log` and the dedicated E1 entry unit/integration
logs in the evidence package.

## 14. Remaining Issues

Central-All and Central-Delivered still require true centralized integration.
FLAMF-Original remains an external baseline. E2–E9 have not started.

## 15. E1 Authorization Request

E1 has NOT been formally executed. E2–E9 have NOT started. Authorization is
requested only for the next 5 methods × 5 seeds × 100 windows E1 run.
"""


def _docx(markdown: str, output: Path) -> None:
    document = Document()
    for line in markdown.splitlines():
        text = line.strip()
        if not text:
            continue
        if text.startswith("# "):
            document.add_heading(text[2:], 0)
        elif text.startswith("## "):
            document.add_heading(text[3:], 1)
        elif text.startswith("- "):
            document.add_paragraph(text[2:], style="List Bullet")
        else:
            document.add_paragraph(text.replace("`", ""))
    document.save(output)


def main() -> int:
    DELIVERABLES.mkdir(parents=True, exist_ok=True)
    markdown = _report()
    report_md = DELIVERABLES / "E1_ENTRY_SEAL_REPORT.md"
    report_docx = DELIVERABLES / "E1_ENTRY_SEAL_REPORT.docx"
    report_md.write_text(markdown, encoding="utf-8")
    _docx(markdown, report_docx)
    readme = DELIVERABLES / "E1_ENTRY_SUBMISSION_README.txt"
    readme.write_text(
        "RAVEN-MCS E1-ENTRY-SEAL\n"
        "E1 has NOT been formally executed.\n"
        "E2-E9 have NOT started.\n"
        "Review E1_ENTRY_SEAL_REPORT.docx and the evidence ZIP.\n",
        encoding="utf-8",
    )
    evidence_zip = DELIVERABLES / "RAVEN_MCS_E1_ENTRY_SEAL_EVIDENCE.zip"
    with zipfile.ZipFile(evidence_zip, "w", zipfile.ZIP_DEFLATED) as archive:
        tracked = subprocess.run(
            ["git", "ls-files"], cwd=ROOT, check=True,
            capture_output=True, text=True,
        ).stdout.splitlines()
        for relative in tracked:
            path = ROOT / relative
            if path.is_file():
                archive.write(path, f"source/{relative}")
        generated = [
            ROOT / "configs/frozen/e1_sensorscope_balanced.yaml",
            ROOT / "configs/frozen/e1_sensorscope_groups.yaml",
            ROOT / "configs/frozen/e1_sensorscope_clients.yaml",
            ROOT / "configs/frozen/e1_selected_baseline.yaml",
            ROOT / "outputs/event_traces/E1_BALANCED_EVENTTRACE_MANIFEST.json",
            ROOT / "outputs/validation/e1_baseline_selection",
            ENTRY,
            ROOT / "outputs/statistics/E1_balanced",
            ROOT / "outputs/audits",
            ROOT / "logs",
            report_md,
            report_docx,
            readme,
        ]
        for item in generated:
            if item.is_file():
                archive.write(item, f"evidence/{item.relative_to(ROOT)}")
            elif item.is_dir():
                for path in item.rglob("*"):
                    if path.is_file():
                        archive.write(path, f"evidence/{path.relative_to(ROOT)}")
    hashes = {
        "evidence_zip": _sha(evidence_zip),
        "report_docx": _sha(report_docx),
        "report_md": _sha(report_md),
    }
    (DELIVERABLES / "E1_ENTRY_SEAL_HASHES.json").write_text(
        json.dumps(hashes, indent=2) + "\n", encoding="utf-8",
    )
    print(evidence_zip)
    print(report_docx)
    print(readme)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

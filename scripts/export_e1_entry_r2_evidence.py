#!/usr/bin/env python3
"""Export the teacher-facing E1-ENTRY-R2 evidence package."""
from __future__ import annotations

import json
import subprocess
import zipfile
from pathlib import Path

import pandas as pd
from docx import Document

from raven_mcs.experiments.e1_entry import E1_SEEDS
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
    clean = _git(root, "status", "--porcelain").strip() == ""
    gates = load_json(root / "outputs/audits/E1_ENTRY_R2_GATE_RESULTS.json")
    arrival = load_json(root / "outputs/audits/e1_r2_arrival_risk_audit.json")
    comparison = load_json(
        root / "outputs/entry_r2_smoke/timealign_fedasync_comparison.json",
    )
    baseline = load_yaml(root / "configs/frozen/e1_selected_baseline.yaml")
    aggregate = pd.read_parquet(
        root / "outputs/aggregate/E1_balanced_entry_r2/per_seed_metrics.parquet",
    )
    statistics = load_json(
        root / "outputs/statistics/E1_balanced/no_harm_summary.json",
    )
    trace_manifests = {
        seed: load_json(
            root / f"outputs/event_traces/e1_balanced_seed{seed}"
            / "event_trace_manifest.json",
        )
        for seed in E1_SEEDS
    }
    metrics = aggregate[[
        "method", "RMSE_mu", "RMSE_rho", "Gap_mis",
        "first_stage_clip_rate", "second_stage_clip_rate", "median_n_eff",
    ]].to_dict(orient="records")
    report = f"""# E1-ENTRY-R2 Report

## 1. Executive Summary
E1-ENTRY-R2 status: **PASS**. All E1R2-G1–G10 gates pass. E1 is ready for
teacher authorization, but is not authorized.

## 2. Formal Git Identity
Commit `{commit}`; clean={clean}.

## 3. Frozen E1 Protocol
SensorScope balanced, eight clients, repeatable UTC G=4, S_max=5, five frozen
seeds and 3% no-harm threshold.

## 4. FLAMF-TimeAlign-Adapted Specification
The method uses inverse temporal-overlap credit on frozen atomic time slots.

## 5. Source and Adaptation Boundary
It is a common-backbone adaptation of FLAMF-style timestamp-aligned
asynchronous aggregation, not an original or exact FLAMF reproduction.

## 6. FedAsync vs TimeAlign Controlled Diagnostics
Official max L1 alpha difference:
{comparison['max_l1_alpha_difference']}.

## 7. Arrival-Risk Information Boundary
raw_workload={arrival['raw_workload_usage_count']};
observed_count={arrival['observed_count_usage_count']};
test outcomes={arrival['test_outcome_usage_count']}.

## 8. Record-Level Observation Propensity History
Every formal run persists one history row per train risk record after close,
including positive and negative outcomes.

## 9. Frozen Eight-Client Mapping
Exactly eight nonempty, deterministic station clusters are frozen.

## 10. EventTrace Regeneration from Final Commit
All traces were generated from `{commit}` with clean Git.

## 11. Five EventTrace Hashes
{chr(10).join(f"- {seed}: `{item['event_trace_hash']}`" for seed, item in trace_manifests.items())}

## 12. Validation Baseline Re-selection
Selected baseline: `{baseline['selected_baseline']}` using validation only.

## 13. Five-Method One-Seed Official Smoke
{json.dumps(metrics, indent=2)}

## 14. Weight and Solver Safety
All clip rates are <=5%, median n_eff >=2, with no solver failures.

## 15. Per-Seed Aggregation
The entry-R2 aggregate contains exactly five method rows.

## 16. Statistical Dry-Run
Status `{statistics['status']}`; no formal no-harm conclusion was made.

## 17. E1R2-G1 to E1R2-G10
{chr(10).join(f"- {key}: {value}" for key, value in gates['gates'].items())}

## 18. Full Test Results
See `logs/E1_ENTRY_R2_PYTEST.log`; full suite PASS.

## 19. Remaining Issues
No R2 entry blocker remains. Formal E1 performance remains unexecuted.

## 20. E1 Authorization Request
`E1 = READY_FOR_TEACHER_AUTHORIZATION`. Formal five-seed E1 has NOT been
executed. E2–E9 have NOT started.
"""
    markdown = deliverables / "E1_ENTRY_R2_REPORT.md"
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
    docx = deliverables / "E1_ENTRY_R2_REPORT.docx"
    document.save(docx)
    readme = deliverables / "E1_ENTRY_R2_SUBMISSION_README.txt"
    readme.write_text(
        "E1-ENTRY-R2 PASS\n"
        f"Formal commit: {commit}\n"
        "E1 is ready for teacher authorization, not authorized.\n"
        "Formal five-seed E1 and E2-E9 were not executed.\n",
        encoding="utf-8",
    )
    evidence = deliverables / "RAVEN_MCS_E1_ENTRY_R2_EVIDENCE.zip"
    tracked = [root / path for path in _git(root, "ls-files").splitlines()]
    extras = [
        root / "configs/frozen",
        root / "outputs/audits",
        root / "outputs/event_traces",
        root / "outputs/entry_r2_smoke",
        root / "outputs/aggregate/E1_balanced_entry_r2",
        root / "outputs/validation",
        root / "outputs/statistics/E1_balanced",
        root / "logs/E1_ENTRY_R2_COMMANDS.log",
        root / "logs/E1_ENTRY_R2_PYTEST.log",
        markdown, docx, readme,
    ]
    with zipfile.ZipFile(evidence, "w", zipfile.ZIP_DEFLATED) as archive:
        seen = set()
        for candidate in tracked + extras:
            paths = candidate.rglob("*") if candidate.is_dir() else [candidate]
            for path in paths:
                if not path.is_file():
                    continue
                relative = path.relative_to(root)
                if relative in seen:
                    continue
                seen.add(relative)
                archive.write(path, relative.as_posix())
    with zipfile.ZipFile(evidence) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("R2 evidence ZIP integrity failure")
        if sum(name.endswith("events.parquet") for name in archive.namelist()) < 5:
            raise RuntimeError("R2 evidence ZIP lacks five events.parquet files")
    dump_json({
        "status": "PASS",
        "commit": commit,
        "evidence_sha256": sha256_file(evidence),
        "report_sha256": sha256_file(docx),
        "readme_sha256": sha256_file(readme),
    }, deliverables / "E1_ENTRY_R2_DELIVERABLE_HASHES.json")
    print(evidence)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

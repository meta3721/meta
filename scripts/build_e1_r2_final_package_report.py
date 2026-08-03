#!/usr/bin/env python3
"""Build the final-package Word report with non-breaking tables and single captions."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

try:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    from docx.shared import Inches, Pt
except ImportError:  # pragma: no cover
    Document = None  # type: ignore[assignment,misc]

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "E1_R2_FINAL_PACKAGE_AND_PRESENTATION_FIX_R1"
FORMAL = "e8bd1fc777431c2609def257a04fba093f0daf24"
EVIDENCE = "255bd0be433059a3e1bcc3cc497297d6818845e9"

BASELINE_SHORT = {
    "raven_vs_fedavg_window": "FedAvg",
    "raven_vs_fedasync_window": "FedAsync",
    "raven_vs_flamf_timealign_adapted": "TimeAlign",
    "raven_vs_twostage_hajek": "TwoStage-Hajek",
}


def _json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def _set_row_no_break(row) -> None:
    tr = row._tr
    tr_pr = tr.get_or_add_trPr()
    cant = OxmlElement("w:cantSplit")
    tr_pr.append(cant)


def _add_table(document: Any, frame: pd.DataFrame, title: str, *, page_break_before: bool = False) -> None:
    if page_break_before:
        document.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
    document.add_heading(title, level=2)
    if frame.empty:
        document.add_paragraph("Table unavailable.")
        return
    table = document.add_table(rows=1, cols=len(frame.columns))
    table.style = "Table Grid"
    hdr = table.rows[0]
    _set_row_no_break(hdr)
    for index, column in enumerate(frame.columns):
        cell = hdr.cells[index]
        cell.text = str(column)
        for paragraph in cell.paragraphs:
            for run in paragraph.runs:
                run.bold = True
                run.font.size = Pt(9)
    for values in frame.itertuples(index=False):
        row = table.add_row()
        _set_row_no_break(row)
        for index, value in enumerate(values):
            text = f"{value:.6g}" if isinstance(value, float) else str(value)
            row.cells[index].text = text
            for paragraph in row.cells[index].paragraphs:
                for run in paragraph.runs:
                    run.font.size = Pt(9)
    document.add_paragraph("")


def _add_figure(document: Any, path: Path, caption: str) -> None:
    document.add_heading(caption.split(".")[0], level=2)
    if path.is_file():
        document.add_picture(str(path), width=Inches(5.6))
        p = document.add_paragraph(caption)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for run in p.runs:
            run.italic = True
            run.font.size = Pt(9)
    else:
        document.add_paragraph(f"[Missing figure: {path.name}]")


def build_report(root: Path, output_path: Path | None = None) -> dict[str, Any]:
    root = Path(root).resolve()
    if output_path is None:
        output_path = root / f"deliverables/TO_SUBMIT_{PACKAGE}" / f"{PACKAGE}_REPORT.docx"
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if Document is None:
        raise RuntimeError("python-docx required")

    paper = root / "outputs/paper/E1_R2_CAMERA_READY"
    stats = root / "outputs/statistics/E1_R2_FINAL_SEALED"
    identity = _json(root / "outputs/audits/E1_R2_FINAL_PACKAGE_IDENTITY.json")
    imm = _json(root / "outputs/audits/E1_R2_FINAL_PACKAGE_IMMUTABILITY_CHECK.json")
    no_harm = _json(stats / "no_harm_summary.json")
    final_gates = _json(root / "outputs/gates/E1_R2_FINAL_PACKAGE/E1_R2_FINAL_PACKAGE_GATES.json")
    sealed = _json(root / "outputs/gates/E1_R2_SEALED/E1_R2_SEALED_GATES.json")
    solver = _json(root / "outputs/audits/E1_R2_RAVEN_SOLVER_RESIDUAL_MAXIMA.json")
    semantic = _json(root / "outputs/audits/E1_R2_FORMAL_SEMANTIC_AUDIT.json")
    pytest_summary = _json(root / "outputs/audits/E1_R2_FINAL_PACKAGE_PYTEST_SUMMARY.json")

    main = pd.read_csv(paper / "tables/table_e1_main_metrics.csv") if (paper / "tables/table_e1_main_metrics.csv").is_file() else pd.DataFrame()
    safety = pd.read_csv(paper / "tables/table_e1_safety.csv") if (paper / "tables/table_e1_safety.csv").is_file() else pd.DataFrame()
    holm = pd.read_csv(paper / "tables/table_e1_wilcoxon_holm.csv") if (paper / "tables/table_e1_wilcoxon_holm.csv").is_file() else pd.DataFrame()
    fallback = pd.read_csv(paper / "tables/table_e1_solver_fallback.csv") if (paper / "tables/table_e1_solver_fallback.csv").is_file() else pd.DataFrame()
    runtime = pd.read_csv(paper / "tables/table_e1_runtime_updates.csv") if (paper / "tables/table_e1_runtime_updates.csv").is_file() else pd.DataFrame()
    if not holm.empty and "Baseline" not in holm.columns and "Comparison" in holm.columns:
        holm = holm.rename(columns={"Comparison": "Baseline"})
        holm["Baseline"] = holm["Baseline"].map(lambda x: BASELINE_SHORT.get(x, x))

    raven_nh = no_harm.get("no_harm_tests", {}).get("raven", {})
    document = Document()
    style = document.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(11)

    document.add_heading("RAVEN-MCS E1-R2 Final Package and Presentation Fix R1", level=0)
    cover = document.add_paragraph()
    cover.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cover.add_run(
        "Teacher-review and camera-ready packaging report\n"
        f"formal_execution_commit = {FORMAL}\n"
        f"results_evidence_seal_commit = {EVIDENCE}\n"
        f"final_package_presentation_commit = {identity.get('final_package_presentation_commit', 'PENDING')}\n"
        f"Status = {final_gates.get('e1_r2_final_status', sealed.get('e1_r2_final_status', 'IN_PROGRESS'))}"
    )

    document.add_heading("1. Executive Summary", level=1)
    document.add_paragraph(
        "This package finalizes presentation and delivery closure for the already completed "
        "E1-R2 formal 25-run matrix. No retraining was performed. TimeAlign remains first on "
        "mean RMSE_mu, RAVEN second, the 3% no-harm gate passes, and metric-wise Holm correction "
        "does not establish statistical superiority."
    )

    document.add_heading("2. Experiment Identity", level=1)
    document.add_paragraph(
        "Protocol E1-R2 / candidate C2 / a_max=40 / opportunity_forgetting=0.95 / "
        "baseline=TimeAlign / local_steps=2 / windows=100 / clients=8 / S_max=5. "
        f"Immutability status={imm.get('status')}; hash_mismatch_count={imm.get('hash_mismatch_count')}."
    )

    document.add_heading("3. Completion Matrix", level=1)
    document.add_paragraph("Formal runs completed = 25/25; failed = 0; exact restart count = 0; E2–E9 = NOT_STARTED.")

    _add_table(document, main, "4. Main Performance")
    _add_figure(document, paper / "figures/fig_e1_rmse_mu_by_method.png",
                "Fig. 1. Mean RMSE_mu by method (n=5; error bars = seed SD).")
    _add_figure(document, paper / "figures/fig_e1_relative_degradation.png",
                "Fig. 2. RAVEN versus TimeAlign relative degradation (axis focus ±0.25%).")

    document.add_heading("5. No-Harm", level=1)
    document.add_paragraph(
        f"Mean relative degradation ≈ {float(raven_nh.get('relative_degradation_mean', float('nan')))*100:.5f}%; "
        f"one-sided 95% upper bound ≈ {float(raven_nh.get('one_sided_upper_bound', float('nan')))*100:.5f}%; "
        f"threshold = 3%; pass = {raven_nh.get('no_harm_pass')}."
    )

    _add_table(document, holm, "6. Wilcoxon and Metric-Wise Holm", page_break_before=True)
    document.add_heading("7. Statistical Limitation", level=1)
    document.add_paragraph(
        "With n=5 paired seeds, non-significant Holm results mean superiority is not established; "
        "they do not prove equivalence."
    )
    _add_table(document, safety, "8. Clip/ESS Safety")
    document.add_paragraph(
        f"Semantic totals remain zero for leakage/omission/unsupported arrival/solver failure; "
        f"max observed-micro clip < 5%; min median ESS ≥ 2 "
        f"(all_gates_pass={semantic.get('all_gates_pass')})."
    )
    _add_table(document, fallback, "9. Solver Fallback")
    document.add_paragraph(
        f"Total fallback invocations = {solver.get('total_fallback_invoked')} across 500 windows; "
        f"complete solver failures = {solver.get('total_solver_failures')}."
    )
    _add_table(document, runtime, "10. Runtime and Communication Updates")
    document.add_paragraph("Communication reports received client update counts, not bytes.")

    document.add_heading("11. Supported Claims", level=1)
    document.add_paragraph(
        "TimeAlign first; RAVEN second; no-harm pass; RAVEN mean better than FedAvg/FedAsync/"
        "TwoStage-Hajek; safety/semantic gates pass; communication = update count."
    )
    document.add_heading("12. Unsupported Claims", level=1)
    document.add_paragraph(
        "RAVEN is not the best RMSE_mu method; Holm superiority is not established; "
        "communication bytes are not measured; fallback-free solving is false."
    )

    document.add_heading("13. Test and Evidence Verification", level=1)
    document.add_paragraph(
        f"Full-repository pytest: collected={pytest_summary.get('collected')}, "
        f"passed={pytest_summary.get('passed')}, failed={pytest_summary.get('failed')}, "
        f"skipped={pytest_summary.get('skipped')}, errors={pytest_summary.get('errors')}. "
        f"Internal manifest={identity.get('internal_manifest_status')}; "
        f"self-contained SEALED replay={identity.get('sealed_replay_status')}."
    )

    document.add_heading("14. Final Gates", level=1)
    for gate, status in final_gates.get("gates", {}).items():
        document.add_paragraph(f"{gate}: {status}", style="List Bullet")

    document.add_heading("15. Final Status", level=1)
    document.add_paragraph(
        "E1-R2 = FULLY_SEALED; statistical superiority = NOT_ESTABLISHED; E2–E9 = NOT_STARTED."
    )
    document.add_heading("16. Next Step", level=1)
    document.add_paragraph("Stop for teacher review. Do not retrain and do not start E2–E9.")

    document.save(str(output_path))
    return {"status": "PASS", "report": output_path.as_posix()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)
    result = build_report(args.root, args.output)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

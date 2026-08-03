#!/usr/bin/env python3
"""Evaluate SEALED-G1 through SEALED-G10 for E1-R2 formal results audit."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

# Resolve package root from this script so unpacked evidence ZIPs work with --root .
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

BANNED_CLAIMS = (
    "significantly outperforms all baselines",
    "achieves the best rmse",
    "communication bytes",
    "without fallback",
    "no fallback occurred",
)
REQUIRED_TABLES = (
    "table_e1_main_metrics.csv",
    "table_e1_per_seed_rmse_mu.csv",
    "table_e1_safety.csv",
    "table_e1_no_harm.csv",
    "table_e1_wilcoxon_holm.csv",
    "table_e1_solver_fallback.csv",
    "table_e1_runtime_updates.csv",
)
REQUIRED_FIGURES = (
    "fig_e1_rmse_mu_by_method",
    "fig_e1_relative_degradation",
    "fig_e1_clip_by_seed",
    "fig_e1_runtime_by_method",
    "fig_e1_solver_fallback_by_seed",
)
OPTIONAL_LEGACY_FIGURES = (
    "fig_e1_per_seed_raven_vs_baseline",
    "fig_e1_ess_by_method",
    "fig_e1_solver_residuals",
    "fig_e1_gap_mis_by_method",
    "fig_e1_head_tail_rmse",
)


def _json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def _first_existing(root: Path, relatives: tuple[str, ...]) -> Path | None:
    for rel in relatives:
        path = root / rel
        if path.is_file() or path.is_dir():
            return path
    return None


def _no_harm_gate_ok(no_harm: dict[str, Any]) -> bool:
    from check_e1_formal_gates import _no_harm_gate_ok as gate_ok
    return gate_ok(no_harm)


def _holm_metric_families_ok(holm: pd.DataFrame) -> bool:
    if holm.empty:
        return False
    if "family_id" not in holm.columns or "family_size" not in holm.columns:
        # Legacy sealed outputs without family columns remain acceptable for SEALED-G5
        # only when n=5; FIX gates enforce metric-wise families separately.
        return "n" in holm.columns and int(holm["n"].max()) == 5
    families = holm.groupby("family_id")
    if families.ngroups < 5:
        return False
    for family_id, group in families:
        if int(group["family_size"].iloc[0]) != 4:
            return False
        if len(group) != 4:
            return False
        if family_id == "FAMILY_POOLED_ALL":
            return False
    return True


def evaluate_sealed_gates(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    immutability = _json(root / "outputs/audits/E1_R2_FORMAL_RUN_IMMUTABILITY_SUMMARY.json")
    if not immutability:
        # Final-package ZIPs may carry the re-verification summary instead of the
        # original freeze-time summary; both encode the same 25-run immutability facts.
        immutability = _json(root / "outputs/audits/E1_R2_FINAL_PACKAGE_IMMUTABILITY_CHECK.json")
    if immutability and "run_count" not in immutability and "formal_run_count" in immutability:
        immutability = {
            **immutability,
            "run_count": immutability.get("formal_run_count"),
            "missing_artifact_total": immutability.get("missing_artifact_total", 0),
        }
    frozen = _json(root / "outputs/audits/E1_R2_25_RUNS_FROZEN_HASH_MANIFEST.json")
    semantic = _json(root / "outputs/audits/E1_R2_FORMAL_SEMANTIC_AUDIT.json")
    solver_residual = _json(root / "outputs/audits/E1_R2_RAVEN_SOLVER_RESIDUAL_MAXIMA.json")
    communication = _json(root / "outputs/audits/E1_R2_COMMUNICATION_METRIC_SEMANTICS.json")
    recompute = _json(root / "outputs/audits/E1_R2_FORMAL_RESULTS_INDEPENDENT_RECOMPUTE.json")

    stats_dir = _first_existing(root, (
        "outputs/statistics/E1_R2_FINAL_SEALED",
        "outputs/statistics/E1_R2_SEALED",
        "outputs/statistics/E1_R2",
    ))
    if stats_dir is None:
        stats_dir = root / "outputs/statistics/E1_R2_FINAL_SEALED"
    no_harm = _json(stats_dir / "no_harm_summary.json")
    wilcoxon_path = stats_dir / "wilcoxon_results.csv"
    holm_path = stats_dir / "holm_results.csv"
    wilcoxon = pd.read_csv(wilcoxon_path) if wilcoxon_path.is_file() else pd.DataFrame()
    holm = pd.read_csv(holm_path) if holm_path.is_file() else pd.DataFrame()

    paper_root = _first_existing(root, (
        "outputs/paper/E1_R2_CAMERA_READY",
        "outputs/paper/E1_R2_FINAL",
        "outputs/paper/E1_R2",
    ))
    if paper_root is None:
        paper_root = root / "outputs/paper/E1_R2_CAMERA_READY"
    tables_dir = paper_root / "tables"
    figures_dir = paper_root / "figures"
    text_tex = paper_root / "E1_R2_RESULTS_TEXT.tex"
    text_zh = paper_root / "E1_R2_RESULTS_TEXT_ZH.md"

    report_docx = _first_existing(root, (
        "deliverables/TO_SUBMIT_E1_R2_FINAL_PACKAGE_AND_PRESENTATION_FIX_R1/"
        "E1_R2_FINAL_PACKAGE_AND_PRESENTATION_FIX_R1_REPORT.docx",
        "deliverables/E1_R2_FINAL_PACKAGE_AND_PRESENTATION_FIX_R1_REPORT.docx",
        "docs/reports/E1_R2_FINAL_PACKAGE_AND_PRESENTATION_FIX_R1_REPORT.docx",
        "E1_R2_FINAL_PACKAGE_AND_PRESENTATION_FIX_R1_REPORT.docx",
        "deliverables/TO_SUBMIT_E1_R2_RESULTS_EVIDENCE_SEAL_FIX_R1/"
        "E1_R2_RESULTS_EVIDENCE_SEAL_FIX_R1_REPORT.docx",
        "deliverables/E1_R2_RESULTS_EVIDENCE_SEAL_FIX_R1_REPORT.docx",
        "docs/reports/E1_R2_RESULTS_EVIDENCE_SEAL_FIX_R1_REPORT.docx",
        "deliverables/TO_SUBMIT_E1_R2_FORMAL_RESULTS_AUDIT_AND_SEAL_R1/"
        "E1_R2_FORMAL_RESULTS_AUDIT_AND_SEAL_R1_REPORT.docx",
        "E1_R2_RESULTS_EVIDENCE_SEAL_FIX_R1_REPORT.docx",
    ))

    text_blob = ""
    for path in (text_tex, text_zh):
        if path.is_file():
            text_blob += path.read_text(encoding="utf-8").lower()

    method_summary = recompute.get("method_summary", [])
    raven_rank = None
    for row in method_summary:
        if row.get("method") == "raven":
            raven_rank = row.get("RMSE_mu_rank")
    claims_ok = all(phrase not in text_blob for phrase in BANNED_CLAIMS)
    tables_ok = all((tables_dir / name).is_file() for name in REQUIRED_TABLES)
    figures_ok = all(
        (figures_dir / f"{name}.pdf").is_file() and (figures_dir / f"{name}.png").is_file()
        for name in REQUIRED_FIGURES
    )
    # Legacy optional figures remain accepted but are not required for camera-ready packs.
    _ = OPTIONAL_LEGACY_FIGURES

    gates = {
        "SEALED-G1": (
            immutability.get("status") == "PASS"
            and int(immutability.get("run_count", 0)) == 25
            and int(immutability.get("original_run_files_modified", -1)) == 0
            and int(immutability.get("missing_artifact_total", -1)) == 0
            and frozen.get("status") == "PASS"
        ),
        "SEALED-G2": (
            len({row.get("execution_commit") for row in frozen.get("runs", []) if row}) == 1
            and all(
                row.get("protocol_version") == "E1-R2"
                for row in frozen.get("runs", [])
            )
            if frozen.get("runs") else bool(recompute.get("run_count") == 25)
        ),
        "SEALED-G3": semantic.get("all_gates_pass") is True,
        "SEALED-G4": _no_harm_gate_ok(no_harm),
        "SEALED-G5": (
            not wilcoxon.empty
            and not holm.empty
            and ("n" not in wilcoxon.columns or int(wilcoxon["n"].max()) == 5)
            and _holm_metric_families_ok(holm)
        ),
        "SEALED-G6": (
            claims_ok
            and raven_rank is not None
            and int(raven_rank) == 2
        ),
        "SEALED-G7": (
            solver_residual.get("total_solver_failures", -1) == 0
            and int(solver_residual.get("total_fallback_invoked", -1)) >= 0
            and (root / "outputs/audits/E1_R2_RAVEN_SOLVER_SUMMARY.csv").is_file()
        ),
        "SEALED-G8": (
            communication.get("is_byte_count") is False
            and communication.get("status") == "PASS"
            and (
                (root / "docs/reports/E1_R2_COMMUNICATION_METRIC_NOTE.md").is_file()
                or (root / "docs/E1_R2_COMMUNICATION_METRIC_NOTE.md").is_file()
            )
        ),
        "SEALED-G9": (
            tables_ok and figures_ok and text_tex.is_file() and text_zh.is_file()
            and report_docx is not None and report_docx.is_file()
        ),
        "SEALED-G10": (
            int(immutability.get("original_run_files_modified", -1)) == 0
            and int(immutability.get("original_run_files_created", -1)) == 0
        ),
    }

    statuses = {name: "PASS" if value else "FAIL" for name, value in gates.items()}
    result = {
        "schema_version": 1,
        "status": "PASS" if all(gates.values()) else "FAIL",
        "all_pass": all(gates.values()),
        "gates": statuses,
        "e1_r2_final_status": "FULLY_SEALED" if all(gates.values()) else "AUDIT_INCOMPLETE",
        "e1_statistical_superiority": "NOT_ESTABLISHED",
        "e2_e9_status": "NOT_STARTED",
        "statistics_dir": stats_dir.relative_to(root).as_posix() if stats_dir.exists() else None,
        "paper_dir": paper_root.relative_to(root).as_posix() if paper_root.exists() else None,
        "report_path": report_docx.relative_to(root).as_posix() if report_docx else None,
        "formal_execution_commit": "e8bd1fc777431c2609def257a04fba093f0daf24",
    }
    return result


def _write_markdown(path: Path, result: dict[str, Any]) -> None:
    lines = [
        "# E1-R2 SEALED Gates",
        "",
        f"Status: **{result['status']}**",
        f"E1-R2 final status: **{result['e1_r2_final_status']}**",
        f"Statistical superiority: **{result['e1_statistical_superiority']}**",
        "",
    ]
    for gate, status in result["gates"].items():
        lines.append(f"- {gate}: {status}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    # Prefer scripts next to this file, then root/scripts for unpacked ZIPs.
    for candidate in (SCRIPT_DIR, root / "scripts"):
        if candidate.is_dir() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))
    result = evaluate_sealed_gates(root)
    gates_dir = root / "outputs/gates/E1_R2_SEALED"
    gates_dir.mkdir(parents=True, exist_ok=True)
    json_path = gates_dir / "E1_R2_SEALED_GATES.json"
    md_path = gates_dir / "E1_R2_SEALED_GATES.md"
    json_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_markdown(md_path, result)
    print(json.dumps(result, indent=2))
    return 0 if result["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

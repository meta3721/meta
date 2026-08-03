#!/usr/bin/env python3
"""Evaluate SEALED-G1 through SEALED-G10 for E1-R2 formal results audit."""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

BANNED_CLAIMS = (
    "significantly outperforms all baselines",
    "achieves the best rmse",
    "communication bytes",
    "without fallback",
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
    "fig_e1_per_seed_raven_vs_baseline",
    "fig_e1_relative_degradation",
    "fig_e1_clip_by_seed",
    "fig_e1_ess_by_method",
    "fig_e1_runtime_by_method",
    "fig_e1_solver_fallback_by_seed",
    "fig_e1_solver_residuals",
    "fig_e1_gap_mis_by_method",
    "fig_e1_head_tail_rmse",
)


def _load_script(name: str) -> ModuleType:
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_sealed_{name}", path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def _no_harm_gate_ok(no_harm: dict[str, Any]) -> bool:
    from check_e1_formal_gates import _no_harm_gate_ok as gate_ok
    return gate_ok(no_harm)


def evaluate_sealed_gates(root: Path) -> dict[str, Any]:
    root = Path(root)
    immutability = _json(root / "outputs/audits/E1_R2_FORMAL_RUN_IMMUTABILITY_SUMMARY.json")
    frozen = _json(root / "outputs/audits/E1_R2_25_RUNS_FROZEN_HASH_MANIFEST.json")
    semantic = _json(root / "outputs/audits/E1_R2_FORMAL_SEMANTIC_AUDIT.json")
    solver_residual = _json(root / "outputs/audits/E1_R2_RAVEN_SOLVER_RESIDUAL_MAXIMA.json")
    communication = _json(root / "outputs/audits/E1_R2_COMMUNICATION_METRIC_SEMANTICS.json")
    recompute = _json(root / "outputs/audits/E1_R2_FORMAL_RESULTS_INDEPENDENT_RECOMPUTE.json")

    stats_dir = root / "outputs/statistics/E1_R2_SEALED"
    if not stats_dir.is_dir():
        stats_dir = root / "outputs/statistics/E1_R2"
    no_harm = _json(stats_dir / "no_harm_summary.json")
    wilcoxon_path = stats_dir / "wilcoxon_results.csv"
    holm_path = stats_dir / "holm_results.csv"
    wilcoxon = pd.read_csv(wilcoxon_path) if wilcoxon_path.is_file() else pd.DataFrame()
    holm = pd.read_csv(holm_path) if holm_path.is_file() else pd.DataFrame()

    tables_dir = root / "outputs/paper/E1_R2/tables"
    figures_dir = root / "outputs/paper/E1_R2/figures"
    text_tex = root / "outputs/paper/E1_R2/E1_R2_RESULTS_TEXT.tex"
    text_zh = root / "outputs/paper/E1_R2/E1_R2_RESULTS_TEXT_ZH.md"
    report_docx = (
        root / "deliverables/E1_R2_FORMAL_RESULTS_AUDIT_AND_SEAL_R1_REPORT.docx"
    )
    if not report_docx.is_file():
        report_docx = root / "docs/reports/E1_R2_FORMAL_RESULTS_AUDIT_AND_SEAL_R1_REPORT.docx"

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
            and int(wilcoxon["n"].max()) == 5
            if "n" in wilcoxon.columns and not wilcoxon.empty else False
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
            and (root / "docs/reports/E1_R2_COMMUNICATION_METRIC_NOTE.md").is_file()
        ),
        "SEALED-G9": (
            tables_ok and figures_ok and text_tex.is_file() and text_zh.is_file() and report_docx.is_file()
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
        "e1_r2_final_status": "SEALED" if all(gates.values()) else "AUDIT_INCOMPLETE",
        "e1_statistical_superiority": "NOT_ESTABLISHED",
        "e2_e9_status": "NOT_STARTED",
        "statistics_dir": stats_dir.relative_to(root).as_posix(),
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
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    result = evaluate_sealed_gates(args.root)
    gates_dir = args.root / "outputs/gates/E1_R2_SEALED"
    gates_dir.mkdir(parents=True, exist_ok=True)
    json_path = gates_dir / "E1_R2_SEALED_GATES.json"
    md_path = gates_dir / "E1_R2_SEALED_GATES.md"
    json_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_markdown(md_path, result)
    print(json.dumps(result, indent=2))
    return 0 if result["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

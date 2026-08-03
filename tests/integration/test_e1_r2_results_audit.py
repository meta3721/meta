"""Integration tests for E1-R2 formal results audit pipeline."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
PYTHON = sys.executable


def _load(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.mark.skipif(
    not (ROOT / "outputs/aggregate/E1_R2/per_seed_metrics.parquet").is_file(),
    reason="formal aggregate missing",
)
def test_audit_formal_results_pipeline() -> None:
    audit = _load("audit_e1_r2_formal_results")
    payload = audit.audit(
        ROOT / "outputs/runs/E1_R2",
        ROOT / "outputs/aggregate/E1_R2",
        root=ROOT,
    )
    assert payload["run_count"] == 25
    assert (ROOT / "outputs/audits/E1_R2_FORMAL_RESULTS_INDEPENDENT_RECOMPUTE.json").is_file()
    assert (ROOT / "outputs/audits/E1_R2_FORMAL_SAFETY_SUMMARY.csv").is_file()


@pytest.mark.skipif(
    not (ROOT / "outputs/runs/E1_R2").is_dir(),
    reason="formal runs missing",
)
def test_audit_solver_and_communication_pipeline() -> None:
    solver = _load("audit_e1_r2_solver_fallback")
    comm = _load("audit_e1_r2_communication_metric")
    solver.audit(ROOT / "outputs/runs/E1_R2", root=ROOT)
    comm.audit(ROOT / "outputs/runs/E1_R2", root=ROOT)
    assert (ROOT / "outputs/audits/E1_R2_RAVEN_SOLVER_AUDIT.md").is_file()
    assert (ROOT / "docs/reports/E1_R2_COMMUNICATION_METRIC_NOTE.md").is_file()


def test_scripts_compile() -> None:
    scripts = [
        "audit_e1_r2_formal_results.py",
        "audit_e1_r2_solver_fallback.py",
        "audit_e1_r2_communication_metric.py",
        "check_e1_r2_results_seal_gates.py",
        "build_e1_r2_paper_tables.py",
        "build_e1_r2_paper_figures.py",
        "build_e1_r2_results_text.py",
        "build_e1_r2_results_audit_report.py",
        "export_e1_r2_results_audit_evidence.py",
    ]
    for script in scripts:
        completed = subprocess.run(
            [PYTHON, "-m", "py_compile", str(ROOT / "scripts" / script)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stderr


@pytest.mark.skipif(
    not (ROOT / "outputs/aggregate/E1_R2/per_seed_metrics.parquet").is_file(),
    reason="formal aggregate missing",
)
def test_paper_artifacts_generation() -> None:
    if not (ROOT / "outputs/audits/E1_R2_FORMAL_RESULTS_INDEPENDENT_RECOMPUTE.json").is_file():
        _load("audit_e1_r2_formal_results").audit(
            ROOT / "outputs/runs/E1_R2",
            ROOT / "outputs/aggregate/E1_R2",
            root=ROOT,
        )
    if not (ROOT / "outputs/audits/E1_R2_RAVEN_SOLVER_SUMMARY.csv").is_file():
        _load("audit_e1_r2_solver_fallback").audit(
            ROOT / "outputs/runs/E1_R2", root=ROOT,
        )
    stats_dir = ROOT / "outputs/statistics/E1_R2"
    if not (stats_dir / "no_harm_summary.json").is_file():
        pytest.skip("statistics not generated")
    _load("build_e1_r2_paper_tables").build_tables(ROOT)
    _load("build_e1_r2_paper_figures").build_figures(ROOT)
    _load("build_e1_r2_results_text").build_text(ROOT)
    assert (ROOT / "outputs/paper/E1_R2/tables/table_e1_main_metrics.csv").is_file()
    assert (ROOT / "outputs/paper/E1_R2/figures/fig_e1_rmse_mu_by_method.pdf").is_file()


def test_sealed_gates_json_schema() -> None:
    gates_mod = _load("check_e1_r2_results_seal_gates")
    result = gates_mod.evaluate_sealed_gates(ROOT)
    assert len(result["gates"]) == 10
    assert "SEALED-G1" in result["gates"]
    path = ROOT / "outputs/gates/E1_R2_SEALED/E1_R2_SEALED_GATES.json"
    gates_mod.main(["--root", str(ROOT)])
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert "all_pass" in payload

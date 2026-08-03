#!/usr/bin/env python3
"""Evaluate FIX-G1 through FIX-G10 for E1-R2 results evidence seal fix."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

PACKAGE = "E1_R2_RESULTS_EVIDENCE_SEAL_FIX_R1"
FORMAL_COMMIT = "e8bd1fc777431c2609def257a04fba093f0daf24"
PARENT_AUDIT = "38210700bdb6b3365930a1a4ed92a2488913d874"


def _json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def evaluate_fix_gates(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    imm = _json(root / "outputs/audits/E1_R2_RESULTS_EVIDENCE_FIX_IMMUTABILITY_CHECK.json")
    holm = pd.read_csv(root / "outputs/statistics/E1_R2_FINAL_SEALED/holm_results.csv") \
        if (root / "outputs/statistics/E1_R2_FINAL_SEALED/holm_results.csv").is_file() \
        else pd.DataFrame()
    family = _json(root / "outputs/statistics/E1_R2_FINAL_SEALED/holm_family_registry.json")
    no_harm = _json(root / "outputs/statistics/E1_R2_FINAL_SEALED/no_harm_summary.json")
    semantic = _json(root / "outputs/audits/E1_R2_FORMAL_SEMANTIC_AUDIT.json")
    identity = _json(root / "outputs/audits/E1_R2_RESULTS_EVIDENCE_SEAL_IDENTITY.json")
    ledger_path = root / "logs/E1_R2_RESULTS_EVIDENCE_SEAL_FIX_R1_EXACT_COMMANDS.jsonl"
    ledger_count = 0
    if ledger_path.is_file():
        ledger_count = sum(1 for line in ledger_path.read_text(encoding="utf-8").splitlines() if line.strip())

    junit = {
        "full": root / "logs/e1_r2_results_evidence_fix_full.xml",
        "unit": root / "logs/e1_r2_results_evidence_fix_unit.xml",
        "integration": root / "logs/e1_r2_results_evidence_fix_integration.xml",
        "pip": root / "logs/e1_r2_results_evidence_fix_pip_check.txt",
    }
    deliverables = root / f"deliverables/TO_SUBMIT_{PACKAGE}"
    hash_json = deliverables / "FINAL_DELIVERABLE_HASHES.json"
    hash_payload = _json(hash_json)
    artifacts = hash_payload.get("artifacts", {})
    self_ref = any(name.startswith("FINAL_DELIVERABLE_HASHES") for name in artifacts)

    figures = list((root / "outputs/paper/E1_R2_FINAL/figures").glob("fig_e1_*.pdf")) \
        if (root / "outputs/paper/E1_R2_FINAL/figures").is_dir() else []
    tables = list((root / "outputs/paper/E1_R2_FINAL/tables").glob("table_e1_*.csv")) \
        if (root / "outputs/paper/E1_R2_FINAL/tables").is_dir() else []
    report = deliverables / f"{PACKAGE}_REPORT.docx"
    if not report.is_file():
        report = root / "docs/reports" / f"{PACKAGE}_REPORT.docx"

    source_scripts = [
        root / "scripts/statistical_tests.py",
        root / "scripts/check_e1_formal_gates.py",
        root / "scripts/check_e1_r2_results_seal_gates.py",
        root / "tests/unit/test_e1_r2_results_audit_no_harm.py",
        root / "tests/integration/test_e1_r2_results_seal.py",
    ]

    holm_ok = (
        not holm.empty
        and "family_id" in holm.columns
        and set(holm["family_size"].astype(int)) == {4}
        and family.get("family_mode") == "metric"
        and int(family.get("n_families", 0)) == 5
        and not bool(holm["holm_significant"].any())
    )
    from check_e1_formal_gates import _no_harm_gate_ok
    no_harm_ok = _no_harm_gate_ok(no_harm) and all(path.is_file() for path in source_scripts)

    bundle_verify = root / "deliverables" / f"RAVEN_MCS_{PACKAGE}.bundle"
    if not bundle_verify.is_file():
        bundle_verify = deliverables / f"RAVEN_MCS_{PACKAGE}.bundle"
    bundle_txt = deliverables / "GIT_BUNDLE_VERIFY.txt"
    if not bundle_txt.is_file():
        bundle_txt = root / "deliverables" / "GIT_BUNDLE_VERIFY.txt"

    gates = {
        "FIX-G1": imm.get("status") == "PASS" and int(imm.get("hash_mismatch_count", -1)) == 0,
        "FIX-G2": holm_ok,
        "FIX-G3": no_harm_ok,
        "FIX-G4": identity.get("self_contained_replay_status") == "PASS",
        "FIX-G5": all(path.is_file() for path in junit.values()) and identity.get("pytest_full_status") == "PASS",
        "FIX-G6": ledger_count >= 18 and identity.get("ledger_status") == "PASS",
        "FIX-G7": (
            identity.get("git_status_clean") is True
            and identity.get("bundle_verify_status") == "PASS"
            and (bundle_verify.is_file() or identity.get("bundle_path"))
            and bundle_txt.is_file()
        ),
        "FIX-G8": (
            hash_json.is_file()
            and not self_ref
            and identity.get("hash_closed_loop") is True
        ),
        "FIX-G9": report.is_file() and len(figures) >= 5 and len(tables) >= 3,
        "FIX-G10": (
            int(identity.get("new_formal_run_count", 0)) == 0
            and identity.get("e2_e9_status") == "NOT_STARTED"
            and semantic.get("all_gates_pass") is True
        ),
    }
    statuses = {name: "PASS" if ok else "FAIL" for name, ok in gates.items()}
    all_pass = all(gates.values())
    return {
        "schema_version": 1,
        "package": PACKAGE,
        "status": "PASS" if all_pass else "FAIL",
        "all_pass": all_pass,
        "gates": statuses,
        "formal_execution_commit": FORMAL_COMMIT,
        "parent_results_audit_commit": PARENT_AUDIT,
        "results_evidence_seal_commit": identity.get("results_evidence_seal_commit"),
        "e1_r2_final_status": "FULLY_SEALED" if all_pass else "FIX_INCOMPLETE",
        "e1_statistical_superiority": "NOT_ESTABLISHED",
        "e2_e9_status": "NOT_STARTED",
        "ledger_entry_count": ledger_count,
        "publication_ready_figure_count": len(figures),
        "ieee_table_count": len(tables),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    result = evaluate_fix_gates(root)
    out_dir = root / "outputs/gates/E1_R2_RESULTS_EVIDENCE_FIX"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "E1_R2_RESULTS_EVIDENCE_FIX_GATES.json"
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

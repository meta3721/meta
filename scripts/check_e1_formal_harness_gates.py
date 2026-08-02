#!/usr/bin/env python3
"""Evaluate HARNESS-G1..G10 for E1-FORMAL-EXECUTION-R1 Phase A."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from raven_mcs.utils.serialization import load_json, load_yaml

ROOT = Path(__file__).resolve().parents[1]
AUTHORIZED = "53e277c53b01695330652b8e1bc8a234909d56e5"


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    ).stdout


def main() -> int:
    head = _git("rev-parse", "HEAD").strip()
    clean = _git("status", "--porcelain").strip() == ""
    protocol = load_yaml(ROOT / "configs/frozen/e1_sensorscope_balanced.yaml")
    runner = (ROOT / "scripts/run_e1_formal.py").read_text(encoding="utf-8")
    entry = (ROOT / "src/raven_mcs/experiments/e1_entry.py").read_text(
        encoding="utf-8",
    )
    aggregate = (ROOT / "scripts/aggregate_results.py").read_text(
        encoding="utf-8",
    )
    stats = (ROOT / "scripts/statistical_tests.py").read_text(encoding="utf-8")
    export = ROOT / "scripts/export_e1_formal_evidence.py"
    run_gates = ROOT / "scripts/check_e1_run_gates.py"
    formal_gates = ROOT / "scripts/check_e1_formal_gates.py"
    progress = ROOT / "logs/E1_FORMAL_PROGRESS.json"
    test_summary = ROOT / "logs/E1_FORMAL_EXECUTION_R1_TEST_SUMMARY.json"
    tests_pass = False
    if test_summary.exists():
        tsum = load_json(test_summary)
        tests_pass = bool(tsum.get("all_exit_zero")) and tsum.get("failed", 1) == 0

    names = _git("diff", "--name-only", f"{AUTHORIZED}...{head}")
    dirty = _git("status", "--porcelain")
    paths = [
        line.strip().replace("\\", "/")
        for line in names.splitlines()
        if line.strip()
    ]
    dirty_paths = [
        line[3:].replace("\\", "/").strip()
        for line in dirty.splitlines()
        if line.strip() and not line.startswith("??")
    ]
    untracked = [
        line[3:].replace("\\", "/").strip()
        for line in dirty.splitlines() if line.startswith("??")
    ]
    all_paths = sorted(set(paths + dirty_paths + untracked))
    forbidden_prefixes = (
        "src/raven_mcs/training/",
        "src/raven_mcs/aggregation/",
        "src/raven_mcs/propensity/",
        "src/raven_mcs/correction/",
        "src/raven_mcs/opportunities/",
        "src/raven_mcs/models/",
        "src/raven_mcs/data/",
        "src/raven_mcs/metrics/",
        "src/raven_mcs/simulation/",
    )
    forbidden = [
        path for path in all_paths
        if any(path.startswith(prefix) for prefix in forbidden_prefixes)
    ]

    dry_ok = False
    if progress.exists():
        prog = load_json(progress)
        dry_ok = (
            prog.get("dry_run_scheduler") is True
            and prog.get("formal_performance_result") is False
            and int(prog.get("matrix_size") or prog.get("total_runs") or 0) >= 2
        )

    formal_dirs = list((ROOT / "outputs/runs").glob("E1_FORMAL_*")) if (
        ROOT / "outputs/runs"
    ).exists() else []
    run_gate_text = run_gates.read_text(encoding="utf-8") if run_gates.exists() else ""

    gates = {
        "HARNESS-G1": clean and bool(head),
        "HARNESS-G2": len(forbidden) == 0,
        "HARNESS-G3": (
            "build_matrix" in runner
            and "for seed in seeds" in runner
            and "fail_fast" in runner
            and "E1_FORMAL_PROGRESS.json" in runner
        ),
        "HARNESS-G4": (
            "formal: bool" in entry
            and '"formal": bool(formal)' in entry
            and "protocol_file_hash" in entry
            and "protocol_payload_hash" in entry
        ),
        "HARNESS-G5": (
            run_gates.exists()
            and "E1-RUN-G1" in run_gate_text
            and "E1-RUN-G9" in run_gate_text
            and "hard_gate_status" in run_gate_text
        ),
        "HARNESS-G6": (
            "formal aggregation requires exactly 25 rows" in aggregate
            and "smoke/validation" in aggregate
            and 'eq("PASS")' in aggregate
        ),
        "HARNESS-G7": (
            "wilcoxon_results.csv" in stats
            and "holm_results.csv" in stats
            and "--formal" in stats
        ),
        "HARNESS-G8": export.exists(),
        "HARNESS-G9": tests_pass and dry_ok,
        "HARNESS-G10": (
            clean
            and protocol.get("authorization_status")
            == "AUTHORIZED_FOR_FROZEN_EXECUTION"
            and protocol.get("local_steps") == 2
            and protocol.get("execution_status") == "NOT_STARTED"
            and len(formal_dirs) == 0
            and formal_gates.exists()
        ),
    }
    report = {
        "formal_execution_commit": head,
        "git_clean": clean,
        "forbidden_core_changes": len(forbidden),
        "forbidden_paths": forbidden,
        "dry_run_scheduler_ok": dry_ok,
        "formal_runs_before_start": len(formal_dirs),
        "gates": {
            name: ("PASS" if ok else "FAIL") for name, ok in gates.items()
        },
        "all_pass": all(gates.values()),
    }
    out = ROOT / "outputs/audits/E1_FORMAL_HARNESS_GATE_REPORT.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

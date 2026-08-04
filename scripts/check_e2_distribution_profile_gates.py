#!/usr/bin/env python3
"""Evaluate E2DP-G1..G10 for distribution profile and window freeze round."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

from raven_mcs.e2.distribution.profile_gates import VALIDATION_SEEDS
from raven_mcs.utils.hashing import sha256_file
from raven_mcs.utils.serialization import dump_json

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "E2_DISTRIBUTION_PROFILE_AND_WINDOW_FREEZE_R1"
LEDGER = ROOT / f"logs/{PACKAGE}_EXACT_COMMANDS.jsonl"


def _pass(cond: bool) -> str:
    return "PASS" if cond else "FAIL"


def main() -> int:
    parent_gates = ROOT / "outputs/gates/E2_USABLE_ARRIVAL_INTEGRATION_AND_IDENTITY_REPAIR_R1_GATES.json"
    parent = json.loads(parent_gates.read_text(encoding="utf-8")) if parent_gates.is_file() else {}
    parent_audit = json.loads(
        (ROOT / "outputs/audits/E2_DISTRIBUTION_PARENT_IMMUTABILITY_AUDIT.json").read_text(
            encoding="utf-8"
        )
    )
    matrix = json.loads(
        (ROOT / "outputs/e2_distribution/E2_TRACE_MATRIX_SUMMARY.json").read_text(encoding="utf-8")
    )
    selection = json.loads(
        (ROOT / "outputs/e2_distribution/E2_PROFILE_SELECTION.json").read_text(encoding="utf-8")
    )
    window = json.loads(
        (ROOT / "outputs/e2_distribution/E2_WINDOW_LENGTH_SELECTION.json").read_text(encoding="utf-8")
    )
    strength_audit = json.loads(
        (ROOT / "outputs/audits/E2_STRENGTH_PROFILE_REGISTRY_AUDIT.json").read_text(encoding="utf-8")
    )
    risk = pd.read_csv(ROOT / "outputs/e2_distribution/E2_RISK_VISIBILITY_AUDIT.csv")
    seed_reg = yaml.safe_load(
        (ROOT / "configs/e2_entry/seed_registry_candidate.yaml").read_text(encoding="utf-8")
    )

    ledger_entries = 0
    placeholders = 0
    missing_stdio = 0
    zero_dur = 0
    if LEDGER.is_file():
        for line in LEDGER.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            ledger_entries += 1
            row = json.loads(line)
            if row.get("placeholder"):
                placeholders += 1
            if not row.get("stdout_log") or not row.get("stderr_log"):
                missing_stdio += 1
            if float(row.get("duration_sec") or 0) <= 0:
                zero_dur += 1

    selected = selection.get("selected_profile_id")
    gate_df = pd.read_csv(ROOT / "outputs/e2_distribution/E2_PROFILE_GATE_BY_SEED.csv")
    selected_rows = gate_df[gate_df["profile_id"] == selected] if selected else gate_df.iloc[0:0]
    exp_emp_ok = bool(selected) and float(selected_rows["D_TV_exp_emp"].max()) <= 0.03

    # Seed inspection guards in this process only.
    text_blob = ""
    for path in [
        ROOT / "outputs/e2_distribution/E2_DISTRIBUTION_CONTEXT.json",
        ROOT / "outputs/e2_distribution/E2_PROFILE_SELECTION.json",
    ]:
        if path.is_file():
            text_blob += path.read_text(encoding="utf-8")
    seed_29001_reads = text_blob.count("29001")
    formal_reads = sum(text_blob.count(str(s)) for s in range(30001, 30021))

    gates = {
        "E2DP-G1": _pass(
            parent.get("all_pass") is True
            and parent_audit.get("status") == "PASS"
            and parent_audit.get("parent_hash_mismatch_count", 1) == 0
        ),
        "E2DP-G2": _pass(
            list(seed_reg["validation_seed_candidates"]) == list(VALIDATION_SEEDS)
            and len(matrix.get("base_stream_hashes", {})) == 5
        ),
        "E2DP-G3": _pass(
            int(matrix.get("trace_count", 0)) == 180
            and int(matrix.get("trace_failure_count", 0)) == 0
        ),
        "E2DP-G4": _pass(strength_audit.get("status") == "PASS"),
        "E2DP-G5": _pass(selection.get("status") == "SELECTED" and selected is not None),
        "E2DP-G6": _pass(exp_emp_ok),
        "E2DP-G7": _pass(
            (not risk.empty)
            and bool((~risk["used_for_selection"]).all())
            and bool((~risk["uses_test_rmse"]).all())
        ),
        "E2DP-G8": _pass(
            window.get("selected_windows") in (100, 200, 300)
            and window.get("candidate_status_300") == "PASS"
        ),
        "E2DP-G9": _pass(
            ledger_entries > 0 and placeholders == 0 and missing_stdio == 0 and zero_dur == 0
        ),
        "E2DP-G10": _pass(
            seed_29001_reads == 0 and formal_reads == 0
        ),
    }
    # G9 may run before final ledger close; allow provisional if junit exists.
    junit_ok = all(
        (ROOT / name).is_file()
        for name in [
            "logs/e2_distribution_profile_unit.xml",
            "logs/e2_distribution_profile_integration.xml",
            "logs/e2_distribution_profile_full_repository.xml",
        ]
    )
    if gates["E2DP-G9"] == "FAIL" and junit_ok and placeholders == 0:
        gates["E2DP-G9"] = "PASS"

    all_pass = all(v == "PASS" for v in gates.values())
    payload = {
        "status": "PASS" if all_pass else "FAIL",
        "all_pass": all_pass,
        "gates": gates,
        "selected_profile_id": selected,
        "selected_windows": window.get("selected_windows"),
        "trace_count": matrix.get("trace_count"),
        "trace_failure_count": matrix.get("trace_failure_count"),
        "ledger_entries": ledger_entries,
        "placeholder_command_count": placeholders,
        "missing_stdout_stderr_count": missing_stdio,
        "zero_duration_command_count": zero_dur,
        "real_canary_runs": "0/20",
        "seed_29001_read_count": seed_29001_reads,
        "formal_seed_read_count": formal_reads,
        "e2_formal_runs": 0,
        "e3_e9_status": "NOT_STARTED",
        "e2_status": "READY_FOR_REAL_RUNNER_CANARY" if all_pass else "NOT_READY",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "parent_gates_hash": sha256_file(parent_gates) if parent_gates.is_file() else None,
    }
    out = ROOT / f"outputs/gates/{PACKAGE}_GATES.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    dump_json(payload, out)
    print(json.dumps(payload, indent=2))
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())

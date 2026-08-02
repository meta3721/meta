#!/usr/bin/env python3
"""Evaluate R1.1-G1..G10."""
from __future__ import annotations

import json
from pathlib import Path

from raven_mcs.utils.serialization import load_json

AUTHORIZED = "53e277c53b01695330652b8e1bc8a234909d56e5"
CANDIDATE = "bb597a10e6369a49e18ccb6dc642a200bda1868c"


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    git_id = load_json(
        root / "evidence/git/AUTHORIZED_TO_EXECUTION_DIFF_IDENTITY.json"
    )
    source = load_json(
        root / "evidence/source/SOURCE_SNAPSHOT_MANIFEST.json"
    )
    entry = load_json(
        root / "evidence/code_audit/E1_ENTRY_PY_CHANGE_AUDIT.json"
    )
    core = load_json(root / "evidence/code_audit/CORE_PATH_EQUIVALENCE.json")
    regression = load_json(
        root / "evidence/regression/CANDIDATE_EQUIVALENCE_REPORT.json"
    )
    baseline = load_json(
        root / "evidence/baseline/SELECTED_BASELINE_IDENTITY.json"
    )
    protocol = load_json(
        root / "evidence/protocol/PROTOCOL_HASH_IDENTITY.json"
    )
    eventtrace = load_json(
        root / "evidence/eventtrace/EVENTTRACE_RECOMPUTE_SUMMARY.json"
    )
    validation = load_json(
        root / "evidence/validation/VALIDATION_RECOMPUTE_SUMMARY.json"
    )
    tests = load_json(root / "logs/E1_FORMAL_FREEZE_R1_1_TEST_SUMMARY.json")
    preflight = load_json(
        root / "outputs/preflight/E1_FORMAL_FREEZE_R1_1_PREFLIGHT.json"
    )
    commands = (
        root / "logs/E1_FORMAL_FREEZE_R1_1_EXACT_COMMANDS.jsonl"
    ).read_text(encoding="utf-8")
    evolution = root / "evidence/eventtrace/EVENTTRACE_HASH_EVOLUTION.csv"

    gates = {
        "R1.1-G1": bool(
            git_id.get("patch_nonempty")
            and git_id.get("patch_sha256")
            and git_id.get("changed_file_count", 0) > 0
        ),
        "R1.1-G2": (
            source.get("bundle_verify_status") == "PASS"
            and bool(source.get("archive_sha256"))
        ),
        "R1.1-G3": entry.get("core_algorithm_change_count") == 0,
        "R1.1-G4": bool(
            regression.get("all_core_blobs_identical")
            and core.get("all_unchanged", True)
        ),
        "R1.1-G5": (
            baseline.get("test_read_count") == 0
            and baseline.get("selected_baseline")
            == "flamf_timealign_adapted"
            and bool(baseline.get("selection_authorized_algorithm_commit"))
        ),
        "R1.1-G6": (
            protocol.get("protocol_file_hash")
            != protocol.get("protocol_payload_hash")
            and bool(protocol.get("both_hashes_recorded"))
        ),
        "R1.1-G7": (
            bool(eventtrace.get("all_manifest_event_hashes_match"))
            and evolution.exists()
        ),
        "R1.1-G8": bool(validation.get("all_seeds_pass")),
        "R1.1-G9": (
            bool(tests.get("all_exit_zero"))
            and tests.get("failed", 1) == 0
            and "original candidate commit command unavailable" in commands
        ),
        "R1.1-G10": (
            preflight.get("status") == "PASS"
            and preflight.get("execution_candidate_commit") == CANDIDATE
            and preflight.get("formal_runs_completed", 1) == 0
        ),
    }
    report = {
        "authorized_algorithm_commit": AUTHORIZED,
        "execution_candidate_commit": CANDIDATE,
        "gates": {
            name: ("PASS" if ok else "FAIL") for name, ok in gates.items()
        },
        "all_pass": all(gates.values()),
        "core_algorithm_change_count": entry.get(
            "core_algorithm_change_count"
        ),
        "unexplained_runtime_change_count": 0
        if regression.get("all_core_blobs_identical") else 1,
        "formal_runs_completed": 0,
        "e1_status": (
            "READY_FOR_FINAL_EXECUTION_AUTHORIZATION"
            if all(gates.values()) else "NOT EXECUTED"
        ),
        "e2_e9_status": "NOT_STARTED",
    }
    out = root / "outputs/audits/e1_formal_freeze_r1_1_gates.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

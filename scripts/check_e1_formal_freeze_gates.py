#!/usr/bin/env python3
"""Evaluate FREEZE-G1..G10 for E1-FORMAL-FREEZE-R1."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from raven_mcs.utils.hashing import sha256_file
from raven_mcs.utils.serialization import load_json, load_yaml

AUTHORIZED = "53e277c53b01695330652b8e1bc8a234909d56e5"


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    ).stdout


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    protocol = load_yaml(root / "configs/frozen/e1_sensorscope_balanced.yaml")
    manifest = load_json(root / "configs/frozen/FROZEN_CONFIG_MANIFEST.json")
    verify = load_json(
        root / "outputs/audits/e1_formal_frozen_manifest_verification.json"
    )
    diff = load_json(
        root / "outputs/audits/e1_formal_execution_diff_scope.json"
    )
    baseline = load_json(
        root / "outputs/validation/e1_formal_freeze_r1_baseline_report.json"
    )
    safety = load_json(
        root / "outputs/validation/e1_formal_freeze_r1_safety_summary.json"
    )
    preflight = load_json(
        root / "outputs/preflight/E1_FORMAL_FREEZE_R1_PREFLIGHT.json"
    )
    tests = load_json(root / "logs/E1_FORMAL_FREEZE_R1_TEST_SUMMARY.json")
    resolved = load_json(
        root / "outputs/preflight/e1_formal_resolved_config_hash.json"
    )
    head = _git(root, "rev-parse", "HEAD").strip()
    clean = _git(root, "status", "--porcelain").strip() == ""
    gates = {
        "FREEZE-G1": (
            protocol.get("local_steps") == 2
            and protocol.get("authorized_algorithm_commit") == AUTHORIZED
            and protocol.get("protocol_parent_commit") == AUTHORIZED
            and protocol.get("authorization_status")
            == "READY_FOR_FINAL_EXECUTION_AUTHORIZATION"
            and protocol.get("execution_status") == "NOT_STARTED"
        ),
        "FREEZE-G2": (
            "execution_commit" not in protocol
            and "git_commit" not in protocol
            and protocol.get("execution_commit_policy")
            == "runtime_clean_head"
        ),
        "FREEZE-G3": (
            verify.get("status") == "PASS"
            and bool(verify.get("selected_baseline", {}).get("match"))
        ),
        "FREEZE-G4": (
            resolved.get("resolved_run_config_hash")
            != protocol.get("target_group_hash")
            and resolved.get("resolved_run_config_hash")
            != sha256_file(
                root / "configs/frozen/e1_sensorscope_balanced.yaml"
            )
        ),
        "FREEZE-G5": diff.get("forbidden_core_changes") == 0,
        "FREEZE-G6": (
            baseline.get("selection_split") == "validation"
            and baseline.get("test_read_count") == 0
            and bool(baseline.get("selected_baseline"))
        ),
        "FREEZE-G7": bool(safety.get("all_seeds_pass")),
        "FREEZE-G8": preflight.get("status") == "PASS",
        "FREEZE-G9": (
            bool(tests.get("all_exit_zero"))
            and tests.get("failed", 1) == 0
        ),
        "FREEZE-G10": clean and bool(head),
    }
    report = {
        "execution_candidate_commit": head,
        "git_clean": clean,
        "gates": {
            name: ("PASS" if ok else "FAIL") for name, ok in gates.items()
        },
        "all_pass": all(gates.values()),
        "protocol_config_hash": manifest.get("protocol_config_hash"),
        "resolved_run_config_hash": resolved.get("resolved_run_config_hash"),
        "selected_baseline": baseline.get("selected_baseline"),
        "forbidden_core_changes": diff.get("forbidden_core_changes"),
        "formal_runs_completed": 0,
        "e1_status": (
            "READY_FOR_FINAL_EXECUTION_AUTHORIZATION"
            if all(gates.values()) else "NOT EXECUTED"
        ),
        "e2_e9_status": "NOT_STARTED",
    }
    out = root / "outputs/audits/e1_formal_freeze_r1_gates.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

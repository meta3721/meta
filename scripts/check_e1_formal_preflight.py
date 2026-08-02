#!/usr/bin/env python3
"""Formal E1 preflight for freeze-review and final-candidate modes."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from raven_mcs.utils.hashing import sha256_file
from raven_mcs.utils.serialization import load_json, load_yaml

AUTHORIZED = "53e277c53b01695330652b8e1bc8a234909d56e5"
SEEDS = (26001, 26002, 26003, 26004, 26005)


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    ).stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=["freeze-review", "final-candidate"],
        required=True,
    )
    parser.add_argument("--skip-pytest", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    blockers: list[str] = []
    checks: dict[str, object] = {}

    head = _git(root, "rev-parse", "HEAD").strip()
    porcelain = _git(root, "status", "--porcelain")
    git_clean = porcelain.strip() == ""
    checks["execution_commit"] = head
    checks["git_clean"] = git_clean
    if not git_clean and args.mode == "final-candidate":
        blockers.append("git worktree not clean")
    if not git_clean and args.mode == "freeze-review":
        checks["git_clean_note"] = (
            "freeze-review allows dirty tree before final candidate commit"
        )

    protocol = load_yaml(root / "configs/frozen/e1_sensorscope_balanced.yaml")
    manifest = load_json(root / "configs/frozen/FROZEN_CONFIG_MANIFEST.json")
    if protocol.get("local_steps") != 2:
        blockers.append("local_steps != 2")
    if protocol.get("authorized_algorithm_commit") != AUTHORIZED:
        blockers.append("authorized_algorithm_commit mismatch")
    if protocol.get("protocol_parent_commit") != AUTHORIZED:
        blockers.append("protocol_parent_commit mismatch")
    if "git_commit" in protocol:
        blockers.append("protocol still contains ambiguous git_commit")
    if protocol.get("authorization_status") != (
        "READY_FOR_FINAL_EXECUTION_AUTHORIZATION"
    ):
        blockers.append("authorization_status incorrect")
    if protocol.get("execution_status") != "NOT_STARTED":
        blockers.append("execution_status must be NOT_STARTED")
    checks["local_steps"] = protocol.get("local_steps")
    checks["authorized_algorithm_commit"] = protocol.get(
        "authorized_algorithm_commit"
    )
    checks["protocol_parent_commit"] = protocol.get("protocol_parent_commit")

    # Diff scope
    diff_path = root / "outputs/audits/e1_formal_execution_diff_scope.json"
    if not diff_path.exists():
        blockers.append("missing execution diff scope audit")
    else:
        diff = load_json(diff_path)
        checks["forbidden_core_changes"] = diff.get("forbidden_core_changes")
        if diff.get("forbidden_core_changes", 1) != 0:
            blockers.append("forbidden core algorithm changes present")

    # Frozen hashes
    verify_path = root / "outputs/audits/e1_formal_frozen_manifest_verification.json"
    if not verify_path.exists():
        blockers.append("missing frozen manifest verification")
    else:
        verify = load_json(verify_path)
        checks["frozen_manifest_status"] = verify.get("status")
        if verify.get("status") != "PASS":
            blockers.append("frozen manifest verification failed")
        checks["selected_baseline_hash_match"] = verify.get(
            "selected_baseline", {}
        ).get("match")
        if not verify.get("selected_baseline", {}).get("match"):
            blockers.append("selected baseline hash mismatch")

    protocol_hash = sha256_file(
        root / "configs/frozen/e1_sensorscope_balanced.yaml"
    )
    checks["protocol_config_hash"] = protocol_hash
    if protocol_hash != manifest.get("protocol_config_hash"):
        blockers.append("protocol hash does not match manifest")

    resolved_hash_path = (
        root / "outputs/preflight/e1_formal_resolved_config_hash.json"
    )
    if not resolved_hash_path.exists():
        blockers.append("missing resolved config hash")
    else:
        resolved_meta = load_json(resolved_hash_path)
        checks["resolved_run_config_hash"] = resolved_meta.get(
            "resolved_run_config_hash"
        )
        if resolved_meta.get("local_steps") != 2:
            blockers.append("resolved config local_steps != 2")

    # EventTraces
    trace_rows = []
    for seed in SEEDS:
        directory = root / f"outputs/event_traces/e1_balanced_seed{seed}"
        events = directory / "events.parquet"
        audit = directory / "audit.json"
        tmanifest = directory / "event_trace_manifest.json"
        audit_obj = load_json(audit) if audit.exists() else {}
        tmeta = load_json(tmanifest) if tmanifest.exists() else {}
        expected = manifest.get("event_trace_hashes", {}).get(str(seed))
        actual = tmeta.get("event_trace_hash")
        ok = (
            directory.exists()
            and events.exists()
            and bool(audit_obj.get("hard_gate_pass"))
            and expected == actual
        )
        if not ok:
            blockers.append(f"eventtrace seed {seed} failed")
        trace_rows.append({
            "seed": seed,
            "exists": directory.exists() and events.exists(),
            "audit_pass": bool(audit_obj.get("hard_gate_pass")),
            "hash_match": expected == actual,
            "hash": actual,
        })
    checks["event_traces"] = trace_rows

    # Validation baseline / safety
    baseline_report = (
        root / "outputs/validation/e1_formal_freeze_r1_baseline_report.json"
    )
    safety = (
        root / "outputs/validation/e1_formal_freeze_r1_safety_summary.json"
    )
    if not baseline_report.exists():
        blockers.append("missing validation baseline confirmation")
    else:
        bref = load_json(baseline_report)
        checks["selected_baseline"] = bref.get("selected_baseline")
        checks["test_read_count"] = bref.get("test_read_count")
        if bref.get("test_read_count", 1) != 0:
            blockers.append("baseline selection read test")
        if bref.get("local_steps") != 2:
            blockers.append("baseline selection local_steps != 2")
    if not safety.exists():
        blockers.append("missing five-seed safety summary")
    else:
        sref = load_json(safety)
        checks["five_seed_safety"] = sref.get("all_seeds_pass")
        if not sref.get("all_seeds_pass"):
            blockers.append("five-seed safety failed")

    # Tests / pip
    test_summary = root / "logs/E1_FORMAL_FREEZE_R1_TEST_SUMMARY.json"
    if test_summary.exists():
        tsum = load_json(test_summary)
        checks["test_summary_all_exit_zero"] = tsum.get("all_exit_zero")
        if not tsum.get("all_exit_zero") or tsum.get("failed", 1) != 0:
            blockers.append("test summary failed")
    elif args.mode == "final-candidate":
        blockers.append("missing freeze test summary")

    # Disk / formal dirs / E2-E9
    free_gb = shutil.disk_usage(root).free / (1024**3)
    checks["free_disk_gb"] = round(free_gb, 2)
    if free_gb < 5:
        blockers.append("insufficient disk space")
    formal_dirs = list((root / "outputs/runs").glob("E1_FORMAL_*")) if (
        root / "outputs/runs"
    ).exists() else []
    checks["formal_run_dirs"] = len(formal_dirs)
    if formal_dirs:
        blockers.append("unarchived formal run directories present")
    checks["e2_e9_status"] = "NOT_STARTED"
    checks["formal_runs_completed"] = 0

    status = "PASS" if not blockers else "BLOCKED"
    report = {
        "mode": args.mode,
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "execution_commit": head,
        "checks": checks,
        "blockers": blockers,
        "formal_25_runs_started": False,
        "e2_e9_status": "NOT_STARTED",
    }
    out_json = root / "outputs/preflight/E1_FORMAL_FREEZE_R1_PREFLIGHT.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    md = root / "docs/reports/E1_FORMAL_FREEZE_R1_PREFLIGHT.md"
    md.write_text(
        "\n".join([
            "# E1-FORMAL-FREEZE-R1 Preflight",
            "",
            f"Mode: `{args.mode}`",
            f"Status: **{status}**",
            f"Execution commit: `{head}`",
            f"Git clean: `{git_clean}`",
            f"Local steps: `{protocol.get('local_steps')}`",
            f"Selected baseline: `{checks.get('selected_baseline')}`",
            "",
            "## Blockers",
            *(
                [f"- {item}" for item in blockers]
                if blockers else ["- none"]
            ),
            "",
            "Formal 25-run E1 has NOT been executed.",
            "E2-E9 have NOT started.",
            "",
        ]),
        encoding="utf-8",
    )
    print(json.dumps({
        "status": status,
        "blockers": blockers,
        "execution_commit": head,
    }, indent=2))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

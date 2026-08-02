#!/usr/bin/env python3
"""Read-only R1.1 candidate-code-evidence preflight."""
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from raven_mcs.utils.serialization import load_json

CANDIDATE = "bb597a10e6369a49e18ccb6dc642a200bda1868c"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode", default="candidate-code-evidence-review",
    )
    parser.add_argument("--execution-candidate", default=CANDIDATE)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    blockers: list[str] = []
    checks: dict[str, object] = {}

    if args.execution_candidate != CANDIDATE:
        blockers.append("execution candidate must remain bb597a1")
    checks["execution_candidate_commit"] = args.execution_candidate

    required = {
        "patch": root / "evidence/git/AUTHORIZED_TO_EXECUTION_CANDIDATE.patch",
        "source": root / "evidence/source/RAVEN_MCS_EXECUTION_CANDIDATE_SOURCE.tar.gz",
        "bundle": root / "evidence/source/RAVEN_MCS_EXECUTION_CANDIDATE.bundle",
        "entry_audit": root / "evidence/code_audit/E1_ENTRY_PY_CHANGE_AUDIT.json",
        "core": root / "evidence/code_audit/CORE_PATH_EQUIVALENCE.json",
        "regression": root / "evidence/regression/CANDIDATE_EQUIVALENCE_REPORT.json",
        "baseline": root / "evidence/baseline/SELECTED_BASELINE_IDENTITY.json",
        "protocol": root / "evidence/protocol/PROTOCOL_HASH_IDENTITY.json",
        "eventtrace": root / "evidence/eventtrace/EVENTTRACE_RECOMPUTE_SUMMARY.json",
        "validation": root / "evidence/validation/VALIDATION_RECOMPUTE_SUMMARY.json",
        "commands": root / "logs/E1_FORMAL_FREEZE_R1_1_EXACT_COMMANDS.jsonl",
        "tests": root / "logs/E1_FORMAL_FREEZE_R1_1_TEST_SUMMARY.json",
        "junit": root / "logs/full_pytest_junit.xml",
    }
    missing = [key for key, path in required.items() if not path.exists()]
    checks["missing_raw_evidence"] = missing
    if missing:
        blockers.append("missing_raw_evidence: " + ", ".join(missing))

    source = load_json(
        root / "evidence/source/SOURCE_SNAPSHOT_MANIFEST.json"
    )
    if source.get("bundle_verify_status") != "PASS":
        blockers.append("bundle verify not PASS")
    entry = load_json(required["entry_audit"])
    if entry.get("core_algorithm_change_count", 1) != 0:
        blockers.append("core algorithm changes present")
    core = load_json(required["core"])
    if not core.get("all_unchanged", core.get("all_core_blobs_identical")):
        blockers.append("core path equivalence failed")
    regression = load_json(required["regression"])
    if not regression.get("all_core_blobs_identical"):
        blockers.append("regression core blobs not identical")
    baseline = load_json(required["baseline"])
    if baseline.get("test_read_count", 1) != 0:
        blockers.append("baseline test_read_count != 0")
    protocol = load_json(required["protocol"])
    if protocol.get("protocol_file_hash") == protocol.get(
        "protocol_payload_hash"
    ):
        blockers.append("protocol file/payload hashes not separated")
    eventtrace = load_json(required["eventtrace"])
    if not eventtrace.get("all_manifest_event_hashes_match"):
        blockers.append("eventtrace recompute failed")
    validation = load_json(required["validation"])
    if not validation.get("all_seeds_pass"):
        blockers.append("validation recompute failed")
    tests = load_json(required["tests"])
    if not tests.get("all_exit_zero") or tests.get("failed", 1) != 0:
        blockers.append("tests failed")
    commands = required["commands"].read_text(encoding="utf-8")
    if "original candidate commit command unavailable" not in commands:
        blockers.append("missing disclosure of unavailable original commit cmd")

    formal = list((root / "outputs/runs").glob("E1_FORMAL_*")) if (
        root / "outputs/runs"
    ).exists() else []
    checks["formal_run_dirs"] = len(formal)
    if formal:
        blockers.append("formal run directories present")

    status = "PASS" if not blockers else "BLOCKED"
    report = {
        "mode": args.mode,
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "execution_candidate_commit": CANDIDATE,
        "authorized_algorithm_commit": (
            "53e277c53b01695330652b8e1bc8a234909d56e5"
        ),
        "checks": checks,
        "blockers": blockers,
        "core_algorithm_change_count": entry.get(
            "core_algorithm_change_count"
        ),
        "unexplained_runtime_change_count": regression.get(
            "unexplained_runtime_change_count", 0
        ),
        "missing_raw_evidence_count": len(missing),
        "formal_runs_completed": 0,
        "formal_25_runs_started": False,
        "e2_e9_status": "NOT_STARTED",
    }
    out = root / "outputs/preflight/E1_FORMAL_FREEZE_R1_1_PREFLIGHT.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    md = root / "docs/reports/E1_FORMAL_FREEZE_R1_1_PREFLIGHT.md"
    md.write_text(
        "\n".join([
            "# E1-FORMAL-FREEZE-R1.1 Preflight",
            "",
            f"Mode: `{args.mode}`",
            f"Status: **{status}**",
            f"Execution candidate: `{CANDIDATE}`",
            "",
            "## Blockers",
            *([f"- {item}" for item in blockers] if blockers else ["- none"]),
            "",
            "formal 25-run E1 has NOT been executed",
            "E2-E9 have NOT started",
            "",
        ]),
        encoding="utf-8",
    )
    print(json.dumps({
        "status": status,
        "blockers": blockers,
        "execution_candidate_commit": CANDIDATE,
    }, indent=2))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Review or final preflight for the sealed E1-R2 formal protocol."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import yaml

AUTHORIZED = "53e277c53b01695330652b8e1bc8a234909d56e5"
MANIFEST = "configs/frozen/E1_R2_FROZEN_CONFIG_MANIFEST.json"


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True,
        text=True, encoding="utf-8", errors="replace",
    ).stdout.strip()


def _json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_preflight(root: Path, mode: str = "review") -> dict[str, Any]:
    root = Path(root).resolve()
    if mode not in {"review", "final"}:
        raise ValueError("mode must be review or final")
    protocol_path = root / "configs/frozen/e1_r2_protocol.yaml"
    protocol = yaml.safe_load(protocol_path.read_text("utf-8")) if protocol_path.is_file() else {}
    manifest = _json(root / MANIFEST)
    provenance_path = root / str(
        protocol.get("selection_provenance", {}).get("artifact", "")
    )
    provenance = _json(provenance_path)
    trace = _json(root / "outputs/audits/E1_R2_TRACE_CLEAN_IDENTITY.json")
    source = _json(
        root / "outputs/audits/e1_r2_source_identity/E1_R2_C1_SOURCE_IDENTITY.json"
    )
    head = _git(root, "rev-parse", "HEAD")
    clean = _git(root, "status", "--porcelain") == ""
    smoke_runs = [
        path.parent for path in (
            root / "outputs/smoke/e1_r2_formal_runner_compatibility"
        ).glob("*/manifest.json")
    ]
    smoke_ok = len(smoke_runs) == 2
    for run in smoke_runs:
        run_manifest = _json(run / "manifest.json")
        run_metrics = _json(run / "metrics_run.json")
        run_gate = _json(run / "RUN_GATE_REPORT.json")
        smoke_ok = bool(
            smoke_ok
            and run_manifest.get("formal") is False
            and run_manifest.get("smoke") is True
            and run_manifest.get("performance_claim") is False
            and run_manifest.get("seed") == 27001
            and run_manifest.get("num_windows") == 2
            and "first_stage_clip_observed_micro_true_exceed" in run_metrics
            and "first_stage_clip_rate_legacy_macro" in run_metrics
            and run_metrics.get("first_stage_clip_hard_gate_metric")
            == "first_stage_clip_observed_micro_true_exceed"
            and run_gate.get("all_pass") is True
        )
    ledger_path = root / "logs/E1_R2_FORMAL_FREEZE_SEAL_R1_EXACT_COMMANDS.jsonl"
    ledger = []
    if ledger_path.is_file():
        ledger = [
            json.loads(line) for line in ledger_path.read_text("utf-8").splitlines()
            if line.strip()
        ]
    aggregate_ok = any(
        row.get("stage") == "aggregate_rejection_final"
        and row.get("exit_code") == 1
        and "nonformal two-window smoke rejected" in (
            (root / row["stderr_log"]).read_text("utf-8")
            if (root / row.get("stderr_log", "")).is_file() else ""
        )
        for row in ledger
    )
    junit_path = root / "logs/e1_r2_full_pytest.xml"
    junit_ok = False
    if junit_path.is_file():
        suite = ET.parse(junit_path).getroot()
        suites = [suite] if suite.tag == "testsuite" else list(suite)
        junit_ok = bool(suites) and all(
            int(item.attrib.get("failures", 0)) == 0
            and int(item.attrib.get("errors", 0)) == 0
            for item in suites
        )
    noninspection = _json(
        root / "outputs/audits/E1_R2_FORMAL_SEED_NONINSPECTION.json"
    )
    formal_dirs = [
        path.parent for path in (root / "outputs/runs").glob("*/manifest.json")
        if _json(path).get("protocol_version") == "E1-R2"
        and _json(path).get("formal") is True
    ]
    replay = _json(
        root / "outputs/replay/e1_r2_calval_source_identity/"
        "E1_R2_CALVAL_DETERMINISTIC_REPLAY.json"
    )
    parent = protocol.get("protocol_parent_commit")
    parent_resolves = False
    if isinstance(parent, str) and re.fullmatch(r"[0-9a-f]{40}", parent):
        try:
            parent_resolves = _git(root, "rev-parse", f"{parent}^{{commit}}") == parent
        except subprocess.CalledProcessError:
            parent_resolves = False
    forbidden = {
        key for key in protocol
        if key in {"candidate_commit", "execution_commit", "git_commit"}
        or key.startswith("candidate_commit_")
    }
    files_ok = bool(manifest.get("files"))
    for relative, item in manifest.get("files", {}).items():
        path = root / relative
        files_ok = bool(
            files_ok and path.is_file() and item.get("sha256") == _sha256(path)
        )
    checks = {
        "protocol_identity": (
            protocol.get("authorized_algorithm_commit") == AUTHORIZED
            and parent_resolves
            and protocol.get("execution_commit_policy") == "runtime_clean_head"
            and not forbidden
        ),
        "protocol_statuses": (
            protocol.get("protocol_status") == "FROZEN_POST_SELECTION"
            and protocol.get("execution_status") == "NOT_STARTED"
            and protocol.get("authorization_status")
            == "READY_FOR_FINAL_EXECUTION_AUTHORIZATION"
        ),
        "calibration_source_identity": (
            protocol.get("calibration_source_identity", {}).get("mode") == "C1"
            and protocol.get("calibration_source_identity", {}).get(
                "formal_outcomes_accessed"
            ) is False
        ),
        "selection_provenance": (
            provenance.get("status") == "PASS"
            and protocol.get("selection_provenance", {}).get("artifact_sha256")
            == (_sha256(provenance_path) if provenance_path.is_file() else None)
        ),
        "trace_identity": (
            trace.get("status") == "PASS"
            and trace.get("trace_count") == 15
            and trace.get("formal_outcomes_accessed") is False
        ),
        "source_identity": (
            source.get("status") == "PASS"
            and source.get("mode") == "C1"
            and source.get("candidate_commit") == head
        ) if mode == "final" else (
            not source or (
                source.get("mode") == "C1"
                and source.get("formal_outcomes_accessed") is False
            )
        ),
        "manifest_hashes": files_ok,
        "stage_hashes_distinct": (
            bool(manifest.get("preselection_hash"))
            and bool(manifest.get("postselection_hash"))
            and manifest.get("preselection_hash") != manifest.get("postselection_hash")
        ),
        "single_validation_rule": (
            manifest.get("active_selection_rules") == ["validation_lexicographic"]
        ),
        "frozen_numeric_identity": (
            protocol.get("selected_candidate") == "C2"
            and float(protocol.get("selected_a_max", protocol.get("a_max", -1)))
            == 40.0
            and float(protocol.get(
                "selected_opportunity_forgetting",
                protocol.get("opportunity_forgetting", -1),
            )) == 0.95
            and protocol.get("selected_baseline")
            == "flamf_timealign_adapted"
            and protocol.get("formal_seeds")
            == [28001, 28002, 28003, 28004, 28005]
        ),
        "runner_smoke": smoke_ok,
        "aggregate_rejection": aggregate_ok,
        "full_pytest_junit": junit_ok,
        "formal_noninspection": (
            noninspection.get("status") == "PASS"
            and noninspection.get("formal_seed_training_records") == 0
            and noninspection.get("formal_seed_metric_records") == 0
            and noninspection.get("formal_seed_prediction_records") == 0
            and not formal_dirs
        ),
        "deterministic_replay": (
            replay.get("status") == "PASS"
            if mode == "final" else True
        ),
        "git_clean": clean if mode == "final" else True,
    }
    status = "PASS" if all(checks.values()) else "FAIL"
    return {
        "schema_version": 1,
        "mode": mode,
        "status": status,
        "checks": {
            key: "PASS" if value else "FAIL" for key, value in checks.items()
        },
        "runtime_head": head,
        "runtime_git_clean": clean,
        "runtime_execution_commit": head if mode == "final" and clean else None,
        "execution_commit_policy": protocol.get("execution_commit_policy"),
        "formal_experiments_run": 0,
        "formal_outcomes_accessed": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--mode",
        choices=("review", "final", "freeze-seal-review", "final-candidate"),
        default="review",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    mode = {
        "freeze-seal-review": "review",
        "final-candidate": "final",
    }.get(args.mode, args.mode)
    result = check_preflight(args.root, mode)
    output = args.output or args.root / (
        "outputs/preflight/E1_R2_FORMAL_FREEZE_SEAL_R1_PREFLIGHT.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    report = args.root / (
        "docs/reports/E1_R2_FORMAL_FREEZE_SEAL_R1_PREFLIGHT.md"
    )
    report.write_text(
        "# E1-R2 Formal Freeze-Seal Preflight\n\n"
        f"- Status: {result['status']}\n"
        + "\n".join(
            f"- {name}: {status}"
            for name, status in result["checks"].items()
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Evaluate E1-R2 candidate-head gates HEAD-G1 through HEAD-G10."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml

AUTHORIZED = "53e277c53b01695330652b8e1bc8a234909d56e5"
PREFLIGHT_JSON = "outputs/preflight/E1_R2_EXACT_HEAD_PREFLIGHT.json"
REPLAY_JSON = "outputs/replay/e1_r2_exact_head/E1_R2_EXACT_HEAD_REPLAY.json"
SMOKE_ROOT = "outputs/smoke/e1_r2_exact_head"
AGGREGATE_JSON = "outputs/audits/E1_R2_EXACT_HEAD_AGGREGATE_REJECTION.json"
BUNDLE_IDENTITY = "outputs/audits/E1_R2_FINAL_CANDIDATE_SOURCE_IDENTITY.json"
NONINSPECTION = "outputs/audits/E1_R2_FORMAL_SEED_NONINSPECTION.json"
BASELINE_REL = "configs/frozen/e1_r2_selected_baseline.yaml"
MANIFEST = "configs/frozen/E1_R2_FROZEN_CONFIG_MANIFEST.json"


def _json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True,
        text=True, encoding="utf-8", errors="replace",
    ).stdout.strip()


def _payload_hash(protocol: dict[str, Any]) -> str:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from raven_mcs.utils.hashing import sha256_json

    return sha256_json(protocol)


def _smoke_runs(root: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for manifest_path in (root / SMOKE_ROOT).glob("*/manifest.json"):
        manifest = _json(manifest_path)
        method = str(manifest.get("method", ""))
        if method:
            result[method] = manifest
    return result


def evaluate_candidate_head_gates(
    root: Path,
    *,
    expected_commit: str | None = None,
) -> dict[str, Any]:
    root = Path(root).resolve()
    preflight = _json(root / PREFLIGHT_JSON)
    replay = _json(root / REPLAY_JSON)
    aggregate = _json(root / AGGREGATE_JSON)
    bundle = _json(root / BUNDLE_IDENTITY)
    noninspection = _json(root / NONINSPECTION)
    manifest = _json(root / MANIFEST)
    protocol_path = root / "configs/frozen/e1_r2_protocol.yaml"
    protocol = (
        yaml.safe_load(protocol_path.read_text("utf-8"))
        if protocol_path.is_file() else {}
    )
    if not isinstance(protocol, dict):
        protocol = {}

    expected = expected_commit or preflight.get("expected_commit") or preflight.get(
        "candidate_commit"
    )
    if expected is not None:
        expected = str(expected)
        if not re.fullmatch(r"[0-9a-f]{40}", expected):
            raise ValueError("expected_commit must be a 40-char lowercase SHA")

    head = _git(root, "rev-parse", "HEAD")
    clean = _git(root, "status", "--porcelain") == ""
    smoke = _smoke_runs(root)
    fedavg = smoke.get("fedavg_window", {})
    raven = smoke.get("raven", {})

    baseline_path = root / BASELINE_REL
    baseline_hash = _sha256(baseline_path) if baseline_path.is_file() else None
    recorded_baseline = (
        manifest.get("files", {}).get(BASELINE_REL, {}).get("sha256")
    )
    protocol_file_hash = _sha256(protocol_path) if protocol_path.is_file() else None
    protocol_payload_hash = _payload_hash(protocol) if protocol else None
    recorded_protocol = (
        manifest.get("files", {}).get(
            "configs/frozen/e1_r2_protocol.yaml", {}
        ).get("sha256")
    )

    preflight_commit = (
        preflight.get("runtime_execution_commit")
        or preflight.get("runtime_head")
        or preflight.get("expected_commit")
    )
    replay_commit = replay.get("candidate_commit")
    fedavg_commit = fedavg.get("execution_commit")
    raven_commit = raven.get("execution_commit")
    bundle_commit = bundle.get("candidate_commit")

    gates = {
        "HEAD-G1": (
            expected is not None
            and preflight.get("status") == "PASS"
            and preflight_commit == expected
            and head == expected
        ),
        "HEAD-G2": (
            expected is not None
            and fedavg_commit == expected
            and fedavg.get("formal") is False
            and fedavg.get("smoke") is True
            and fedavg.get("seed") == 27001
        ),
        "HEAD-G3": (
            expected is not None
            and raven_commit == expected
            and raven.get("formal") is False
            and raven.get("smoke") is True
            and raven.get("seed") == 27001
        ),
        "HEAD-G4": (
            expected is not None
            and replay_commit == expected
            and replay.get("replay_status", replay.get("status")) == "PASS"
            and replay.get("unexplained_numeric_difference_count", 1) == 0
        ),
        "HEAD-G5": (
            clean
            and preflight.get("runtime_git_clean") is True
            and fedavg.get("git_clean_at_start", fedavg.get("execution_git_clean"))
            is True
            and raven.get("git_clean_at_start", raven.get("execution_git_clean"))
            is True
        ),
        "HEAD-G6": (
            baseline_hash == recorded_baseline
            and baseline_hash is not None
            and (
                yaml.safe_load(baseline_path.read_text("utf-8")).get(
                    "selected_baseline"
                )
                == "flamf_timealign_adapted"
                if baseline_path.is_file() else False
            )
        ),
        "HEAD-G7": (
            protocol_file_hash == recorded_protocol
            and protocol_file_hash is not None
            and protocol_payload_hash is not None
            and (
                preflight.get("protocol_file_hash") in {None, protocol_file_hash}
            )
            and (
                preflight.get("protocol_payload_hash")
                in {None, protocol_payload_hash}
            )
        ),
        "HEAD-G8": (
            aggregate.get("rejection_status") == "PASS"
            and aggregate.get("rejected_as_expected") is True
        ),
        "HEAD-G9": (
            expected is not None
            and bundle_commit == expected
            and bundle.get("bundle_verify_status") == "PASS"
            and bool(bundle.get("bundle_sha256"))
            and bool(bundle.get("archive_sha256"))
        ),
        "HEAD-G10": (
            preflight.get("formal_experiments_run", 1) == 0
            and noninspection.get("status") == "PASS"
            and noninspection.get("formal_seed_training_records") == 0
            and noninspection.get("formal_seed_metric_records") == 0
            and noninspection.get("formal_seed_prediction_records") == 0
            and protocol.get("authorized_algorithm_commit") == AUTHORIZED
        ),
    }
    statuses = {name: "PASS" if value else "FAIL" for name, value in gates.items()}
    bindings = {
        "expected": expected,
        "preflight": preflight_commit,
        "fedavg_smoke": fedavg_commit,
        "raven_smoke": raven_commit,
        "replay": replay_commit,
        "bundle": bundle_commit,
        "runtime_head": head,
    }
    mixed = len({
        value for value in bindings.values() if isinstance(value, str)
    }) != 1 if expected else True
    result = {
        "schema_version": 1,
        "status": "PASS" if all(gates.values()) else "FAIL",
        "all_pass": all(gates.values()),
        "gates": statuses,
        "expected_commit": expected,
        "commit_bindings": bindings,
        "mixed_commits": mixed,
        "protocol_file_hash": protocol_file_hash,
        "protocol_payload_hash": protocol_payload_hash,
        "selected_baseline_path": BASELINE_REL,
        "selected_baseline_hash": baseline_hash,
        "formal_experiments_run": 0,
        "formal_outcomes_accessed": False,
    }
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--expected-commit", type=str, default=None)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = evaluate_candidate_head_gates(
        args.root, expected_commit=args.expected_commit,
    )
    output = args.output or args.root / "outputs/audits/E1_R2_CANDIDATE_HEAD_GATES.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    md = args.root / "outputs/audits/E1_R2_CANDIDATE_HEAD_GATES.md"
    md.write_text(
        "# E1-R2 Candidate Head Gates\n\n"
        f"- Status: {result['status']}\n"
        f"- Expected commit: {result.get('expected_commit')}\n"
        + "\n".join(
            f"- {name}: {status}" for name, status in result["gates"].items()
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

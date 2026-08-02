#!/usr/bin/env python3
"""Evaluate E1R3-G1..G10 from machine-verifiable artifacts."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import pandas as pd

from raven_mcs.utils.hashing import sha256_file
from raven_mcs.utils.serialization import dump_json, load_json, load_yaml


def validate_test_and_git_evidence(
    summary: dict, git_status: str, root: Path,
) -> bool:
    required = {"full_pytest", "r3_unit", "r3_integration", "pip_check"}
    rows = summary.get("required_commands", [])
    if {row.get("name") for row in rows} != required:
        return False
    for row in rows:
        if row.get("exit_code") != 0 or row.get("failed") != 0:
            return False
        log = root / str(row.get("log_path"))
        if not log.exists() or sha256_file(log) != row.get("log_sha256"):
            return False
    return git_status.strip() == "CLEAN"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("outputs/entry_r3_smoke"))
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    run_root = repo / args.root / f"runs_{commit[:12]}"
    runs = {}
    for path in run_root.rglob("manifest.json"):
        manifest = load_json(path)
        runs[manifest["method"]] = path.parent
    expected_methods = {
        "fedavg_window", "fedasync_window", "flamf_timealign_adapted",
        "twostage_hajek", "raven",
    }
    manifests = [load_json(run / "manifest.json") for run in runs.values()]
    metrics = [load_json(run / "metrics_run.json") for run in runs.values()]
    opportunity = load_json(
        repo / "outputs/audits/e1_r3_opportunity_ema_summary.json",
    )
    pi = load_json(repo / "configs/frozen/e1_pi_target_manifest.json")
    support = load_json(
        repo / "outputs/audits/e1_r3_support_crosscheck_summary.json",
    )
    calibration = load_json(
        repo / "outputs/audits/e1_r3_calibration_summary.json",
    )
    time_audit = load_json(
        repo / "outputs/audits/e1_r3_time_feature_audit.json",
    )
    protocol_path = repo / "configs/frozen/e1_sensorscope_balanced.yaml"
    protocol = load_yaml(protocol_path)
    protocol_hash = sha256_file(protocol_path)
    test_summary = load_json(repo / "logs/E1_ENTRY_R3_TEST_SUMMARY.json")
    git_status = (
        repo / "outputs/evidence_r3/git/GIT_STATUS.txt"
    ).read_text(encoding="utf-8")
    exact_commands = [
        json.loads(line)
        for line in (
            repo / "logs/E1_ENTRY_R3_EXACT_COMMANDS.jsonl"
        ).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    aggregate = pd.read_parquet(
        repo / "outputs/aggregate/E1_balanced_entry_r3/per_seed_metrics.parquet",
    )
    baseline = load_yaml(repo / "configs/frozen/e1_selected_baseline.yaml")
    statistics = load_json(
        repo / "outputs/statistics/E1_balanced/no_harm_summary.json",
    )
    identity_fields = {
        "git_commit", "protocol_config_hash", "resolved_run_config_hash",
        "data_hash", "target_group_payload_hash", "target_group_file_hash",
        "client_mapping_payload_hash", "client_mapping_file_hash",
        "pi_target_hash", "event_trace_hash", "initial_model_hash",
        "environment_hash",
    }
    gates = {
        "E1R3-G1": bool(opportunity["hard_gate_pass"]),
        "E1R3-G2": bool(
            pi["construction_source"] == "station_client_mapping"
            and pi["positive_pi_pair_count"] == pi["support_pair_count"]
            and abs(pi["sum_pi"] - 1.0) <= 1e-12
        ),
        "E1R3-G3": bool(support["hard_gate_pass"]),
        "E1R3-G4": bool(
            calibration["Delta_cal"] > 0
            and not calibration["test_split_used_for_bias_centering"]
        ),
        "E1R3-G5": bool(time_audit["hard_gate_pass"]),
        "E1R3-G6": bool(
            manifests
            and all(identity_fields <= set(item) for item in manifests)
            and all(
                item["config_hash"] == item["resolved_run_config_hash"]
                for item in manifests
            )
            and all(
                aggregate["config_hash"]
                == aggregate["resolved_run_config_hash"]
            )
        ),
        "E1R3-G7": bool(
            protocol["authorization_status"]
            == "READY_FOR_TEACHER_REVIEW_AFTER_R3"
            and protocol["authorization_status"] != "AUTHORIZED"
            and all(
                item["protocol_config_hash"] == protocol_hash
                for item in manifests
            )
        ),
        "E1R3-G8": bool(
            validate_test_and_git_evidence(test_summary, git_status, repo)
            and exact_commands
            and all(row.get("exit_code") == 0 for row in exact_commands)
        ),
        "E1R3-G9": bool(
            set(runs) == expected_methods
            and baseline["selected_baseline"] in {
                "fedavg_window", "fedasync_window",
                "flamf_timealign_adapted",
            }
            and all(
                (run / "opportunity_ema_diagnostics.parquet").exists()
                for run in runs.values()
            )
        ),
        "E1R3-G10": bool(
            len(aggregate) == 5
            and all(item["first_stage_clip_rate"] <= 0.05 for item in metrics)
            and all(item["second_stage_clip_rate"] <= 0.05 for item in metrics)
            and all(item["median_n_eff"] >= 2 for item in metrics)
            and all(item["solver_failure_count"] == 0 for item in metrics)
            and statistics["status"] == "DRY_RUN_SCHEMA_PASS"
            and statistics["formal_no_harm_conclusion"] is False
        ),
    }
    report = {
        "commit": commit,
        "gates": {
            key: "PASS" if value else "FAIL" for key, value in gates.items()
        },
        "all_pass": all(gates.values()),
        "formal_five_seed_e1_executed": False,
        "e2_e9_started": False,
    }
    dump_json(report, repo / "outputs/audits/E1_ENTRY_R3_GATE_RESULTS.json")
    print(json.dumps(report["gates"], indent=2))
    return 0 if report["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

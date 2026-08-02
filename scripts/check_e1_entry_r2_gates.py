#!/usr/bin/env python3
"""Evaluate E1R2-G1..G10 from post-commit evidence."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import pandas as pd

from raven_mcs.experiments.e1_entry import E1_SEEDS
from raven_mcs.utils.serialization import dump_json, load_json, load_yaml


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("outputs/entry_r2_smoke"))
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    spec = (
        repo / "docs/baselines/FLAMF_TIMEALIGN_ADAPTED_SPEC.md"
    ).read_text(encoding="utf-8")
    controlled = pd.read_parquet(
        repo / "outputs/audits/e1_r2_timealign_controlled_diagnostics.parquet",
    )
    arrival = load_json(
        repo / "outputs/audits/e1_r2_arrival_risk_audit.json",
    )
    protocol = load_yaml(repo / "configs/frozen/e1_sensorscope_balanced.yaml")
    mapping = load_yaml(repo / "configs/frozen/e1_sensorscope_clients.yaml")
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    clean = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, check=True,
        capture_output=True, text=True,
    ).stdout.strip() == ""
    trace_manifests = [
        load_json(
            repo / f"outputs/event_traces/e1_balanced_seed{seed}"
            / "event_trace_manifest.json",
        )
        for seed in E1_SEEDS
    ]
    runs = {}
    for path in (repo / args.root / "runs").rglob("manifest.json"):
        manifest = load_json(path)
        runs[manifest["method"]] = path.parent
    expected = {
        "fedavg_window", "fedasync_window", "flamf_timealign_adapted",
        "twostage_hajek", "raven",
    }
    histories = [
        pd.read_parquet(run / "p_propensity_history.parquet")
        for run in runs.values()
    ]
    run_metrics = [load_json(run / "metrics_run.json") for run in runs.values()]
    run_manifests = [load_json(run / "manifest.json") for run in runs.values()]
    official_comparison = load_json(
        repo / args.root / "timealign_fedasync_comparison.json",
    )
    aggregate_path = (
        repo / "outputs/aggregate/E1_balanced_entry_r2/per_seed_metrics.parquet"
    )
    aggregate = pd.read_parquet(aggregate_path)
    selected = load_yaml(repo / "configs/frozen/e1_selected_baseline.yaml")
    statistics = load_json(
        repo / "outputs/statistics/E1_balanced/no_harm_summary.json",
    )
    shared_fields = (
        "data_hash", "split_hash", "target_group_hash", "client_mapping_hash",
        "pi_target_hash", "event_trace_hash", "initial_model_hash",
        "protocol_config_hash",
    )
    required_artifacts = {
        "manifest.json", "resolved_config.yaml", "event_trace_ref.json",
        "metrics_window.parquet", "metrics_run.json", "predictions_test.parquet",
        "arrival_weights_test.parquet", "propensity_diagnostics.parquet",
        "p_propensity_history.parquet", "solver_diagnostics.parquet",
        "method_diagnostics.parquet", "system_metrics.json", "checkpoints",
        "stdout.log", "stderr.log",
    }
    gates = {
        "E1R2-G1": bool(
            "FLAMF-TimeAlign-Adapted" in spec
            and "not the original FLAMF implementation" in spec
            and "alpha" in spec
        ),
        "E1R2-G2": bool(
            controlled.groupby("fixture")["alpha_diff"].apply(
                lambda values: values.abs().sum(),
            ).min() > 1e-10
            and official_comparison["max_l1_alpha_difference"] > 1e-10
            and (
                runs["flamf_timealign_adapted"]
                / "method_diagnostics_timealign.parquet"
            ).exists()
        ),
        "E1R2-G3": bool(arrival["hard_gate_pass"]),
        "E1R2-G4": bool(
            histories
            and all(len(frame) > 0 for frame in histories)
            and all(set(frame["O"].unique()) == {0, 1} for frame in histories)
            and all(set(frame["source_split"]) == {"train"} for frame in histories)
        ),
        "E1R2-G5": bool(
            protocol["num_clients"] == 8
            and mapping["num_clients"] == 8
            and len(set(mapping["station_to_client"].values())) == 8
        ),
        "E1R2-G6": bool(
            all(item["generation_git_commit"] == commit for item in trace_manifests)
            and all(item["git_clean"] for item in trace_manifests)
            and all(item["clients"] == 8 for item in trace_manifests)
            and all(
                (
                    repo / f"outputs/event_traces/e1_balanced_seed{seed}"
                    / "events.parquet"
                ).exists()
                for seed in E1_SEEDS
            )
        ),
        "E1R2-G7": bool(
            set(runs) == expected
            and all(
                all((run / name).exists() for name in required_artifacts)
                for run in runs.values()
            )
            and all(
                len({item[field] for item in run_manifests}) == 1
                for field in shared_fields
            )
        ),
        "E1R2-G8": bool(
            run_metrics
            and all(item["first_stage_clip_rate"] <= 0.05 for item in run_metrics)
            and all(item["second_stage_clip_rate"] <= 0.05 for item in run_metrics)
            and all(item["median_n_eff"] >= 2 for item in run_metrics)
            and all(item["solver_failure_count"] == 0 for item in run_metrics)
        ),
        "E1R2-G9": bool(
            len(aggregate) == 5
            and selected["selected_baseline"] in expected
            and statistics["status"] == "DRY_RUN_SCHEMA_PASS"
            and statistics["formal_no_harm_conclusion"] is False
        ),
        "E1R2-G10": bool(
            clean
            and (repo / "logs/E1_ENTRY_R2_PYTEST.log").exists()
            and (repo / "logs/E1_ENTRY_R2_COMMANDS.log").exists()
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
    output = repo / "outputs/audits/E1_ENTRY_R2_GATE_RESULTS.json"
    dump_json(report, output)
    print(json.dumps(report["gates"], indent=2))
    return 0 if report["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

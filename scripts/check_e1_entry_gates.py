#!/usr/bin/env python3
"""Evaluate E1E-G1 through E1E-G8 from frozen artifacts."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from raven_mcs.experiments.e1_entry import E1_METHODS, E1_SEEDS, frozen_group_identity
from raven_mcs.utils.serialization import dump_json, load_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root", type=Path,
        default=ROOT / "outputs/entry_smoke/E1_ENTRY_SMOKE_seed26001",
    )
    args = parser.parse_args(argv)
    manifests = [
        load_json(path) for path in sorted((args.root / "runs").rglob("manifest.json"))
    ]
    group_path, group_hash = frozen_group_identity(ROOT)
    group_cfg = yaml.safe_load(group_path.read_text(encoding="utf-8"))
    g1 = (
        int(group_cfg["group_count"]) == 4
        and len(manifests) == 5
        and {item["target_group_hash"] for item in manifests} == {group_hash}
    )
    trace_manifest = load_json(
        ROOT / "outputs/event_traces/E1_BALANCED_EVENTTRACE_MANIFEST.json",
    )
    trace_audits = [
        load_json(ROOT / f"outputs/audits/e1_eventtrace_audit_seed{seed}.json")
        for seed in E1_SEEDS
    ]
    g2 = (
        len(trace_manifest["traces"]) == 5
        and all(item["hard_gate_pass"] for item in trace_audits)
    )
    prediction_gate = True
    for manifest in manifests:
        run_dir = args.root / "runs" / manifest["run_id"]
        prediction = pd.read_parquet(run_dir / "predictions_test.parquet")
        metrics = load_json(run_dir / "metrics_run.json")
        prediction_gate &= (
            prediction["unit_id"].is_unique
            and abs(
                metrics["Gap_mis"]
                - (metrics["RMSE_mu"] - metrics["RMSE_rho"])
            ) <= 1e-12
        )
    g3 = bool(prediction_gate and len(manifests) == 5)
    required_status = {
        "entry_smoke": "PASS", "metric_gate": "PASS",
        "solver_gate": "PASS", "eventtrace_gate": "PASS",
        "artifact_gate": "PASS",
    }
    g4 = (
        {item["method"] for item in manifests} == set(E1_METHODS)
        and all(item["hard_gate_status"] == required_status for item in manifests)
        and len({item["event_trace_hash"] for item in manifests}) == 1
        and len({item["initial_model_seed"] for item in manifests}) == 1
    )
    per_seed = pd.read_parquet(args.root / "aggregate/per_seed_metrics.parquet")
    g5 = (
        len(per_seed) == 5
        and not per_seed.duplicated(["seed", "method"]).any()
        and per_seed["config_hash"].nunique() == 1
        and per_seed["event_trace_hash"].nunique() == 1
    )
    baseline_path = ROOT / "configs/frozen/e1_selected_baseline.yaml"
    baseline = yaml.safe_load(baseline_path.read_text(encoding="utf-8"))
    g6 = (
        baseline.get("validation_split_only") is True
        and baseline.get("selected_baseline") in {
            "fedavg_window", "fedasync_window", "timealign_agg",
        }
        and baseline.get("test_metrics_read") is False
    )
    statistics = load_json(
        ROOT / "outputs/statistics/E1_balanced/no_harm_summary.json",
    )
    g7 = (
        statistics.get("status") == "DRY_RUN_SCHEMA_PASS"
        and statistics.get("formal_no_harm_conclusion") is False
        and statistics.get("baseline_method") == baseline["selected_baseline"]
    )
    clean = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT,
        capture_output=True, text=True, check=True,
    ).stdout == ""
    g8 = (
        clean
        and (ROOT / "logs/E1_ENTRY_SEAL_EXACT_COMMANDS.log").exists()
        and (ROOT / "logs/E1_ENTRY_SEAL_PYTEST.log").exists()
        and (ROOT / "deliverables/RAVEN_MCS_E1_ENTRY_SEAL_EVIDENCE.zip").exists()
        and all("PENDING" not in json.dumps(item["hard_gate_status"]) for item in manifests)
    )
    gates = {
        "E1E-G1": g1, "E1E-G2": g2, "E1E-G3": g3, "E1E-G4": g4,
        "E1E-G5": g5, "E1E-G6": g6, "E1E-G7": g7, "E1E-G8": g8,
    }
    result = {
        "gates": {name: "PASS" if passed else "FAIL" for name, passed in gates.items()},
        "all_pass": all(gates.values()),
        "e1_status": (
            "READY_FOR_TEACHER_AUTHORIZATION" if all(gates.values()) else "BLOCKED"
        ),
    }
    dump_json(result, args.root / "E1_ENTRY_GATE_RESULTS.json")
    dump_json(result, ROOT / "outputs/audits/E1_ENTRY_GATE_RESULTS.json")
    for gate, status in result["gates"].items():
        print(f"{gate}: {status}")
    return 0 if result["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

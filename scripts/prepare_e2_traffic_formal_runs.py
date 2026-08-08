#!/usr/bin/env python3
"""E2-TRAFFIC-FORMAL-RUNS-R1 prepare CLI (preflight / eventtrace / run-one / finalize)."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from raven_mcs.e2.traffic_balanced_canary import (
    build_traffic_schedule,
    load_traffic_targets,
    sha256_file,
)
from raven_mcs.e2.traffic_formal_runs import (
    EXPECTED_RUNS,
    EXPECTED_TRACES,
    FORMAL_SEEDS,
    FORBIDDEN_CANARY_SEED,
    METHOD_DISPLAY,
    METHODS,
    REGISTRY_SHA256_EXPECTED,
    SCENARIO_LABELS,
    SCENARIOS,
    SELECTED_STRENGTH,
    VALIDATION_SEEDS,
)
from raven_mcs.e2.traffic_formal_runs.stats import paired_raven_vs_baseline, summarize_vector
from raven_mcs.e2.traffic_real_runner import (
    generate_scenario_eventtrace,
    load_pi_target_traffic,
    load_profile_s1_registry,
    load_target_mu_traffic,
    run_method_on_trace,
    traffic_dataset,
)
from raven_mcs.aggregation.method_policy import get_method_policy
from raven_mcs.utils.serialization import dump_json

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts/e2_traffic_formal_runs_r1"
AUDIT = ART / "audits"
FROZEN_S1 = ROOT / "configs/frozen/e2_traffic_profiles_s1"
PACKAGE = "E2_TRAFFIC_FORMAL_RUNS_R1"


def _git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return "UNKNOWN"


def _dirty() -> bool:
    try:
        out = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)
        return bool(out.strip())
    except Exception:
        return True


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_preflight_snapshots() -> dict[str, Any]:
    ART.mkdir(parents=True, exist_ok=True)
    AUDIT.mkdir(parents=True, exist_ok=True)
    reg_path = FROZEN_S1 / "traffic_s1_s6_profile_registry.json"
    reg_sha = _sha(reg_path)
    if reg_sha != REGISTRY_SHA256_EXPECTED:
        payload = {
            "status": "BLOCKED_INPUT_IDENTITY_MISMATCH",
            "expected_registry_sha256": REGISTRY_SHA256_EXPECTED,
            "actual_registry_sha256": reg_sha,
        }
        dump_json(payload, ART / "FROZEN_INPUT_IDENTITY.json")
        return payload

    py_ver = subprocess.check_output([sys.executable, "--version"], text=True).strip()
    freeze = subprocess.run([sys.executable, "-m", "pip", "freeze"], capture_output=True, text=True)
    config = {
        "experiment_id": PACKAGE,
        "git_commit": _git_head(),
        "dirty_working_tree": _dirty(),
        "python_version": py_ver,
        "environment_summary_lines": len((freeze.stdout or "").splitlines()),
        "registry_path": reg_path.relative_to(ROOT).as_posix(),
        "registry_sha256": reg_sha,
        "profile": SELECTED_STRENGTH,
        "seeds": list(FORMAL_SEEDS),
        "scenarios": list(SCENARIOS),
        "methods": list(METHODS),
        "method_display": METHOD_DISPLAY,
        "hyperparameters": {
            "learning_rate": 0.01,
            "local_steps": 2,
            "a_max": 40.0,
            "s_max": 5,
            "standardization": "train_split_zscore",
            "n_windows": 100,
            "n_clients": 43,
            "n_protocol_atoms": 25800,
        },
        "expected_run_count": EXPECTED_RUNS,
        "expected_eventtrace_count": EXPECTED_TRACES,
        "expected_windows_per_run": 100,
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }
    dump_json(config, ART / "FORMAL_RUN_CONFIG.json")

    source_files = [
        "src/raven_mcs/e2/traffic_real_runner/__init__.py",
        "src/raven_mcs/e2/traffic_profiles/runner_consistency.py",
        "src/raven_mcs/e2/traffic_formal_runs/__init__.py",
        "src/raven_mcs/e2/traffic_formal_runs/stats.py",
        "src/raven_mcs/aggregation/method_policy.py",
        "src/raven_mcs/training/window_runner.py",
        "src/raven_mcs/training/client.py",
        "src/raven_mcs/metrics/accuracy.py",
        "scripts/prepare_e2_traffic_formal_runs.py",
        "scripts/_run_e2fr_ledger_sequence.py",
        "scripts/run_and_log.py",
        "scripts/check_e2_traffic_formal_runs_gates.py",
        "configs/frozen/e2_traffic_profiles_s1/traffic_s1_s6_profile_registry.json",
        "configs/frozen/e2_traffic_profiles_s1/traffic_s1_s6_runner_identity.json",
        "configs/frozen/e2_traffic_public_target/atomic_public_target.parquet",
        "data/processed/traffic/atomic_units.parquet",
    ]
    hashes = {}
    for rel in source_files:
        p = ROOT / rel
        if p.is_file():
            hashes[rel] = _sha(p)
    dump_json({"created_utc": datetime.now(timezone.utc).isoformat(), "files": hashes}, ART / "SOURCE_HASHES.json")

    canary_stop = ROOT / "outputs/e2_traffic_real_runner_canary/E2_TRAFFIC_REAL_RUNNER_CANARY_STOP_STATUS.json"
    identity = {
        "status": "PASS",
        "registry_sha256": reg_sha,
        "expected_registry_sha256": REGISTRY_SHA256_EXPECTED,
        "mismatch_count": 0,
        "profile": SELECTED_STRENGTH,
        "formal_seeds": list(FORMAL_SEEDS),
        "forbidden_canary_seed": FORBIDDEN_CANARY_SEED,
        "validation_seeds_forbidden": list(VALIDATION_SEEDS),
        "prior_canary_status": (
            json.loads(canary_stop.read_text(encoding="utf-8")).get("status")
            if canary_stop.is_file() else None
        ),
        "prior_next_authorized_round": (
            json.loads(canary_stop.read_text(encoding="utf-8")).get("next_authorized_round")
            if canary_stop.is_file() else None
        ),
        "source_file_count": len(hashes),
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }
    if identity["prior_next_authorized_round"] != "E2-TRAFFIC-FORMAL-RUNS-R1":
        identity["status"] = "BLOCKED_INPUT_IDENTITY_MISMATCH"
        identity["mismatch_count"] = 1
    dump_json(identity, ART / "FROZEN_INPUT_IDENTITY.json")
    return identity


def cmd_preflight() -> int:
    identity = write_preflight_snapshots()
    print(json.dumps(identity, indent=2))
    return 0 if identity.get("status") == "PASS" else 1


def cmd_generate_eventtrace(seed: int, scenario: str) -> int:
    if seed not in FORMAL_SEEDS:
        raise SystemExit(f"seed {seed} not in formal set")
    if scenario not in SCENARIOS:
        raise SystemExit(f"unknown scenario {scenario}")
    out_dir = ART / "eventtraces" / str(seed) / scenario
    if (out_dir / "training_eventtrace" / "trace_identity.json").is_file():
        # Resume: keep existing shared trace
        payload = json.loads((out_dir / "eventtrace_identity.json").read_text(encoding="utf-8"))
        print(json.dumps({"status": "EXISTS", **{k: payload.get(k) for k in ("seed", "scenario_id")}}, indent=2))
        return 0
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    registry = load_profile_s1_registry(ROOT)
    targets = load_traffic_targets(ROOT)
    schedule = build_traffic_schedule(targets)
    payload = generate_scenario_eventtrace(
        ROOT,
        scenario_id=scenario,
        label=SCENARIO_LABELS[scenario],
        registry=registry,
        schedule=schedule,
        unit_meta=targets["unit_meta"],
        out_dir=out_dir,
        seed=seed,
    )
    dump_json(payload, out_dir / "eventtrace_identity.json")
    print(json.dumps({
        "status": "PASS",
        "seed": seed,
        "scenario": scenario,
        "events_sha256": payload["eventtrace_identity"].get("events_sha256"),
        "n_event_rows": payload["n_event_rows"],
    }, indent=2))
    return 0


def cmd_run_one(seed: int, scenario: str, method: str, attempt: int = 1) -> int:
    if seed not in FORMAL_SEEDS:
        raise SystemExit(f"seed {seed} not in formal set")
    if scenario not in SCENARIOS or method not in METHODS:
        raise SystemExit("bad scenario/method")
    payload_path = ART / "eventtraces" / str(seed) / scenario / "eventtrace_identity.json"
    if not payload_path.is_file():
        raise SystemExit(f"missing eventtrace: {payload_path}")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    run_dir = ART / "runs" / str(seed) / scenario / method
    accepted = run_dir / "runtime_manifest.json"
    if accepted.is_file():
        man = json.loads(accepted.read_text(encoding="utf-8"))
        if man.get("status") == "PASS" and int(man.get("completed_windows", 0)) == 100:
            print(json.dumps({"status": "ALREADY_COMPLETE", "seed": seed, "scenario": scenario, "method": method}, indent=2))
            return 0
    # Preserve failed/incomplete attempt if present.
    if run_dir.exists() and any(run_dir.iterdir()):
        tomb = ART / "failed_attempts" / str(seed) / scenario / method / f"attempt_{attempt-1:03d}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        tomb.parent.mkdir(parents=True, exist_ok=True)
        if tomb.exists():
            shutil.rmtree(tomb)
        shutil.move(str(run_dir), str(tomb))
    run_dir.mkdir(parents=True, exist_ok=True)

    dataset = traffic_dataset(ROOT)
    pi = load_pi_target_traffic(ROOT)
    mu = load_target_mu_traffic(ROOT)
    man = run_method_on_trace(
        ROOT,
        method=method,
        scenario_id=scenario,
        label=SCENARIO_LABELS[scenario],
        trace_dir=ROOT / payload["training_eventtrace_dir"],
        run_dir=run_dir,
        dataset=dataset,
        pi_target=pi,
        target_mu=mu,
        hard_arrival_path=ROOT / payload["hard_dir"] / "hard_arrival_events.parquet",
        seed=seed,
    )
    man["attempt"] = int(attempt)
    man["eventtrace_events_sha256"] = payload["eventtrace_identity"].get("events_sha256")
    dump_json(man, run_dir / "runtime_manifest.json")
    ok = man.get("status") == "PASS" and int(man.get("completed_windows", 0)) == 100 and int(man.get("exit_code", 1)) == 0
    print(json.dumps({
        "status": man.get("status"),
        "seed": seed,
        "scenario": scenario,
        "method": method,
        "completed_windows": man.get("completed_windows"),
        "exit_code": man.get("exit_code"),
        "attempt": attempt,
    }, indent=2))
    return 0 if ok else 1


def _load_all_manifests() -> list[dict[str, Any]]:
    rows = []
    for seed in FORMAL_SEEDS:
        for scenario in SCENARIOS:
            for method in METHODS:
                path = ART / "runs" / str(seed) / scenario / method / "runtime_manifest.json"
                if path.is_file():
                    rows.append(json.loads(path.read_text(encoding="utf-8")))
    return rows


def cmd_finalize() -> int:
    manifests = _load_all_manifests()
    if len(manifests) != EXPECTED_RUNS:
        print(json.dumps({"status": "INCOMPLETE", "manifest_count": len(manifests), "expected": EXPECTED_RUNS}, indent=2))
        return 1
    if any(m.get("status") != "PASS" or int(m.get("completed_windows", 0)) != 100 for m in manifests):
        print(json.dumps({"status": "FAIL_RUNS"}, indent=2))
        return 1

    # EventTrace audit
    et_rows = []
    mismatch = 0
    for seed in FORMAL_SEEDS:
        for scenario in SCENARIOS:
            ident = ART / "eventtraces" / str(seed) / scenario / "eventtrace_identity.json"
            if not ident.is_file():
                mismatch += 1
                continue
            p = json.loads(ident.read_text(encoding="utf-8"))
            sha = p["eventtrace_identity"].get("events_sha256")
            et_rows.append({"seed": seed, "scenario": scenario, "events_sha256": sha})
            for method in METHODS:
                man = json.loads(
                    (ART / "runs" / str(seed) / scenario / method / "runtime_manifest.json").read_text(encoding="utf-8")
                )
                if man.get("eventtrace_events_sha256") != sha:
                    mismatch += 1
    et_df = pd.DataFrame(et_rows)
    et_df.to_csv(ART / "eventtrace_manifest.csv", index=False)
    et_df.to_parquet(ART / "eventtrace_manifest.parquet", index=False)
    dump_json({
        "eventtrace_count": len(et_rows),
        "expected": EXPECTED_TRACES,
        "cross_method_mismatch_count": mismatch,
        "status": "PASS" if len(et_rows) == EXPECTED_TRACES and mismatch == 0 else "FAIL",
    }, AUDIT / "EVENTTRACE_IDENTITY_AUDIT.json")

    main_rows = []
    group_rows = []
    runtime_rows = []
    for m in manifests:
        fm = m.get("final_metrics") or {}
        main_rows.append({
            "seed": int(m["seed"]),
            "scenario": m["scenario"],
            "method": m["method"],
            "method_display": m.get("method_display"),
            "RMSE_mu": fm.get("RMSE_mu"),
            "RMSE_rho": fm.get("RMSE_rho"),
            "Gap_mis": fm.get("Gap_mis"),
            "runtime_seconds": m.get("runtime_seconds"),
            "completed_windows": m.get("completed_windows"),
            "status": m.get("status"),
            "attempt": m.get("attempt", 1),
            "eventtrace_events_sha256": m.get("eventtrace_events_sha256"),
        })
        for g, val in (fm.get("group_rmse") or {}).items():
            group_rows.append({
                "seed": int(m["seed"]), "scenario": m["scenario"], "method": m["method"],
                "group": g, "RMSE": val,
            })
        runtime_rows.append({
            "seed": int(m["seed"]), "scenario": m["scenario"], "method": m["method"],
            "runtime_seconds": m.get("runtime_seconds"),
            "completed_windows": m.get("completed_windows"),
            "nonfinite_model_parameter_count": fm.get("nonfinite_model_parameter_count"),
            "nonfinite_loss_count": fm.get("nonfinite_loss_count"),
            "P2_solver_failure_count": fm.get("P2_solver_failure_count"),
            "denominator_zero_count": fm.get("denominator_zero_count"),
        })
    main = pd.DataFrame(main_rows).sort_values(["seed", "scenario", "method"]).reset_index(drop=True)
    main.to_csv(ART / "formal_results.csv", index=False)
    main.to_parquet(ART / "formal_results.parquet", index=False)
    pd.DataFrame(group_rows).to_csv(ART / "formal_group_metrics.csv", index=False)
    pd.DataFrame(runtime_rows).to_csv(ART / "formal_runtime_metrics.csv", index=False)
    pd.DataFrame(manifests).to_parquet(ART / "formal_run_manifest.parquet", index=False)

    # Isolation audit
    seeds_used = set(int(x) for x in main["seed"])
    isol = {
        "formal_seeds_only": seeds_used == set(FORMAL_SEEDS),
        "canary_seed_in_results": FORBIDDEN_CANARY_SEED in seeds_used,
        "validation_seed_hits": sorted(seeds_used & set(VALIDATION_SEEDS)),
        "status": "PASS" if seeds_used == set(FORMAL_SEEDS) else "FAIL",
    }
    dump_json(isol, AUDIT / "FORMAL_SEED_ISOLATION_AUDIT.json")

    # Statistics
    stat_rows = []
    for scenario in SCENARIOS:
        for method in METHODS:
            for metric in ("RMSE_mu", "RMSE_rho", "Gap_mis", "runtime_seconds"):
                vals = main.loc[(main["scenario"] == scenario) & (main["method"] == method), metric].to_numpy()
                s = summarize_vector(vals)
                stat_rows.append({
                    "scenario": scenario, "method": method, "metric": metric, **s,
                })
    stats_df = pd.DataFrame(stat_rows)
    stats_df.to_csv(ART / "formal_statistics.csv", index=False)
    dump_json({"rows": stat_rows, "ci_method": "normal_approx_mean_z1.96"}, ART / "formal_statistics.json")

    paired_rows = []
    for scenario in SCENARIOS:
        for baseline in METHODS:
            if baseline == "raven":
                continue
            for metric in ("RMSE_mu", "RMSE_rho", "Gap_mis"):
                paired_rows.append(paired_raven_vs_baseline(
                    main, metric=metric, baseline_method=baseline, scenario=scenario,
                ))
    paired_df = pd.DataFrame(paired_rows)
    paired_df.to_csv(ART / "paired_comparisons.csv", index=False)

    # Semantic audit (policy-based, same as canary)
    raven_ok = all(get_method_policy("raven").uses_debt for _ in [0])
    base_illegal = 0
    for method in METHODS:
        if method == "raven":
            continue
        pol = get_method_policy(method)
        if method in {"fedavg_window", "fedasync_window", "flamf_timealign_adapted"}:
            if pol.uses_design_ratio or pol.uses_debt:
                base_illegal += 1
        if method == "twostage_hajek" and (pol.uses_debt or pol.uses_instant_calibration):
            base_illegal += 1
    dump_json({
        "status": "PASS" if raven_ok and base_illegal == 0 else "FAIL",
        "baseline_illegal_count": base_illegal,
    }, AUDIT / "METHOD_SEMANTIC_AUDIT.json")

    num = {
        "nonfinite_model_parameter_count": int(sum(int(r.get("nonfinite_model_parameter_count") or 0) for r in runtime_rows)),
        "nonfinite_loss_count": int(sum(int(r.get("nonfinite_loss_count") or 0) for r in runtime_rows)),
        "nonfinite_metric_count": int((~np.isfinite(main[["RMSE_mu", "RMSE_rho", "Gap_mis"]].to_numpy().astype(float))).sum()),
        "denominator_zero_count": int(sum(int(r.get("denominator_zero_count") or 0) for r in runtime_rows)),
        "P2_solver_failure_count": int(sum(int(r.get("P2_solver_failure_count") or 0) for r in runtime_rows)),
    }
    num["status"] = "PASS" if all(v == 0 for k, v in num.items() if k != "status") else "FAIL"
    dump_json(num, AUDIT / "NUMERICAL_INTEGRITY_AUDIT.json")

    failed_attempts = 0
    fa_root = ART / "failed_attempts"
    if fa_root.is_dir():
        failed_attempts = sum(1 for _ in fa_root.rglob("runtime_manifest.json"))

    stop = {
        "protocol": PACKAGE,
        "status": "PENDING_FORMAL_GATES",
        "selected_strength": SELECTED_STRENGTH,
        "formal_seed_count": len(FORMAL_SEEDS),
        "scenario_count": len(SCENARIOS),
        "method_count": len(METHODS),
        "expected_runs": EXPECTED_RUNS,
        "accepted_runs": int(len(main)),
        "failed_logical_runs": 0,
        "eventtrace_count": int(len(et_rows)),
        "cross_method_trace_mismatch_count": mismatch,
        "retry_attempt_directories": failed_attempts,
        "seed_replacement_count": 0,
        "registry_sha256": REGISTRY_SHA256_EXPECTED,
        "runtime_commit": _git_head(),
        "numerical_status": num["status"],
        "isolation_status": isol["status"],
        "e3_e9_status": "NOT_STARTED",
        "canary_seed_excluded": True,
        "next_authorized_round": None,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "runtime_min": float(main["runtime_seconds"].min()),
        "runtime_median": float(main["runtime_seconds"].median()),
        "runtime_max": float(main["runtime_seconds"].max()),
    }
    dump_json(stop, ART / "E2_TRAFFIC_FORMAL_RUNS_STOP_STATUS.json")
    dump_json({"seed": "all", "manifests": len(manifests)}, ART / "formal_run_manifest_summary.json")
    print(json.dumps({"status": stop["status"], "accepted_runs": stop["accepted_runs"]}, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--generate-eventtrace", action="store_true")
    mode.add_argument("--run-one", action="store_true")
    mode.add_argument("--finalize", action="store_true")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--scenario", type=str, default=None)
    parser.add_argument("--method", type=str, default=None)
    parser.add_argument("--attempt", type=int, default=1)
    args = parser.parse_args(argv)
    ART.mkdir(parents=True, exist_ok=True)
    if args.preflight:
        return cmd_preflight()
    if args.generate_eventtrace:
        if args.seed is None or not args.scenario:
            raise SystemExit("--generate-eventtrace requires --seed and --scenario")
        return cmd_generate_eventtrace(args.seed, args.scenario)
    if args.run_one:
        if args.seed is None or not args.scenario or not args.method:
            raise SystemExit("--run-one requires --seed --scenario --method")
        return cmd_run_one(args.seed, args.scenario, args.method, attempt=args.attempt)
    if args.finalize:
        return cmd_finalize()
    raise SystemExit("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())

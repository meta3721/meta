#!/usr/bin/env python3
"""Resume-capable ledger sequence for E2-TRAFFIC-FORMAL-RUNS-R1 (600 runs)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = str(ROOT / ".venv" / "Scripts" / "python.exe")
PACKAGE = "E2_TRAFFIC_FORMAL_RUNS_R1"
LEDGER = f"logs/{PACKAGE}_EXACT_COMMANDS.jsonl"
ART = ROOT / "artifacts/e2_traffic_formal_runs_r1"
PROGRESS = ART / "progress.json"

FORMAL_SEEDS = list(range(30001, 30021))
SCENARIOS = [
    "balanced", "opportunity_only", "observation_only",
    "usable_only", "complete_aligned", "complete_counteracting",
]
METHODS = [
    "fedavg_window", "fedasync_window", "flamf_timealign_adapted",
    "twostage_hajek", "raven",
]
FROZEN_INPUTS = [
    "configs/frozen/e2_traffic_profiles_s1/traffic_s1_s6_profile_registry.json",
    "configs/frozen/e2_traffic_profiles_s1/traffic_s1_s6_runner_identity.json",
    "src/raven_mcs/aggregation/method_policy.py",
]


def _load_progress() -> dict:
    if PROGRESS.is_file():
        return json.loads(PROGRESS.read_text(encoding="utf-8"))
    return {"completed": [], "failed_attempts": []}


def _save_progress(prog: dict) -> None:
    ART.mkdir(parents=True, exist_ok=True)
    PROGRESS.write_text(json.dumps(prog, indent=2) + "\n", encoding="utf-8")


def _is_complete(seed: int, scenario: str, method: str) -> bool:
    path = ART / "runs" / str(seed) / scenario / method / "runtime_manifest.json"
    if not path.is_file():
        return False
    man = json.loads(path.read_text(encoding="utf-8"))
    return man.get("status") == "PASS" and int(man.get("completed_windows", 0)) == 100


def run(
    label: str,
    command: list[str],
    *,
    outputs: list[str] | None = None,
    inputs: list[str] | None = None,
    seed: int | None = None,
    scenario: str | None = None,
    method: str | None = None,
    run_kind: str | None = None,
    expected_windows: int | None = None,
    run_id: str | None = None,
) -> int:
    wrapped = [
        PYTHON, "scripts/run_and_log.py",
        "--ledger", LEDGER,
        "--label", label,
        "--stdout-log", f"logs/e2fr_{label}.stdout.log",
        "--stderr-log", f"logs/e2fr_{label}.stderr.log",
        "--profile-id", "PROFILE-S1",
    ]
    if run_id:
        wrapped.extend(("--run-id", run_id))
    if run_kind:
        wrapped.extend(("--run-kind", run_kind))
    if seed is not None:
        wrapped.extend(("--seed", str(seed)))
    if scenario is not None:
        wrapped.extend(("--scenario", scenario))
    if method is not None:
        wrapped.extend(("--method", method))
    if expected_windows is not None:
        wrapped.extend(("--expected-windows", str(expected_windows)))
    for path in inputs or []:
        wrapped.extend(("--input", path))
    for path in outputs or []:
        wrapped.extend(("--output", path))
    wrapped.extend(("--", *command))
    print(f">> {label}", flush=True)
    return subprocess.call(wrapped, cwd=ROOT)


def main() -> int:
    if not Path(PYTHON).is_file():
        raise SystemExit(f"missing interpreter: {PYTHON}")
    ART.mkdir(parents=True, exist_ok=True)
    ledger = ROOT / LEDGER
    # Do not wipe ledger on resume; only create if missing.
    if not ledger.is_file():
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text("", encoding="utf-8")

    prog = _load_progress()

    code = run(
        "e2fr_preflight",
        [PYTHON, "scripts/prepare_e2_traffic_formal_runs.py", "--preflight"],
        outputs=[
            "artifacts/e2_traffic_formal_runs_r1/FORMAL_RUN_CONFIG.json",
            "artifacts/e2_traffic_formal_runs_r1/SOURCE_HASHES.json",
            "artifacts/e2_traffic_formal_runs_r1/FROZEN_INPUT_IDENTITY.json",
        ],
        inputs=list(FROZEN_INPUTS),
        run_kind="preflight",
    )
    if code != 0:
        return code

    # Deterministic order: seed → scenario → (trace) → methods
    for seed in FORMAL_SEEDS:
        for scenario in SCENARIOS:
            et_label = f"e2fr_eventtrace_seed{seed}__{scenario}"
            et_ident = f"artifacts/e2_traffic_formal_runs_r1/eventtraces/{seed}/{scenario}/eventtrace_identity.json"
            et_trace = (
                f"artifacts/e2_traffic_formal_runs_r1/eventtraces/{seed}/{scenario}/"
                "training_eventtrace/trace_identity.json"
            )
            if not (ROOT / et_trace).is_file():
                code = run(
                    et_label,
                    [
                        PYTHON, "scripts/prepare_e2_traffic_formal_runs.py",
                        "--generate-eventtrace", "--seed", str(seed), "--scenario", scenario,
                    ],
                    outputs=[et_ident, et_trace],
                    inputs=list(FROZEN_INPUTS),
                    seed=seed,
                    scenario=scenario,
                    run_kind="eventtrace_generation",
                )
                if code != 0:
                    return code

            for method in METHODS:
                key = f"{seed}:{scenario}:{method}"
                if _is_complete(seed, scenario, method):
                    if key not in prog["completed"]:
                        prog["completed"].append(key)
                        _save_progress(prog)
                    print(f"SKIP_COMPLETE {key}", flush=True)
                    continue

                prior_fails = sum(
                    1 for x in prog.get("failed_attempts", []) if x.startswith(key + ":")
                )
                success = False
                for attempt in range(prior_fails + 1, prior_fails + 3):
                    run_id = f"formal_seed{seed}_{scenario}_{method}"
                    label = f"e2fr_train_seed{seed}__{scenario}__{method}__attempt{attempt}"
                    run_dir = f"artifacts/e2_traffic_formal_runs_r1/runs/{seed}/{scenario}/{method}"
                    outputs = [
                        f"{run_dir}/runtime_manifest.json",
                        f"{run_dir}/config_snapshot.json",
                        f"{run_dir}/window_metrics.parquet",
                        f"{run_dir}/runner_diagnostics.parquet",
                        f"{run_dir}/checkpoints/final.pt",
                    ]
                    inputs = list(FROZEN_INPUTS) + [et_trace, et_ident]
                    code = run(
                        label,
                        [
                            PYTHON, "scripts/prepare_e2_traffic_formal_runs.py",
                            "--run-one", "--seed", str(seed), "--scenario", scenario,
                            "--method", method, "--attempt", str(attempt),
                        ],
                        outputs=outputs,
                        inputs=inputs,
                        seed=seed,
                        scenario=scenario,
                        method=method,
                        run_kind="training",
                        expected_windows=100,
                        run_id=f"{run_id}__attempt{attempt}",
                    )
                    if code == 0 and _is_complete(seed, scenario, method):
                        success = True
                        break
                    prog.setdefault("failed_attempts", []).append(f"{key}:{attempt}")
                    _save_progress(prog)
                    print(f"TRAINING_FAILED {key} attempt={attempt} exit={code}", flush=True)
                if not success:
                    return 1
                prog["completed"].append(key)
                _save_progress(prog)

    # Ensure all complete before finalize
    missing = [
        f"{s}:{sc}:{m}"
        for s in FORMAL_SEEDS for sc in SCENARIOS for m in METHODS
        if not _is_complete(s, sc, m)
    ]
    if missing:
        print(json.dumps({"status": "INCOMPLETE", "missing_count": len(missing), "sample": missing[:10]}, indent=2))
        return 1

    code = run(
        "e2fr_finalize",
        [PYTHON, "scripts/prepare_e2_traffic_formal_runs.py", "--finalize"],
        outputs=[
            "artifacts/e2_traffic_formal_runs_r1/formal_results.csv",
            "artifacts/e2_traffic_formal_runs_r1/formal_results.parquet",
            "artifacts/e2_traffic_formal_runs_r1/E2_TRAFFIC_FORMAL_RUNS_STOP_STATUS.json",
        ],
        inputs=list(FROZEN_INPUTS),
        run_kind="finalization",
    )
    if code != 0:
        return code

    post = [
        (
            "formal_unit_tests",
            [PYTHON, "-m", "pytest", "-q",
             "tests/unit/test_e2_traffic_formal_runs_core.py",
             "--junitxml=logs/e2_traffic_formal_runs_unit.xml"],
            ["logs/e2_traffic_formal_runs_unit.xml"],
        ),
        (
            "full_repository_pytest",
            [PYTHON, "-m", "pytest", "-q",
             "--junitxml=logs/e2_traffic_formal_runs_full_repository.xml"],
            ["logs/e2_traffic_formal_runs_full_repository.xml"],
        ),
        (
            "pip_check",
            [PYTHON, "-m", "pip", "check"],
            [],
        ),
        (
            "gates",
            [PYTHON, "scripts/check_e2_traffic_formal_runs_gates.py"],
            ["artifacts/e2_traffic_formal_runs_r1/gate_results.json"],
        ),
        (
            "export",
            [PYTHON, "scripts/export_e2_traffic_formal_runs_evidence.py"],
            [
                "deliverables/TO_SUBMIT_E2_TRAFFIC_FORMAL_RUNS_R1/TO_SUBMIT_E2_TRAFFIC_FORMAL_RUNS_R1.zip",
                "deliverables/TO_SUBMIT_E2_TRAFFIC_FORMAL_RUNS_R1/FINAL_DELIVERABLE_HASHES_VERIFY.json",
            ],
        ),
    ]
    for label, command, outputs in post:
        if label == "pip_check":
            code = run(label, command, run_kind="pip_check")
            (ROOT / "logs/e2fr_pip_check.txt").write_text("pip check completed\n", encoding="utf-8")
            if code != 0:
                return code
            continue
        code = run(label, command, outputs=outputs, run_kind=label)
        if code != 0:
            return code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

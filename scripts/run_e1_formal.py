#!/usr/bin/env python3
"""Seed-major scheduler for sealed E1-R2 formal and compatibility execution."""
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from raven_mcs.experiments.e1_entry import E1_METHODS  # noqa: E402
from raven_mcs.utils.serialization import dump_json, load_yaml  # noqa: E402
from e1_r2_common import (  # noqa: E402
    CALIBRATION_SEEDS,
    FORMAL_SEEDS,
    R2_HORIZON,
    run_r2_method,
    trace_dir,
    validate_frozen_r2_selection,
)

R2_CONFIG = ROOT / "configs/frozen/e1_r2_protocol.yaml"
SMOKE_OUTPUT = ROOT / "outputs/smoke/e1_r2_formal_runner_compatibility"


def _load_run_gates():
    path = ROOT / "scripts/check_e1_run_gates.py"
    spec = importlib.util.spec_from_file_location("check_e1_run_gates", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.check_e1_run_gates


def _git_clean() -> bool:
    return subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT,
        capture_output=True, text=True, check=True,
    ).stdout.strip() == ""


def _git_head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT,
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def _bool_arg(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise argparse.ArgumentTypeError("expected true or false")


def build_matrix(
    methods: list[str], seeds: list[int],
) -> list[dict[str, object]]:
    return [
        {"seed": seed, "method": method}
        for seed in seeds
        for method in methods
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", type=Path,
        default=R2_CONFIG,
    )
    parser.add_argument("--methods", nargs="+", default=list(E1_METHODS))
    parser.add_argument("--seeds", nargs="+", type=int)
    parser.add_argument("--windows", type=int)
    parser.add_argument("--formal", type=_bool_arg, default=True)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--restart-failed-exact", action="store_true")
    parser.add_argument("--dry-run-scheduler", action="store_true")
    args = parser.parse_args(argv)

    config = args.config.resolve()
    if config != R2_CONFIG.resolve():
        raise ValueError("E1-R2 execution requires configs/frozen/e1_r2_protocol.yaml")
    validate_frozen_r2_selection(ROOT)
    methods = list(args.methods)
    if args.smoke:
        if methods == list(E1_METHODS):
            methods = ["fedavg_window", "raven"]
        if methods != ["fedavg_window", "raven"]:
            raise ValueError(
                "smoke requires methods fedavg_window raven in that order"
            )
    elif methods != list(E1_METHODS):
        raise ValueError("E1-R2 execution requires frozen method order")
    if args.smoke:
        if args.formal:
            raise ValueError("--smoke requires --formal false")
        seeds = list(args.seeds or [CALIBRATION_SEEDS[0]])
        windows = 2 if args.windows is None else int(args.windows)
        output_root = args.output_root or SMOKE_OUTPUT
        if seeds != [27001] or windows != 2:
            raise ValueError("smoke allows only calibration seed 27001 and 2 windows")
        if output_root.resolve() != SMOKE_OUTPUT.resolve():
            raise ValueError(
                "smoke output must be outputs/smoke/e1_r2_formal_runner_compatibility"
            )
    else:
        if not args.formal:
            raise ValueError("--formal false is allowed only with --smoke")
        seeds = list(args.seeds or FORMAL_SEEDS)
        windows = R2_HORIZON if args.windows is None else int(args.windows)
        output_root = args.output_root or ROOT / "outputs/runs"

    if not args.dry_run_scheduler:
        if args.formal and seeds != list(FORMAL_SEEDS):
            raise ValueError("formal execution requires frozen seeds 28001-28005")
        if args.formal and windows != R2_HORIZON:
            raise RuntimeError("formal scheduler requires --windows 100")
        if args.formal and not _git_clean():
            raise RuntimeError("formal execution requires a clean git worktree")

    protocol = load_yaml(config)
    matrix = build_matrix(methods, seeds)
    progress_path = ROOT / "logs/E1_FORMAL_PROGRESS.json"
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    start = datetime.now(timezone.utc)
    progress: dict[str, object] = {
        "total_runs": len(matrix),
        "completed_runs": 0,
        "passed_runs": 0,
        "failed_runs": 0,
        "current_seed": None,
        "current_method": None,
        "current_window": None,
        "current_run_id": None,
        "last_completed_run": None,
        "start_time": start.isoformat(),
        "last_update_time": start.isoformat(),
        "estimated_remaining_sec": None,
        "formal_performance_result": False,
        "protocol_version": "E1-R2",
        "formal": bool(args.formal),
        "smoke": bool(args.smoke),
        "dry_run_scheduler": bool(args.dry_run_scheduler),
        "execution_commit": _git_head(),
        "planned": matrix,
        "completed": [],
        "failed": [],
    }

    if args.dry_run_scheduler:
        progress.update({
            "routing_verified": True,
            "seed_major_order": True,
            "matrix_size": len(matrix),
            "note": (
                "Scheduler dry-run only; no formal 100-window performance "
                "result was produced."
            ),
        })
        dump_json(progress, progress_path)
        print(json.dumps({
            "dry_run_scheduler": True,
            "formal_performance_result": False,
            "matrix_size": len(matrix),
            "first": matrix[0] if matrix else None,
            "last": matrix[-1] if matrix else None,
        }, indent=2))
        return 0

    if protocol.get("protocol_status") != "FROZEN_POST_SELECTION":
        raise RuntimeError("R2 protocol is not frozen post-selection")

    check_e1_run_gates = _load_run_gates()
    execution_head = _git_head()
    tick0 = time.perf_counter()
    for index, item in enumerate(matrix):
        seed = int(item["seed"])
        method = str(item["method"])
        progress["current_seed"] = seed
        progress["current_method"] = method
        progress["current_window"] = windows
        progress["last_update_time"] = datetime.now(timezone.utc).isoformat()
        dump_json(progress, progress_path)
        try:
            if args.formal and _git_head() != execution_head:
                raise RuntimeError("runtime HEAD changed during formal execution")
            role = "formal" if args.formal else "calibration"
            run_dir = run_r2_method(
                ROOT,
                role=role,
                method=method,
                seed=seed,
                custom_trace_dir=trace_dir(ROOT, role, seed),
                windows=windows,
                device=args.device,
                output_root=output_root,
                formal=bool(args.formal),
                smoke=bool(args.smoke),
            )
            if args.formal and _git_head() != execution_head:
                raise RuntimeError("runtime HEAD changed during formal execution")
            report = check_e1_run_gates(run_dir)
            if not report["all_pass"]:
                raise RuntimeError(
                    f"per-run hard gates failed: {run_dir}"
                )
            progress["completed"].append({
                "run_dir": str(run_dir.relative_to(ROOT)),
                "seed": seed,
                "method": method,
            })
            progress["passed_runs"] = len(progress["completed"])
            progress["last_completed_run"] = str(run_dir)
            progress["current_run_id"] = run_dir.name
        except Exception as exc:  # noqa: BLE001
            progress["failed"].append({
                "seed": seed, "method": method, "error": str(exc),
            })
            progress["failed_runs"] = len(progress["failed"])
            if args.fail_fast:
                progress["last_update_time"] = (
                    datetime.now(timezone.utc).isoformat()
                )
                dump_json(progress, progress_path)
                print(json.dumps(progress, indent=2))
                return 1
        done = len(progress["completed"]) + len(progress["failed"])
        progress["completed_runs"] = done
        elapsed = time.perf_counter() - tick0
        if done:
            progress["estimated_remaining_sec"] = (
                (elapsed / done) * (len(matrix) - done)
            )
        progress["last_update_time"] = datetime.now(timezone.utc).isoformat()
        dump_json(progress, progress_path)

    progress["formal_performance_result"] = bool(
        args.formal and not progress["failed"] and len(progress["completed"]) == 25
    )
    progress["smoke_compatibility_pass"] = bool(
        args.smoke and not progress["failed"] and len(progress["completed"]) == 2
    )
    progress["finished_at"] = datetime.now(timezone.utc).isoformat()
    dump_json(progress, progress_path)
    print(json.dumps({
        "formal_performance_result": progress["formal_performance_result"],
        "passed_runs": progress["passed_runs"],
        "failed_runs": progress["failed_runs"],
        "execution_commit": progress["execution_commit"],
    }, indent=2))
    success = (
        progress["formal_performance_result"]
        if args.formal
        else progress["smoke_compatibility_pass"]
    )
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())

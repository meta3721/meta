#!/usr/bin/env python3
"""Evaluate E1-R2 freeze-seal gates R2FS-G1 through R2FS-G10."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import yaml

AUTHORIZED = "53e277c53b01695330652b8e1bc8a234909d56e5"


def _load_script(root: Path, name: str) -> ModuleType:
    path = root / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_r2fs_{name}", path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def evaluate_freeze_seal_gates(
    root: Path, mode: str = "review"
) -> dict[str, Any]:
    root = Path(root).resolve()
    protocol_path = root / "configs/frozen/e1_r2_protocol.yaml"
    protocol = yaml.safe_load(protocol_path.read_text("utf-8")) if protocol_path.is_file() else {}
    manifest_path = root / "configs/frozen/E1_R2_FROZEN_CONFIG_MANIFEST.json"
    manifest = _json(manifest_path)
    source = _json(
        root / "outputs/audits/e1_r2_source_identity/E1_R2_C1_SOURCE_IDENTITY.json"
    )
    trace = _json(root / "outputs/audits/E1_R2_TRACE_CLEAN_IDENTITY.json")
    noninspection = _json(
        root / "outputs/audits/E1_R2_FORMAL_SEED_NONINSPECTION.json"
    )
    provenance = _json(root / str(
        protocol.get("selection_provenance", {}).get("artifact", "")
    ))
    preflight_mod = _load_script(root, "check_e1_r2_formal_preflight")
    rebuild_mod = _load_script(root, "rebuild_e1_r2_frozen_manifest")
    preflight = preflight_mod.check_preflight(root, mode)
    try:
        reproducible = rebuild_mod.build_manifest(root) == manifest
    except (FileNotFoundError, RuntimeError, TypeError, ValueError):
        reproducible = False
    forbidden = {"candidate_commit", "execution_commit", "git_commit"} & set(protocol)
    gates = {
        "R2FS-G1": (
            protocol.get("authorized_algorithm_commit") == AUTHORIZED
            and bool(protocol.get("protocol_parent_commit"))
            and (
                preflight.get("runtime_git_clean") is True
                if mode == "final" else True
            )
        ),
        "R2FS-G2": (
            protocol.get("execution_commit_policy") == "runtime_clean_head"
            and not forbidden
            and (
                source.get("all_numeric_blobs_equivalent") is True
                if mode == "final" else True
            )
        ),
        "R2FS-G3": (
            source.get("status") == "PASS"
            and source.get("mode") == "C1"
            and source.get("all_numeric_blobs_equivalent") is True
            and preflight["checks"].get("deterministic_replay") == "PASS"
        ) if mode == "final" else (
            not source or source.get("mode") == "C1"
        ),
        "R2FS-G4": (
            provenance.get("status") == "PASS"
            and provenance.get("screening_stage") == "calibration"
            and provenance.get("final_selection_stage") == "validation"
            and provenance.get("required_source_count")
            == provenance.get("bound_source_count")
        ),
        "R2FS-G5": (
            manifest.get("active_selection_rules")
            == ["validation_lexicographic"]
            and protocol.get("selected_candidate") == "C2"
        ),
        "R2FS-G6": (
            reproducible
            and manifest.get("preselection_hash")
            != manifest.get("postselection_hash")
        ),
        "R2FS-G7": (
            preflight["checks"].get("runner_smoke") == "PASS"
            and protocol.get("main_clip_population") == "observed_records"
            and protocol.get("main_clip_aggregation")
            == "global_micro_per_seed"
            and protocol.get("main_clip_threshold") == 0.05
        ),
        "R2FS-G8": (
            preflight["checks"].get("runner_smoke") == "PASS"
            and preflight["checks"].get("aggregate_rejection") == "PASS"
        ),
        "R2FS-G9": (
            trace.get("status") == "PASS"
            and trace.get("trace_count") == 15
            and trace.get("formal_outcomes_accessed") is False
            and noninspection.get("status") == "PASS"
            and noninspection.get("formal_seed_training_records") == 0
            and noninspection.get("formal_seed_metric_records") == 0
            and noninspection.get("formal_seed_prediction_records") == 0
        ),
        "R2FS-G10": (
            preflight.get("status") == "PASS"
            and preflight["checks"].get("full_pytest_junit") == "PASS"
            and preflight.get("formal_experiments_run") == 0
        ),
    }
    statuses = {
        name: "PASS" if value else "FAIL" for name, value in gates.items()
    }
    return {
        "schema_version": 1,
        "mode": mode,
        "status": "PASS" if all(gates.values()) else "FAIL",
        "all_pass": all(gates.values()),
        "gates": statuses,
        "preflight": preflight,
        "formal_experiments_run": 0,
        "formal_outcomes_accessed": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--mode", choices=("review", "final"), default="review")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = evaluate_freeze_seal_gates(args.root, args.mode)
    output = args.output or args.root / (
        f"outputs/audits/E1_R2_FREEZE_SEAL_GATES_{args.mode.upper()}.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Evaluate R2P-G1..G10 without running an E1 experiment."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "configs/frozen/E1_R2_FROZEN_CONFIG_MANIFEST.json"
NONINSPECTION = "outputs/audits/E1_R2_FORMAL_SEED_NONINSPECTION.json"
FREEZE_STATUS = "outputs/audits/E1_R2_PROTOCOL_FREEZE_STATUS.json"
DRY_RUN = "outputs/audits/E1_R2_SCHEDULER_DRY_RUN.json"
REPORT = "outputs/audits/E1_R2_PROTOCOL_GATE_REPORT.json"
REQUIRED_ROLES = {
    "protocol", "weight_safety", "selected_baseline",
    "candidate_selection", "seed_registry", "eventtrace_manifest",
    "analysis", "scheduler",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(value), indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _resolve_recorded_path(root: Path, recorded: str) -> Path:
    path = Path(recorded)
    if path.is_absolute():
        return path
    return root / path


def scheduler_dry_run(
    scheduler: Mapping[str, Any],
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Check the formal matrix shape without importing any runner."""
    methods = scheduler.get("methods", [])
    seeds = scheduler.get("formal_seeds", [])
    windows = scheduler.get("num_windows")
    valid = (
        isinstance(methods, list)
        and bool(methods)
        and len(methods) == len(set(map(str, methods)))
        and isinstance(seeds, list)
        and bool(seeds)
        and len(seeds) == len(set(map(int, seeds)))
        and isinstance(windows, int)
        and windows > 0
        and scheduler.get("order") == "seed_major"
    )
    matrix = (
        [
            {"seed": int(seed), "method": str(method)}
            for seed in seeds
            for method in methods
        ]
        if valid
        else []
    )
    result = {
        "status": "PASS" if valid else "BLOCKED",
        "dry_run": True,
        "formal_execution_performed": False,
        "matrix_size": len(matrix),
        "expected_matrix_size": len(seeds) * len(methods)
        if isinstance(seeds, list) and isinstance(methods, list)
        else 0,
        "seed_major_order": bool(valid),
        "planned": matrix,
    }
    if output_path is not None:
        _write_json(output_path, result)
    return result


def evaluate_gates(root: Path) -> dict[str, Any]:
    manifest = _load_json(root / MANIFEST)
    freeze = _load_json(root / FREEZE_STATUS)
    noninspection = _load_json(root / NONINSPECTION)
    calibration = _load_json(
        root / "outputs/e1_r2/calibration/calibration_summary.json"
    )
    validation = _load_json(
        root / "outputs/e1_r2/validation/validation_summary.json"
    )
    registry = _load_yaml(root / "configs/e1_r2/candidate_registry.yaml")
    archive_hashes = _load_json(
        root / "archive/e1_r1_weight_safety_failure/ARCHIVE_HASHES.json"
    )
    r1_status = _load_json(
        root / "archive/e1_r1_weight_safety_failure/E1_R1_FINAL_STATUS.json"
    )
    files = manifest.get("files", {})
    if not isinstance(files, dict):
        files = {}

    by_role: dict[str, Path] = {}
    hashes_match = bool(files)
    for recorded, metadata in files.items():
        if not isinstance(metadata, dict):
            hashes_match = False
            continue
        path = _resolve_recorded_path(root, str(recorded))
        role = str(metadata.get("semantic_role", ""))
        by_role[role] = path
        hashes_match = bool(
            hashes_match
            and path.is_file()
            and metadata.get("sha256") == _sha256(path)
            and metadata.get("size_bytes") == path.stat().st_size
        )

    protocol = _load_yaml(by_role.get("protocol", Path("__missing__")))
    weight = _load_yaml(by_role.get("weight_safety", Path("__missing__")))
    analysis = _load_yaml(by_role.get("analysis", Path("__missing__")))
    scheduler = _load_yaml(by_role.get("scheduler", Path("__missing__")))
    dry_run = scheduler_dry_run(scheduler, root / DRY_RUN)
    provenance = protocol.get("selection_provenance", {})
    if not isinstance(provenance, dict):
        provenance = {}

    source_hashes_match = True
    for path_key, hash_key in (
        ("calibration_summary", "calibration_summary_sha256"),
        ("validation_summary", "validation_summary_sha256"),
    ):
        recorded = provenance.get(path_key)
        expected = provenance.get(hash_key)
        if not recorded or not expected:
            source_hashes_match = False
            continue
        source = _resolve_recorded_path(root, str(recorded))
        source_hashes_match = bool(
            source_hashes_match
            and source.is_file()
            and _sha256(source) == expected
        )

    formal_seeds = protocol.get("formal_seeds", [])
    calibration_seeds = protocol.get("calibration_seeds", [])
    validation_seeds = protocol.get("validation_seeds", [])
    methods = protocol.get("methods", [])
    archive_ok = bool(archive_hashes.get("files"))
    for recorded, expected in archive_hashes.get("files", {}).items():
        path = root / "archive/e1_r1_weight_safety_failure" / recorded
        archive_ok = bool(
            archive_ok and path.is_file() and _sha256(path) == expected
        )
    seed_sets = [
        set(map(int, calibration_seeds)),
        set(map(int, validation_seeds)),
        set(map(int, formal_seeds)),
        {26001, 26002, 26003, 26004, 26005},
    ]
    seeds_disjoint = all(
        not seed_sets[i] & seed_sets[j]
        for i in range(len(seed_sets))
        for j in range(i + 1, len(seed_sets))
    )
    gates: dict[str, bool | None] = {
        "R2P-G1": (
            archive_ok
            and r1_status.get("E1_R1_weight_safety") == "FAIL"
            and r1_status.get("remaining_runs") == "PERMANENTLY_STOPPED"
        ) if archive_hashes and r1_status else None,
        "R2P-G2": (
            protocol.get("main_clip_population") == "observed_records"
            and protocol.get("main_clip_aggregation") == "global_micro_per_seed"
            and protocol.get("main_clip_comparison") == "raw_weight > a_max + 1e-12"
            and protocol.get("main_clip_threshold") == 0.05
        ) if protocol else None,
        "R2P-G3": (
            seeds_disjoint
            and len(calibration_seeds) == 5
            and len(validation_seeds) == 5
            and len(formal_seeds) == 5
        ) if protocol else None,
        "R2P-G4": (
            protocol.get("validation_horizon") == 100
            and protocol.get("formal_horizon") == 100
            and calibration.get("protocol", {}).get("num_windows") == 100
        ) if protocol and calibration else None,
        "R2P-G5": (
            registry.get("registry_stage") == "PRE_RUN"
            and 0 < len(registry.get("candidates", {})) <= 8
            and bool(registry.get("candidate_registry_hash"))
        ) if registry else None,
        "R2P-G6": (
            calibration.get("calibration_complete") is True
            and bool(calibration.get("passed_candidates"))
            and all(
                value in {"PASSED", "REJECTED"}
                for value in calibration.get("candidate_status", {}).values()
            )
        ) if calibration else None,
        "R2P-G7": (
            validation.get("validation_pass") is True
            and bool(validation.get("selected_validation_baseline"))
            and bool(validation.get("passed_candidates"))
        ) if validation else None,
        "R2P-G8": (
            bool(validation.get("selected_candidate"))
            and validation.get("test_read_count") == 0
            and validation.get("formal_seed_read_count") == 0
        ) if validation else None,
        "R2P-G9": (
            noninspection.get("status") == "PASS"
            and noninspection.get("formal_seed_training_records") == 0
            and noninspection.get("formal_seed_metric_records") == 0
            and noninspection.get("formal_seed_prediction_records") == 0
        ) if noninspection else None,
        "R2P-G10": (
            freeze.get("status") == "PASS"
            and manifest.get("status") == "FROZEN_POST_SELECTION"
            and REQUIRED_ROLES.issubset(by_role)
            and hashes_match
            and source_hashes_match
            and protocol.get("execution_status") == "NOT_STARTED"
            and protocol.get("authorization_status") == "READY_FOR_TEACHER_REVIEW"
            and manifest.get("formal_experiments_run") == 0
            and scheduler.get("formal_execution_performed") is False
            and freeze.get("formal_experiments_run") == 0
            and dry_run["status"] == "PASS"
        ) if manifest and scheduler and freeze else None,
    }
    gate_statuses = {
        name: "BLOCKED" if value is None else ("PASS" if value else "FAIL")
        for name, value in gates.items()
    }
    if all(status == "PASS" for status in gate_statuses.values()):
        overall = "PASS"
    elif any(status == "FAIL" for status in gate_statuses.values()):
        overall = "FAIL"
    else:
        overall = "BLOCKED"
    return {
        "status": overall,
        "gates": gate_statuses,
        "all_pass": overall == "PASS",
        "formal_experiments_run": 0,
        "scheduler_dry_run": dry_run,
        "missing_prerequisites": [
            name for name, status in gate_statuses.items() if status == "BLOCKED"
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    result = evaluate_gates(root)
    _write_json(args.output or root / REPORT, result)
    print(json.dumps(result, indent=2))
    return {"PASS": 0, "FAIL": 1, "BLOCKED": 2}[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())

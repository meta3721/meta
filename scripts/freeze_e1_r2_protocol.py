#!/usr/bin/env python3
"""Freeze the E1-R2 protocol from completed post-selection evidence only.

This script is deliberately a serializer/validator.  It never imports or calls
the experiment runner and it refuses evidence that is not calibration- or
validation-only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CALIBRATION = (
    ROOT / "outputs/e1_r2/calibration/calibration_summary.json"
)
DEFAULT_VALIDATION = (
    ROOT / "outputs/e1_r2/validation/validation_summary.json"
)
DEFAULT_OUTPUT = ROOT / "configs/frozen"
MANIFEST_NAME = "E1_R2_FROZEN_CONFIG_MANIFEST.json"
FROZEN_NAMES = {
    "protocol": "e1_r2_protocol.yaml",
    "weight_safety": "e1_r2_weight_safety.yaml",
    "selected_baseline": "e1_r2_selected_baseline.yaml",
    "candidate_selection": "e1_r2_candidate_selection.json",
    "seed_registry": "e1_r2_seed_registry.yaml",
    "eventtrace_manifest": "e1_r2_eventtrace_manifest.json",
    "analysis": "e1_r2_analysis.yaml",
    "scheduler": "e1_r2_scheduler.yaml",
}
FORBIDDEN_SELECTION_SPLITS = {"test", "formal", "training", "train"}
R2_FORMAL_SEEDS = [28001, 28002, 28003, 28004, 28005]
R2_METHODS = [
    "fedavg_window",
    "fedasync_window",
    "flamf_timealign_adapted",
    "twostage_hajek",
    "raven",
]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _payload_hash(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(value), sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(value), indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _write_yaml(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(dict(value), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"missing mapping: {label}")
    return dict(value)


def _seeds(value: object, label: str) -> list[int]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"missing non-empty seed list: {label}")
    result = [int(seed) for seed in value]
    if len(result) != len(set(result)):
        raise ValueError(f"duplicate seeds in {label}")
    return result


def _selection_seeds(document: Mapping[str, Any]) -> set[int]:
    found: set[int] = set()
    for key in ("seed", "validation_seed", "calibration_seed"):
        if key in document and document[key] is not None:
            found.add(int(document[key]))
    for key in ("seeds", "validation_seeds", "calibration_seeds", "selection_seeds"):
        value = document.get(key)
        if isinstance(value, list):
            found.update(int(seed) for seed in value)
    return found


def _assert_selection_only(
    calibration: Mapping[str, Any],
    validation: Mapping[str, Any],
    formal_seeds: list[int],
) -> None:
    for label, document in (
        ("calibration", calibration),
        ("validation", validation),
    ):
        split_values = {
            str(document[key]).lower()
            for key in ("split", "selection_split", "evaluation_split")
            if document.get(key) is not None
        }
        if split_values & FORBIDDEN_SELECTION_SPLITS:
            raise ValueError(f"{label} evidence uses forbidden split: {split_values}")
        if document.get("formal") is True:
            raise ValueError(f"{label} evidence is marked formal")
        if int(document.get("test_read_count", 0)) != 0:
            raise ValueError(f"{label} evidence records test reads")
        if int(document.get("formal_seed_read_count", 0)) != 0:
            raise ValueError(f"{label} evidence records formal-seed reads")
        if document.get("test_metrics_read") is True:
            raise ValueError(f"{label} evidence records test metric inspection")
        overlap = _selection_seeds(document) & set(formal_seeds)
        if overlap:
            raise ValueError(
                f"{label} evidence inspected formal seed(s): {sorted(overlap)}"
            )


def build_frozen_payloads(
    calibration: Mapping[str, Any],
    validation: Mapping[str, Any],
    *,
    calibration_path: Path,
    validation_path: Path,
) -> dict[str, dict[str, Any]]:
    """Validate selection summaries and return deterministic frozen payloads."""
    protocol_input = _mapping(
        calibration.get(
            "selected_protocol",
            calibration.get(
                "protocol",
                {
                    "dataset": "sensorscope",
                    "scenario": "balanced",
                    "methods": R2_METHODS,
                    "formal_seeds": R2_FORMAL_SEEDS,
                    "num_windows": 100,
                    "local_steps": 2,
                },
            ),
        ),
        "selected_protocol",
    )
    formal_seeds = _seeds(
        protocol_input.get("formal_seeds", calibration.get("formal_seeds")),
        "formal_seeds",
    )
    _assert_selection_only(calibration, validation, formal_seeds)

    calibration_pass = calibration.get(
        "all_candidates_evaluated",
        calibration.get(
            "calibration_complete",
            calibration.get("status") == "PASS",
        ),
    )
    validation_pass = validation.get(
        "all_validation_gates_pass",
        validation.get(
            "validation_pass",
            validation.get("status") == "PASS",
        ),
    )
    if calibration_pass is not True:
        raise ValueError("calibration evidence is not complete")
    if validation_pass is not True:
        raise ValueError("validation evidence did not pass")

    calibration_passed = set(calibration.get("passed_candidates", []))
    validation_passed = set(validation.get("passed_candidates", []))
    eligible = sorted(calibration_passed & validation_passed)
    validation_candidates = validation.get("candidates", {})
    if not isinstance(validation_candidates, dict):
        validation_candidates = {}
    selected_candidate = validation.get(
        "selected_candidate", calibration.get("selected_candidate")
    )
    if selected_candidate is None and eligible:
        selected_candidate = min(
            eligible,
            key=lambda name: (
                float(validation_candidates.get(name, {}).get("a_max", float("inf"))),
                name,
            ),
        )
    weight_input = _mapping(
        calibration.get(
            "selected_weight_safety",
            protocol_input.get(
                "weight_safety",
                {
                    "selected_candidate": selected_candidate,
                    "selected_parameters": calibration.get("selected_parameters"),
                    "gates": calibration.get("gates"),
                },
            ),
        ),
        "selected_weight_safety",
    )
    if not isinstance(weight_input.get("selected_parameters"), dict):
        selected_a_max = validation.get(
            "selected_a_max", calibration.get("selected_a_max")
        )
        if selected_a_max is None and selected_candidate in validation_candidates:
            selected_a_max = validation_candidates[selected_candidate].get("a_max")
        if selected_a_max is None and isinstance(calibration.get("selection"), dict):
            selected_a_max = calibration["selection"].get("a_max")
        if selected_a_max is None:
            raise ValueError("calibration evidence must identify selected_parameters")
        weight_input["selected_parameters"] = {
            "p_min": 0.05,
            "pi_min": 1.0e-6,
            "a_max": float(selected_a_max),
            "q_min": 0.05,
            "d_max": 10.0,
        }
    if not isinstance(weight_input.get("gates"), dict):
        weight_input["gates"] = {
            "first_stage_observed_micro_true_exceed_max": 0.05,
            "second_stage_clip_rate_max": 0.05,
            "median_n_eff_min": 2.0,
        }
    weight_input["selected_parameters"].setdefault(
        "opportunity_forgetting", 0.95
    )
    weight_input["selected_candidate"] = selected_candidate
    analysis_input = _mapping(
        calibration.get(
            "analysis_plan",
            protocol_input.get(
                "analysis",
                {
                    "clip_population": "observed_records",
                    "clip_aggregation": "global_micro_per_seed",
                    "clip_comparison": "u > a_max + 1e-12",
                    "candidate_rule": "reject candidate if any calibration seed fails",
                    "selection_rule": "lowest passing a_max",
                    "validation_rule": "all validation seeds must pass",
                    "no_harm_threshold": 0.03,
                },
            ),
        ),
        "analysis_plan",
    )
    methods = protocol_input.get("methods", calibration.get("methods"))
    if not isinstance(methods, list) or not methods:
        raise ValueError("selected protocol must define methods")
    windows = int(protocol_input.get("num_windows", 0))
    if windows <= 0:
        raise ValueError("selected protocol must define positive num_windows")

    provenance = {
        "calibration_summary": calibration_path.as_posix(),
        "calibration_summary_sha256": _sha256(calibration_path),
        "validation_summary": validation_path.as_posix(),
        "validation_summary_sha256": _sha256(validation_path),
        "selection_split": "calibration",
        "confirmation_split": "validation",
        "selection_splits": ["calibration"],
        "test_read_count": 0,
        "formal_seed_inspection_count": 0,
    }
    calibration_seeds = _seeds(
        calibration.get("calibration_seeds", calibration.get("seeds")),
        "calibration_seeds",
    )
    validation_seeds = _seeds(
        validation.get("validation_seeds"), "validation_seeds"
    )
    selected_baseline_name = validation.get("selected_validation_baseline")
    if not selected_baseline_name:
        raise ValueError("validation evidence must identify selected baseline")
    protocol = {
        **protocol_input,
        "protocol_version": "E1-R2",
        "parent_failure": "E1-R1-WEIGHT-SAFETY",
        "main_clip_population": "observed_records",
        "main_clip_aggregation": "global_micro_per_seed",
        "main_clip_comparison": "raw_weight > a_max + 1e-12",
        "main_clip_threshold": 0.05,
        "validation_horizon": 100,
        "formal_horizon": 100,
        "local_steps": 2,
        "num_clients": 8,
        "S_max": 5,
        "calibration_seeds": calibration_seeds,
        "validation_seeds": validation_seeds,
        "formal_seeds": formal_seeds,
        "methods": [str(method) for method in methods],
        "num_windows": windows,
        "no_harm_threshold": 0.03,
        "execution_status": "NOT_STARTED",
        "protocol_status": "FROZEN_POST_SELECTION",
        "authorization_status": "READY_FOR_TEACHER_REVIEW",
        "selected_candidate": weight_input.get("selected_candidate"),
        "selected_validation_baseline": selected_baseline_name,
        "selection_provenance": provenance,
    }
    weight_safety = {
        **weight_input,
        "selection_data": "calibration_only",
        "confirmation_data": "validation_only",
        "validation_pass": True,
        "formal_seed_inspection_count": 0,
        "source_sha256": provenance["calibration_summary_sha256"],
    }
    analysis = {
        **analysis_input,
        "frozen_before_formal_execution": True,
        "formal_seed_inspection_count": 0,
        "test_outcome_adaptation": False,
    }
    scheduler = {
        "methods": protocol["methods"],
        "formal_seeds": formal_seeds,
        "num_windows": windows,
        "order": "seed_major",
        "matrix_size": len(formal_seeds) * len(protocol["methods"]),
        "dry_run_only_during_protocol_calibration": True,
        "formal_execution_performed": False,
    }
    selected_baseline = {
        "selected_baseline": selected_baseline_name,
        "selection_split": "validation",
        "validation_seeds": validation_seeds,
        "test_read_count": 0,
        "formal_seed_read_count": 0,
    }
    candidate_selection = {
        "selected_candidate": selected_candidate,
        "selected_parameters": weight_input["selected_parameters"],
        "selected_validation_baseline": selected_baseline_name,
        "eligible_candidates": eligible,
        "selection_split": "validation",
        "test_read_count": 0,
        "formal_seed_read_count": 0,
    }
    seed_registry = {
        "protocol_version": "E1-R2",
        "calibration_seeds": calibration_seeds,
        "validation_seeds": validation_seeds,
        "formal_seeds": formal_seeds,
        "r1_seeds_excluded": [26001, 26002, 26003, 26004, 26005],
        "roles_disjoint": True,
    }
    eventtrace_manifest = {
        role: _read_json(
            ROOT / f"data/frozen/e1_r2/{role}/ROLE_MANIFEST.json"
        )
        for role in ("calibration", "validation", "formal")
    }
    return {
        "protocol": protocol,
        "weight_safety": weight_safety,
        "selected_baseline": selected_baseline,
        "candidate_selection": candidate_selection,
        "seed_registry": seed_registry,
        "eventtrace_manifest": eventtrace_manifest,
        "analysis": analysis,
        "scheduler": scheduler,
    }


def freeze_protocol(
    calibration_path: Path,
    validation_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Create the R2 frozen files, or return BLOCKED without partial freezing."""
    missing = [
        path.as_posix()
        for path in (calibration_path, validation_path)
        if not path.is_file()
    ]
    if missing:
        return {
            "status": "BLOCKED",
            "reason": "prerequisite selection outputs are absent",
            "missing": missing,
            "formal_experiments_run": 0,
            "files_written": [],
        }
    try:
        calibration = _read_json(calibration_path)
        validation = _read_json(validation_path)
        payloads = build_frozen_payloads(
            calibration,
            validation,
            calibration_path=calibration_path,
            validation_path=validation_path,
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return {
            "status": "BLOCKED",
            "reason": str(exc),
            "missing": [],
            "formal_experiments_run": 0,
            "files_written": [],
        }

    output_dir.mkdir(parents=True, exist_ok=True)
    repo_root = output_dir.parents[1]
    provenance = payloads["protocol"]["selection_provenance"]
    for key in ("calibration_summary", "validation_summary"):
        source = Path(str(provenance[key]))
        try:
            provenance[key] = source.relative_to(repo_root).as_posix()
        except ValueError:
            provenance[key] = source.as_posix()
    paths: dict[str, Path] = {}
    for role, filename in FROZEN_NAMES.items():
        paths[role] = output_dir / filename
        if paths[role].suffix == ".json":
            _write_json(paths[role], payloads[role])
        else:
            _write_yaml(paths[role], payloads[role])
    files = {
        (
            path.relative_to(repo_root).as_posix()
            if path.is_relative_to(repo_root)
            else path.as_posix()
        ): {
            "semantic_role": role,
            "sha256": _sha256(path),
            "size_bytes": path.stat().st_size,
        }
        for role, path in sorted(paths.items())
    }
    manifest = {
        "seal": "E1_R2_PROTOCOL_CALIBRATION_R1",
        "manifest_schema_version": 1,
        "status": "FROZEN_POST_SELECTION",
        "formal_experiments_run": 0,
        "formal_seeds": payloads["protocol"]["formal_seeds"],
        "methods": payloads["protocol"]["methods"],
        "num_windows": payloads["protocol"]["num_windows"],
        "source_evidence": payloads["protocol"]["selection_provenance"],
        "protocol_file_hash": _sha256(paths["protocol"]),
        "protocol_payload_hash": _payload_hash(payloads["protocol"]),
        "files": files,
    }
    manifest_path = output_dir / MANIFEST_NAME
    _write_json(manifest_path, manifest)
    return {
        "status": "PASS",
        "reason": "R2 protocol frozen from post-selection evidence",
        "formal_experiments_run": 0,
        "files_written": [path.as_posix() for path in paths.values()]
        + [manifest_path.as_posix()],
        "manifest_sha256": _sha256(manifest_path),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--calibration-summary", type=Path, default=DEFAULT_CALIBRATION)
    parser.add_argument("--validation-summary", type=Path, default=DEFAULT_VALIDATION)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--status-output",
        type=Path,
        default=ROOT / "outputs/audits/E1_R2_PROTOCOL_FREEZE_STATUS.json",
    )
    args = parser.parse_args(argv)
    result = freeze_protocol(
        args.calibration_summary.resolve(),
        args.validation_summary.resolve(),
        args.output_dir.resolve(),
    )
    _write_json(args.status_output, result)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Bind E1-R2 screening and final selection to every source artifact."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import yaml

SOURCE_GROUPS = {
    "screening_calibration": (
        "configs/e1_r2/candidate_registry.yaml",
        "outputs/e1_r2/calibration/calibration_summary.json",
        "outputs/e1_r2/calibration/candidate_gate_matrix.csv",
        "outputs/e1_r2/calibration/passed_candidates.json",
    ),
    "final_validation": (
        "outputs/e1_r2/validation/baseline_selection.json",
        "outputs/e1_r2/validation/baseline_selection.parquet",
        "outputs/e1_r2/validation/candidate_seed_metrics.parquet",
        "outputs/e1_r2/validation/candidate_gate_matrix.csv",
        "outputs/e1_r2/validation/final_candidate_selection.json",
        "outputs/e1_r2/validation/validation_summary.json",
    ),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_selection_provenance(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    groups: dict[str, Any] = {}
    missing: list[str] = []
    for group, names in SOURCE_GROUPS.items():
        files: dict[str, Any] = {}
        for name in names:
            path = root / name
            if not path.is_file():
                missing.append(name)
                continue
            files[name] = {
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
        groups[group] = {
            "selection_split": "calibration" if group == "screening_calibration"
            else "validation",
            "files": files,
        }
    calibration = json.loads(
        (root / "outputs/e1_r2/calibration/calibration_summary.json").read_text(
            encoding="utf-8"
        )
    ) if not missing else {}
    validation = json.loads(
        (root / "outputs/e1_r2/validation/validation_summary.json").read_text(
            encoding="utf-8"
        )
    ) if not missing else {}
    valid = (
        not missing
        and calibration.get("selection_split") == "calibration"
        and validation.get("selection_split") == "validation"
        and calibration.get("formal_seed_read_count", 0) == 0
        and validation.get("formal_seed_read_count", 0) == 0
        and calibration.get("test_read_count", 0) == 0
        and validation.get("test_read_count", 0) == 0
    )
    return {
        "schema_version": 1,
        "status": "PASS" if valid else "FAIL",
        "screening_stage": "calibration",
        "final_selection_stage": "validation",
        "source_groups": groups,
        "required_source_count": sum(map(len, SOURCE_GROUPS.values())),
        "bound_source_count": sum(len(value["files"]) for value in groups.values()),
        "missing_sources": missing,
        "formal_seed_read_count": 0,
        "test_read_count": 0,
        "formal_outcomes_accessed": False,
    }


def write_selection_provenance(
    root: Path,
    *,
    output: Path | None = None,
    protocol_path: Path | None = None,
) -> dict[str, Any]:
    root = Path(root).resolve()
    result = build_selection_provenance(root)
    output = output or root / "outputs/audits/E1_R2_SELECTION_PROVENANCE.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    protocol_path = protocol_path or root / "configs/frozen/e1_r2_protocol.yaml"
    if result["status"] == "PASS" and protocol_path.is_file():
        protocol = yaml.safe_load(protocol_path.read_text(encoding="utf-8"))
        if not isinstance(protocol, dict):
            raise TypeError("R2 protocol must be a mapping")
        protocol["selection_provenance"] = {
            "screening_split": "calibration",
            "final_selection_split": "validation",
            "artifact": output.relative_to(root).as_posix(),
            "artifact_sha256": sha256_file(output),
            "source_groups": result["source_groups"],
            "formal_seed_read_count": 0,
            "test_read_count": 0,
        }
        protocol_path.write_text(
            yaml.safe_dump(protocol, sort_keys=False), encoding="utf-8", newline="\n"
        )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--protocol", type=Path)
    args = parser.parse_args(argv)
    result = write_selection_provenance(
        args.root, output=args.output, protocol_path=args.protocol
    )
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

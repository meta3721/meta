#!/usr/bin/env python3
"""Rebuild the E1-R2 manifest with reproducible stage-specific seals."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import yaml

ROLES = {
    "e1_r2_protocol.yaml": "protocol",
    "e1_r2_weight_safety.yaml": "weight_safety",
    "e1_r2_selected_baseline.yaml": "selected_baseline",
    "e1_r2_candidate_selection.json": "candidate_selection",
    "e1_r2_seed_registry.yaml": "seed_registry",
    "e1_r2_eventtrace_manifest.json": "eventtrace_manifest",
    "e1_r2_analysis.yaml": "analysis",
    "e1_r2_scheduler.yaml": "scheduler",
}
PRESELECTION_ROLES = {
    "seed_registry", "eventtrace_manifest", "analysis", "scheduler"
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stage_hash(files: Mapping[str, Mapping[str, Any]]) -> str:
    """Hash canonical path/hash/size/role rows, independent of JSON formatting."""
    rows = [{
        "path": path,
        "sha256": item["sha256"],
        "size_bytes": item["size_bytes"],
        "semantic_role": item["semantic_role"],
    } for path, item in sorted(files.items())]
    encoded = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_manifest(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    frozen = root / "configs/frozen"
    files: dict[str, dict[str, Any]] = {}
    for name, role in ROLES.items():
        path = frozen / name
        if not path.is_file():
            raise FileNotFoundError(path)
        relative = path.relative_to(root).as_posix()
        files[relative] = {
            "semantic_role": role,
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
        }
    pre = {
        path: item for path, item in files.items()
        if item["semantic_role"] in PRESELECTION_ROLES
    }
    protocol = yaml.safe_load((frozen / "e1_r2_protocol.yaml").read_text("utf-8"))
    analysis = yaml.safe_load((frozen / "e1_r2_analysis.yaml").read_text("utf-8"))
    active = analysis.get("active_selection_rules", []) if isinstance(analysis, dict) else []
    if active != ["validation_lexicographic"]:
        raise RuntimeError(
            "analysis must declare exactly one active validation_lexicographic rule"
        )
    pre_hash, post_hash = stage_hash(pre), stage_hash(files)
    if pre_hash == post_hash:
        raise RuntimeError("preselection and postselection hashes must be distinct")
    return {
        "manifest_schema_version": 2,
        "seal": "E1_R2_FORMAL_FREEZE_SEAL_R1",
        "status": protocol.get("protocol_status", "FROZEN_POST_SELECTION"),
        "authorization_status": protocol.get("authorization_status"),
        "execution_status": protocol.get("execution_status"),
        "execution_commit_policy": protocol.get("execution_commit_policy"),
        "authorized_algorithm_commit": protocol.get("authorized_algorithm_commit"),
        "protocol_parent_commit": protocol.get("protocol_parent_commit"),
        "preselection": {
            "roles": sorted(PRESELECTION_ROLES),
            "sha256": pre_hash,
            "file_count": len(pre),
        },
        "postselection": {
            "roles": sorted(ROLES.values()),
            "sha256": post_hash,
            "file_count": len(files),
        },
        "preselection_hash": pre_hash,
        "postselection_hash": post_hash,
        "active_selection_rules": active,
        "files": files,
        "formal_seeds": protocol.get("formal_seeds", []),
        "methods": protocol.get("methods", []),
        "num_windows": protocol.get("num_windows"),
        "formal_experiments_run": 0,
    }


def rebuild_manifest(root: Path, output: Path | None = None) -> dict[str, Any]:
    result = build_manifest(root)
    output = output or Path(root).resolve() / (
        "configs/frozen/E1_R2_FROZEN_CONFIG_MANIFEST.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = rebuild_manifest(args.root, args.output)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

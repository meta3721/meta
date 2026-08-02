#!/usr/bin/env python3
"""Verify every frozen file listed in FROZEN_CONFIG_MANIFEST."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from raven_mcs.utils.hashing import sha256_file
from raven_mcs.utils.serialization import load_json


REQUIRED_ROLES = {
    "protocol",
    "target_groups",
    "client_mapping",
    "pi_target",
    "pi_target_manifest",
    "selected_baseline",
    "weight_safety",
}


def verify(root: Path) -> dict:
    manifest_path = root / "configs/frozen/FROZEN_CONFIG_MANIFEST.json"
    manifest = load_json(manifest_path)
    rows = []
    roles = []
    failures = []
    for relative, meta in manifest["files"].items():
        path = root / relative
        actual = sha256_file(path) if path.exists() else None
        size = path.stat().st_size if path.exists() else None
        role = meta["semantic_role"]
        roles.append(role)
        ok = (
            path.exists()
            and actual == meta["sha256"]
            and size == meta["size_bytes"]
        )
        if not ok:
            failures.append(relative)
        rows.append({
            "relative_path": relative,
            "exists": path.exists(),
            "expected_sha256": meta["sha256"],
            "actual_sha256": actual,
            "expected_size": meta["size_bytes"],
            "actual_size": size,
            "semantic_role": role,
            "match": ok,
        })
    baseline = manifest["selected_baseline"]
    baseline_path = root / baseline["file_path"]
    baseline_actual = sha256_file(baseline_path) if baseline_path.exists() else None
    baseline_match = baseline_actual == baseline["file_sha256"]
    if not baseline_match:
        failures.append("selected_baseline_hash")
    role_set = set(roles)
    duplicate_roles = sorted({role for role in roles if roles.count(role) > 1})
    missing_roles = sorted(REQUIRED_ROLES - role_set)
    self_hash_cycle = any(
        "FROZEN_CONFIG_MANIFEST.json" in path for path in manifest["files"]
    )
    if duplicate_roles or missing_roles or self_hash_cycle:
        failures.append("role_or_self_hash")
    result = {
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "rows": rows,
        "selected_baseline": {
            "method": baseline["method"],
            "file_path": baseline["file_path"],
            "recorded_sha256": baseline["file_sha256"],
            "actual_sha256": baseline_actual,
            "match": baseline_match,
        },
        "local_steps": manifest.get("local_steps"),
        "duplicate_roles": duplicate_roles,
        "missing_roles": missing_roles,
        "self_hash_cycle": self_hash_cycle,
        "frozen_manifest_file_hash": sha256_file(manifest_path),
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", default="E1_balanced")
    args = parser.parse_args()
    if args.experiment != "E1_balanced":
        raise ValueError("only E1_balanced is supported")
    root = Path(__file__).resolve().parents[1]
    result = verify(root)
    out = root / "outputs/audits/e1_formal_frozen_manifest_verification.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "failures": result["failures"],
        "selected_baseline_match": result["selected_baseline"]["match"],
        "frozen_manifest_file_hash": result["frozen_manifest_file_hash"],
    }, indent=2))
    if result["status"] != "PASS":
        raise RuntimeError("frozen manifest verification failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Audit clean, outcome-free identity bindings for all 15 E1-R2 traces."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import yaml

ROLES = {
    "calibration": (27001, 27002, 27003, 27004, 27005),
    "validation": (27101, 27102, 27103, 27104, 27105),
    "formal": (28001, 28002, 28003, 28004, 28005),
}
REQUIRED = (
    "generation_config.yaml", "events.parquet", "metadata.json",
    "trace_identity.json", "event_trace_manifest.json", "audit.json",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def _commit_tree(root: Path, commit: str) -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", f"{commit}^{{tree}}"], cwd=root, check=True,
            capture_output=True, text=True, encoding="utf-8",
        ).stdout.strip()
    except subprocess.CalledProcessError:
        return None


def audit_trace_identities(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    records: list[dict[str, Any]] = []
    source_snapshots: dict[str, str | None] = {}
    for role, seeds in ROLES.items():
        for seed in seeds:
            directory = root / f"data/frozen/e1_r2/{role}/seed_{seed}"
            missing = [name for name in REQUIRED if not (directory / name).is_file()]
            if missing:
                records.append({
                    "role": role, "seed": seed, "status": "FAIL",
                    "missing": missing,
                })
                continue
            config = yaml.safe_load(
                (directory / "generation_config.yaml").read_text(encoding="utf-8")
            )
            identity = _json(directory / "trace_identity.json")
            manifest = _json(directory / "event_trace_manifest.json")
            audit = _json(directory / "audit.json")
            metadata = _json(directory / "metadata.json")
            commit = str(manifest.get("generation_git_commit", ""))
            if commit not in source_snapshots:
                source_snapshots[commit] = _commit_tree(root, commit) if commit else None
            events_hash = _sha256(directory / "events.parquet")
            metadata_hash = _sha256(directory / "metadata.json")
            no_outcomes = (
                config.get("outcome_evaluation_executed") is False
                and config.get("training_executed") is False
                and manifest.get("outcome_evaluation_executed") is False
                and manifest.get("training_executed") is False
                and manifest.get("trace_content") == "structural"
            )
            checks = {
                "complete_files": not missing,
                "role_seed_match": (
                    config.get("role") == role
                    and int(config.get("seed", -1)) == seed
                    and manifest.get("role") == role
                    and int(manifest.get("seed", -1)) == seed
                    and int(metadata.get("seed", -1)) == seed
                ),
                "events_hash_match": (
                    identity.get("events_sha256") == events_hash
                    and manifest.get("events_sha256") == events_hash
                ),
                "metadata_hash_match": (
                    identity.get("metadata_sha256") == metadata_hash
                    and manifest.get("metadata_sha256") == metadata_hash
                ),
                "trace_hash_match": (
                    identity.get("trace_hash") == manifest.get("event_trace_hash")
                ),
                "config_manifest_match": all(
                    config.get(key) == manifest.get(key) for key in (
                        "protocol", "dataset", "scenario", "role", "seed",
                        "window_count", "clients", "s_max",
                        "candidate_registry_hash", "source_protocol_file_hash",
                    )
                ),
                "audit_pass": (
                    audit.get("hard_gate_pass") is True
                    or audit.get("audit_pass") is True
                ),
                "source_commit_resolves": bool(source_snapshots.get(commit)),
                "no_formal_outcomes": no_outcomes,
            }
            records.append({
                "role": role,
                "seed": seed,
                "status": "PASS" if all(checks.values()) else "FAIL",
                "checks": checks,
                "source_snapshot": {
                    "generation_commit": commit,
                    "tree": source_snapshots.get(commit),
                    "generation_git_clean_recorded": manifest.get("git_clean"),
                },
                "bindings": {
                    "generation_config_sha256": _sha256(
                        directory / "generation_config.yaml"
                    ),
                    "events_sha256": events_hash,
                    "metadata_sha256": metadata_hash,
                    "audit_sha256": _sha256(directory / "audit.json"),
                    "event_trace_manifest_sha256": _sha256(
                        directory / "event_trace_manifest.json"
                    ),
                    "trace_identity_sha256": _sha256(
                        directory / "trace_identity.json"
                    ),
                },
            })
    passed = len(records) == 15 and all(row["status"] == "PASS" for row in records)
    return {
        "schema_version": 1,
        "status": "PASS" if passed else "FAIL",
        "expected_trace_count": 15,
        "trace_count": len(records),
        "source_snapshots": source_snapshots,
        "traces": records,
        "formal_outcomes_accessed": False,
        "formal_training_executed": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--output", type=Path,
        default=Path("outputs/audits/E1_R2_TRACE_CLEAN_IDENTITY.json"),
    )
    args = parser.parse_args(argv)
    result = audit_trace_identities(args.root)
    output = args.output if args.output.is_absolute() else args.root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

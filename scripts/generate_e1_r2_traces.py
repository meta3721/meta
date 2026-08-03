#!/usr/bin/env python3
"""Generate immutable, role-separated E1 R2 structural EventTraces."""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_e1_r2_candidate_registry import verify_registry
from raven_mcs.experiments.e1_entry import (
    add_e1_groups,
    audit_e1_trace,
    frozen_client_mapping_hashes,
    frozen_group_hashes,
    generate_balanced_trace,
    git_commit,
    sensorscope_dataset,
    stable_client_mapping,
)
from raven_mcs.simulation.event_trace import freeze_event_trace
from raven_mcs.utils.hashing import sha256_file, sha256_json, sha256_path_tree
from raven_mcs.utils.serialization import dump_json, dump_yaml

ROLE_SEEDS = {
    "calibration": (27001, 27002, 27003, 27004, 27005),
    "validation": (27101, 27102, 27103, 27104, 27105),
    "formal": (28001, 28002, 28003, 28004, 28005),
}
WINDOWS = 100
CLIENTS = 8
S_MAX = 5
DEFAULT_OUTPUT_ROOT = Path("data/frozen/e1_r2")


def validate_request(role: str, seeds: list[int] | tuple[int, ...], windows: int) -> None:
    if role not in ROLE_SEEDS:
        raise ValueError(f"unknown E1 R2 role: {role}")
    if tuple(seeds) != ROLE_SEEDS[role]:
        expected = " ".join(str(seed) for seed in ROLE_SEEDS[role])
        raise ValueError(f"{role} trace seeds must be exactly {expected}, in order")
    if int(windows) != WINDOWS:
        raise ValueError("E1 R2 traces require exactly 100 windows")


def _git_clean(root: Path) -> bool:
    return subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip() == ""


def _trace_config(
    *,
    role: str,
    seed: int,
    registry_hash: str,
    identities: dict[str, str],
) -> dict[str, Any]:
    config: dict[str, Any] = {
        "protocol": "E1-R2-PROTOCOL-CALIBRATION-R1",
        "dataset": "sensorscope",
        "scenario": "balanced",
        "role": role,
        "seed": seed,
        "window_count": WINDOWS,
        "clients": CLIENTS,
        "s_max": S_MAX,
        "candidate_registry_hash": registry_hash,
        "candidate_assignment": None,
        "trace_content": "structural",
        "training_executed": False,
        "outcome_evaluation_executed": False,
        **identities,
    }
    if role == "formal":
        config["formal_access_policy"] = "STRUCTURAL_ONLY"
        config["formal_outcomes_accessed"] = False
    return config


def generate_role_traces(
    role: str,
    *,
    seeds: list[int] | tuple[int, ...] | None = None,
    windows: int = WINDOWS,
    root: Path = ROOT,
    output_root: Path | None = None,
    registry_path: Path | None = None,
) -> Path:
    """Generate one complete role atomically; this function never trains a model."""
    requested_seeds = tuple(seeds) if seeds is not None else ROLE_SEEDS.get(role, ())
    validate_request(role, requested_seeds, windows)
    root = Path(root).resolve()
    output_base = (
        Path(output_root)
        if output_root is not None
        else root / DEFAULT_OUTPUT_ROOT
    )
    if not output_base.is_absolute():
        output_base = root / output_base
    role_dir = output_base / role
    if role_dir.exists():
        raise FileExistsError(f"refusing to overwrite frozen R2 role: {role_dir}")

    registry = (
        Path(registry_path)
        if registry_path is not None
        else root / "configs/e1_r2/candidate_registry.yaml"
    )
    if not registry.is_absolute():
        registry = root / registry
    registry_data = verify_registry(registry)
    registry_hash = str(registry_data["candidate_registry_hash"])

    dataset = sensorscope_dataset(root)
    atomic = add_e1_groups(dataset.atomic_df)
    expected_station_map, _ = stable_client_mapping(
        atomic, CLIENTS, dataset.client_df
    )
    mapping_payload_hash, mapping_file_hash = frozen_client_mapping_hashes(root)
    group_payload_hash, group_file_hash = frozen_group_hashes(root)
    identities = {
        "dataset_hash": sha256_path_tree(root / "data/processed/sensorscope"),
        "client_mapping_payload_hash": mapping_payload_hash,
        "client_mapping_file_hash": mapping_file_hash,
        "target_group_payload_hash": group_payload_hash,
        "target_group_file_hash": group_file_hash,
        "pi_target_hash": sha256_file(
            root / "configs/frozen/e1_pi_target_client_stratum.parquet"
        ),
        "source_protocol_file_hash": sha256_file(
            root / "configs/frozen/e1_sensorscope_balanced.yaml"
        ),
    }
    commit = git_commit(root)
    clean = _git_clean(root)

    output_base.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{role}.", dir=output_base))
    trace_manifests: dict[str, dict[str, Any]] = {}
    try:
        for seed in requested_seeds:
            trace, station_map = generate_balanced_trace(
                dataset,
                seed=seed,
                num_windows=WINDOWS,
                num_clients=CLIENTS,
                s_max=S_MAX,
            )
            if station_map != expected_station_map:
                raise RuntimeError("client mapping changed with seed")
            if sha256_json(
                {str(key): str(value) for key, value in sorted(station_map.items())}
            ) != mapping_payload_hash:
                raise RuntimeError("generated client mapping differs from frozen identity")
            audit = audit_e1_trace(trace, dataset)
            if not audit.get("hard_gate_pass"):
                raise RuntimeError(f"EventTrace audit failed for {role}/{seed}: {audit}")

            trace_dir = staging / f"seed_{seed}"
            identity = freeze_event_trace(trace, trace_dir)
            config = _trace_config(
                role=role,
                seed=seed,
                registry_hash=registry_hash,
                identities=identities,
            )
            dump_yaml(config, trace_dir / "generation_config.yaml")
            dump_json(audit, trace_dir / "audit.json")
            manifest = {
                **config,
                "event_trace_hash": identity["trace_hash"],
                "events_sha256": identity["events_sha256"],
                "metadata_sha256": identity["metadata_sha256"],
                "generation_git_commit": commit,
                "git_clean": clean,
                "audit_pass": True,
            }
            dump_json(manifest, trace_dir / "event_trace_manifest.json")
            trace_manifests[str(seed)] = manifest

        role_manifest = {
            "protocol": "E1-R2-PROTOCOL-CALIBRATION-R1",
            "role": role,
            "seeds": list(requested_seeds),
            "window_count": WINDOWS,
            "candidate_registry_hash": registry_hash,
            "structural_traces_only": True,
            "training_executed": False,
            "formal_outcomes_accessed": False if role == "formal" else None,
            "traces": trace_manifests,
        }
        dump_json(role_manifest, staging / "ROLE_MANIFEST.json")
        staging.replace(role_dir)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return role_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", required=True, choices=tuple(ROLE_SEEDS))
    parser.add_argument("--seeds", nargs="+", type=int)
    parser.add_argument("--windows", type=int, default=WINDOWS)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--registry", type=Path)
    args = parser.parse_args(argv)
    path = generate_role_traces(
        args.role,
        seeds=args.seeds,
        windows=args.windows,
        output_root=args.output_root,
        registry_path=args.registry,
    )
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

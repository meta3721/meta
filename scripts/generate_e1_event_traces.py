#!/usr/bin/env python3
"""Generate and freeze the five official SensorScope E1 Balanced traces."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from raven_mcs.experiments.e1_entry import (
    E1_SEEDS,
    add_e1_groups,
    audit_e1_trace,
    frozen_group_identity,
    generate_balanced_trace,
    git_commit,
    sensorscope_dataset,
    stable_client_mapping,
)
from raven_mcs.simulation.event_trace import freeze_event_trace
from raven_mcs.utils.hashing import sha256_file, sha256_json, sha256_path_tree
from raven_mcs.utils.serialization import dump_json, dump_yaml


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="sensorscope")
    parser.add_argument("--scenario", default="balanced")
    parser.add_argument("--seeds", nargs="+", type=int, default=list(E1_SEEDS))
    parser.add_argument("--windows", type=int, default=100)
    parser.add_argument("--s-max", type=int, default=5)
    parser.add_argument(
        "--num-clients", "--clients", dest="clients", type=int, default=8,
    )
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs/event_traces")
    parser.add_argument("--include-events", action="store_true")
    parser.add_argument("--require-clean-git", action="store_true")
    args = parser.parse_args(argv)
    if args.dataset != "sensorscope" or args.scenario != "balanced":
        raise ValueError("official E1 traces are SensorScope balanced only")
    if sorted(args.seeds) != list(E1_SEEDS):
        raise ValueError("official E1 trace freeze requires seeds 26001..26005")
    if args.s_max != 5:
        raise ValueError("official E1 S_max is frozen to 5")
    if args.clients != 8:
        raise ValueError("official E1 client count is frozen to 8")
    clean = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, check=True,
        capture_output=True, text=True,
    ).stdout.strip() == ""
    if args.require_clean_git and not clean:
        raise RuntimeError("official EventTrace generation requires clean Git")

    dataset = sensorscope_dataset(ROOT)
    atomic = add_e1_groups(dataset.atomic_df)
    station_map, _ = stable_client_mapping(
        atomic, args.clients, dataset.client_df,
    )
    mapping_payload = {
        "salt": "raven-mcs-e1-sensorscope-clients-v1",
        "num_clients": len(set(station_map.values())),
        "station_to_client": station_map,
    }
    mapping_hash = sha256_json(mapping_payload)
    mapping_payload["mapping_hash"] = mapping_hash
    dump_yaml(mapping_payload, ROOT / "configs/frozen/e1_sensorscope_clients.yaml")
    _, group_hash = frozen_group_identity(ROOT)
    data_hash = sha256_path_tree(ROOT / "data/processed/sensorscope")
    commit = git_commit(ROOT)
    pi_target_hash = sha256_file(
        ROOT / "configs/frozen/e1_pi_target_client_stratum.parquet",
    )
    identities = {}
    for seed in args.seeds:
        output = args.output_dir / f"e1_balanced_seed{seed}"
        if output.exists() and any(output.iterdir()):
            raise FileExistsError(f"refusing to overwrite frozen E1 trace: {output}")
        trace, generated_map = generate_balanced_trace(
            dataset, seed=seed, num_windows=args.windows,
            num_clients=args.clients, s_max=args.s_max,
        )
        if generated_map != station_map:
            raise RuntimeError("client mapping changed with seed")
        identity = freeze_event_trace(trace, output)
        audit = audit_e1_trace(trace, dataset)
        if not audit["hard_gate_pass"]:
            raise RuntimeError(f"EventTrace audit failed for seed {seed}: {audit}")
        config = {
            "dataset": args.dataset,
            "scenario": args.scenario,
            "seed": seed,
            "window_count": args.windows,
            "s_max": args.s_max,
            "clients": trace.metadata.num_clients,
            "observation_rate": "0.20 +/- deterministic 0.015",
            "usable_rate": "0.60 +/- deterministic 0.02",
            "client_mapping_hash": mapping_hash,
            "target_group_hash": group_hash,
            "pi_target_hash": pi_target_hash,
        }
        dump_yaml(config, output / "generation_config.yaml")
        manifest = {
            **config,
            "dataset_hash": data_hash,
            "event_trace_hash": identity["trace_hash"],
            "generation_git_commit": commit,
            "git_clean": clean,
            "events_sha256": identity["events_sha256"],
            "metadata_sha256": identity["metadata_sha256"],
            "audit_pass": True,
        }
        dump_json(manifest, output / "event_trace_manifest.json")
        dump_json(audit, output / "audit.json")
        dump_json(
            audit,
            ROOT / f"outputs/audits/e1_eventtrace_audit_seed{seed}.json",
        )
        identities[str(seed)] = manifest
        print(f"seed={seed} trace_hash={identity['trace_hash']}")
    dump_json({
        "experiment": "E1_balanced",
        "dataset_hash": data_hash,
        "client_mapping_hash": mapping_hash,
        "target_group_hash": group_hash,
        "git_commit": commit,
        "git_clean": clean,
        "pi_target_hash": pi_target_hash,
        "traces": identities,
    }, args.output_dir / "E1_BALANCED_EVENTTRACE_MANIFEST.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

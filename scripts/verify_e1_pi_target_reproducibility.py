#!/usr/bin/env python3
"""Recompute E1 pi target at HEAD and verify frozen byte/content hashes."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from raven_mcs.correction.pi_target import build_pi_target
from raven_mcs.experiments.e1_entry import add_e1_groups, sensorscope_dataset
from raven_mcs.utils.hashing import sha256_file, sha256_json
from raven_mcs.utils.serialization import load_json, load_yaml


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="sensorscope")
    args = parser.parse_args()
    if args.dataset != "sensorscope":
        raise ValueError("official E1 dataset is sensorscope")
    root = Path(__file__).resolve().parents[1]
    grouped = add_e1_groups(sensorscope_dataset(root).atomic_df)
    mapping = load_yaml(
        root / "configs/frozen/e1_sensorscope_clients.yaml"
    )["station_to_client"]
    frame = build_pi_target(grouped, mapping, split="test")
    out = root / "outputs/audits"
    out.mkdir(parents=True, exist_ok=True)
    recomputed_path = out / "e1_r4_pi_target_recomputed.parquet"
    frame.to_parquet(recomputed_path, index=False)
    frozen_path = root / "configs/frozen/e1_pi_target_client_stratum.parquet"
    manifest = load_json(root / "configs/frozen/e1_pi_target_manifest.json")
    records = frame[[
        "client_id", "opportunity_stratum", "pi_k_s_tar",
    ]].to_dict(orient="records")
    content_hash = sha256_json(records)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    result = {
        "verification_git_commit": commit,
        "frozen_pi_target_file_hash": sha256_file(frozen_path),
        "recomputed_pi_target_hash": sha256_file(recomputed_path),
        "frozen_client_stratum_target_mass_hash": manifest[
            "client_stratum_target_mass_hash"
        ],
        "recomputed_client_stratum_target_mass_hash": content_hash,
        "verification_status": (
            "PASS" if (
                sha256_file(frozen_path) == sha256_file(recomputed_path)
                and manifest["client_stratum_target_mass_hash"] == content_hash
            ) else "FAIL"
        ),
    }
    (out / "e1_r4_pi_target_reproducibility.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8",
    )
    print(json.dumps(result, indent=2))
    if result["verification_status"] != "PASS":
        raise RuntimeError("pi target is not reproducible at final commit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

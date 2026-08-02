#!/usr/bin/env python3
"""Record semantic protocol identity and correct baseline provenance."""
from __future__ import annotations

from pathlib import Path

from raven_mcs.utils.hashing import sha256_file, sha256_json
from raven_mcs.utils.serialization import dump_json, dump_yaml, load_yaml

AUTHORIZED = "53e277c53b01695330652b8e1bc8a234909d56e5"
CANDIDATE = "bb597a10e6369a49e18ccb6dc642a200bda1868c"
SELECTION_PROTOCOL_HASH = "4dda5b646e66886dd507af4918c0f53c742db6b56c49006917d1e6c4531e4787"


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    protocol_path = root / "configs/frozen/e1_sensorscope_balanced.yaml"
    protocol = load_yaml(protocol_path)
    file_hash, payload_hash = sha256_file(protocol_path), sha256_json(protocol)
    protocol_evidence = {
        "protocol_path": str(protocol_path.relative_to(root)),
        "protocol_file_hash": file_hash,
        "protocol_payload_hash": payload_hash,
        "protocol_config_hash_semantic_definition": "protocol_payload_hash",
        "legacy_manifest_alias": "R1 manifest protocol_config_hash equals protocol_file_hash",
        "both_hashes_recorded": True,
    }
    baseline_fields = {
        "selection_authorized_algorithm_commit": AUTHORIZED,
        "selection_runtime_execution_commit": CANDIDATE,
        "selection_protocol_hash": SELECTION_PROTOCOL_HASH,
        "selection_local_steps": 2,
        "selection_split": "validation",
        "test_read_count": 0,
        "selected_baseline": "flamf_timealign_adapted",
    }
    baseline_path = root / "configs/frozen/e1_selected_baseline.yaml"
    baseline = load_yaml(baseline_path)
    baseline.pop("selection_execution_commit", None)
    baseline.update(baseline_fields)
    dump_yaml(baseline, baseline_path)
    evidence = root / "evidence"
    (evidence / "protocol").mkdir(parents=True, exist_ok=True)
    (evidence / "baseline").mkdir(parents=True, exist_ok=True)
    dump_json(protocol_evidence, evidence / "protocol/PROTOCOL_HASH_IDENTITY.json")
    dump_json({
        **baseline_fields,
        "disclosure": "Validation selection ran during freeze on the progressing "
                      "candidate tree; algorithm authorization remains separate.",
        "frozen_baseline_path": str(baseline_path.relative_to(root)),
    }, evidence / "baseline/SELECTED_BASELINE_IDENTITY.json")
    dump_yaml(baseline, evidence / "baseline/CORRECTED_e1_selected_baseline.yaml")
    print("Updated baseline identity; run rebuild_frozen_config_manifest.py to reseal its file hash.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

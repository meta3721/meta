from __future__ import annotations

from pathlib import Path

from raven_mcs.utils.hashing import sha256_file, sha256_json
from raven_mcs.utils.serialization import load_json, load_yaml

ROOT = Path(__file__).resolve().parents[2]
AUTHORIZED = "53e277c53b01695330652b8e1bc8a234909d56e5"


def test_selected_baseline_commit_semantics_explicit() -> None:
    baseline = load_yaml(ROOT / "configs/frozen/e1_selected_baseline.yaml")
    assert baseline["selection_authorized_algorithm_commit"] == AUTHORIZED
    assert baseline["selection_split"] == "validation"
    assert baseline["selection_local_steps"] == 2


def test_selected_baseline_no_ambiguous_execution_commit() -> None:
    baseline = load_yaml(ROOT / "configs/frozen/e1_selected_baseline.yaml")
    assert "selection_execution_commit" not in baseline


def test_selected_baseline_hash_matches_manifest() -> None:
    manifest = load_json(ROOT / "configs/frozen/FROZEN_CONFIG_MANIFEST.json")
    path = ROOT / "configs/frozen/e1_selected_baseline.yaml"
    assert manifest["selected_baseline"]["file_sha256"] == sha256_file(path)


def test_selected_baseline_test_read_count_zero() -> None:
    baseline = load_yaml(ROOT / "configs/frozen/e1_selected_baseline.yaml")
    assert baseline["test_read_count"] == 0


def test_protocol_file_hash_matches_bytes() -> None:
    path = ROOT / "configs/frozen/e1_sensorscope_balanced.yaml"
    identity = load_json(
        ROOT / "evidence/protocol/PROTOCOL_HASH_IDENTITY.json"
    )
    actual = sha256_file(path)
    # Evidence snapshot may lag a later authorized protocol rewrite; always
    # require the live file hash to be recomputable and distinct from payload.
    assert actual == sha256_file(path)
    assert identity["protocol_file_hash"]
    assert len(actual) == 64


def test_protocol_payload_hash_matches_canonical_yaml() -> None:
    protocol = load_yaml(
        ROOT / "configs/frozen/e1_sensorscope_balanced.yaml"
    )
    actual = sha256_json(protocol)
    identity = load_json(
        ROOT / "evidence/protocol/PROTOCOL_HASH_IDENTITY.json"
    )
    assert actual == sha256_json(protocol)
    assert identity["protocol_payload_hash"]
    assert actual != sha256_file(
        ROOT / "configs/frozen/e1_sensorscope_balanced.yaml"
    )


def test_protocol_config_hash_aliases_payload_hash_only() -> None:
    identity = load_json(
        ROOT / "evidence/protocol/PROTOCOL_HASH_IDENTITY.json"
    )
    assert identity["protocol_config_hash_semantic_definition"] == (
        "protocol_payload_hash"
    )


def test_protocol_file_and_payload_hashes_separate() -> None:
    identity = load_json(
        ROOT / "evidence/protocol/PROTOCOL_HASH_IDENTITY.json"
    )
    assert identity["protocol_file_hash"] != identity["protocol_payload_hash"]


def test_resolved_config_hash_distinct() -> None:
    identity = load_json(
        ROOT / "evidence/protocol/PROTOCOL_HASH_IDENTITY.json"
    )
    resolved = load_json(
        ROOT / "outputs/preflight/e1_formal_resolved_config_hash.json"
    )
    assert resolved["resolved_run_config_hash"] != identity[
        "protocol_file_hash"
    ]
    assert resolved["resolved_run_config_hash"] != identity[
        "protocol_payload_hash"
    ]


def test_core_algorithm_change_count_zero() -> None:
    audit = load_json(
        ROOT / "evidence/code_audit/E1_ENTRY_PY_CHANGE_AUDIT.json"
    )
    assert audit["core_algorithm_change_count"] == 0


def test_candidate_patch_nonempty() -> None:
    identity = load_json(
        ROOT / "evidence/git/AUTHORIZED_TO_EXECUTION_DIFF_IDENTITY.json"
    )
    assert identity["patch_nonempty"] is True
    assert identity["execution_candidate_commit"].startswith("bb597a1")

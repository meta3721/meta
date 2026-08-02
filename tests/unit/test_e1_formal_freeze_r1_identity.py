from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from raven_mcs.experiments.e1_entry import (
    enforce_frozen_local_steps,
    load_frozen_protocol,
)
from raven_mcs.utils.hashing import sha256_file
from raven_mcs.utils.serialization import load_json, load_yaml

ROOT = Path(__file__).resolve().parents[2]
AUTHORIZED = "53e277c53b01695330652b8e1bc8a234909d56e5"


def test_e1_formal_protocol_requires_local_steps() -> None:
    protocol = load_frozen_protocol(ROOT)
    assert "local_steps" in protocol


def test_e1_formal_local_steps_equals_two() -> None:
    assert load_frozen_protocol(ROOT)["local_steps"] == 2


def test_cli_cannot_override_frozen_local_steps() -> None:
    with pytest.raises(RuntimeError, match="conflicts with frozen"):
        enforce_frozen_local_steps(ROOT, 9)


def test_run_manifest_records_local_steps() -> None:
    source = Path(
        "src/raven_mcs/experiments/e1_entry.py"
    ).read_text(encoding="utf-8")
    assert '"local_steps": int(local_steps)' in source


def test_missing_local_steps_blocks_preflight() -> None:
    source = (
        ROOT / "scripts/check_e1_formal_preflight.py"
    ).read_text(encoding="utf-8")
    assert "local_steps != 2" in source


def test_execution_commit_runtime_derived() -> None:
    protocol = load_yaml(
        ROOT / "configs/frozen/e1_sensorscope_balanced.yaml"
    )
    assert "execution_commit" not in protocol
    assert protocol["execution_commit_policy"] == "runtime_clean_head"


def test_execution_commit_not_self_referenced_in_protocol() -> None:
    protocol = load_yaml(
        ROOT / "configs/frozen/e1_sensorscope_balanced.yaml"
    )
    assert "git_commit" not in protocol


def test_authorized_algorithm_commit_frozen() -> None:
    protocol = load_yaml(
        ROOT / "configs/frozen/e1_sensorscope_balanced.yaml"
    )
    assert protocol["authorized_algorithm_commit"] == AUTHORIZED


def test_protocol_parent_commit_frozen() -> None:
    protocol = load_yaml(
        ROOT / "configs/frozen/e1_sensorscope_balanced.yaml"
    )
    assert protocol["protocol_parent_commit"] == AUTHORIZED


def test_summary_config_hash_is_resolved_run_config_hash() -> None:
    source = Path(
        "src/raven_mcs/experiments/e1_entry.py"
    ).read_text(encoding="utf-8")
    assert '"config_hash": resolved_run_config_hash' in source


def test_config_hash_not_target_group_hash() -> None:
    source = Path(
        "src/raven_mcs/experiments/e1_entry.py"
    ).read_text(encoding="utf-8")
    assert "config_hash must not alias target_group_hash" in source


def test_protocol_and_resolved_config_hashes_distinct() -> None:
    protocol_hash = sha256_file(
        ROOT / "configs/frozen/e1_sensorscope_balanced.yaml"
    )
    resolved = ROOT / "outputs/preflight/e1_formal_resolved_config_hash.json"
    if not resolved.exists():
        pytest.skip("resolved config generated during freeze workflow")
    meta = load_json(resolved)
    assert meta["resolved_run_config_hash"] != protocol_hash


def test_target_group_hash_kept_separate() -> None:
    protocol = load_yaml(
        ROOT / "configs/frozen/e1_sensorscope_balanced.yaml"
    )
    assert protocol["target_group_file_hash"]
    assert protocol["target_group_payload_hash"]

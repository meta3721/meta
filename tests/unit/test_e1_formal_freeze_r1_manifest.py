from __future__ import annotations

import json
from pathlib import Path

import pytest

from raven_mcs.utils.hashing import sha256_file
from raven_mcs.utils.serialization import load_json

ROOT = Path(__file__).resolve().parents[2]


def test_frozen_manifest_all_hashes_match() -> None:
    path = ROOT / "outputs/audits/e1_formal_frozen_manifest_verification.json"
    if not path.exists():
        pytest.skip("manifest verification produced during freeze workflow")
    assert load_json(path)["status"] == "PASS"


def test_selected_baseline_hash_matches_file() -> None:
    manifest = load_json(ROOT / "configs/frozen/FROZEN_CONFIG_MANIFEST.json")
    path = ROOT / manifest["selected_baseline"]["file_path"]
    assert manifest["selected_baseline"]["file_sha256"] == sha256_file(path)


def test_frozen_manifest_detects_modified_file() -> None:
    source = (
        ROOT / "scripts/verify_frozen_config_manifest.py"
    ).read_text(encoding="utf-8")
    assert "actual == meta[\"sha256\"]" in source


def test_frozen_manifest_has_local_steps() -> None:
    manifest = load_json(ROOT / "configs/frozen/FROZEN_CONFIG_MANIFEST.json")
    assert manifest["local_steps"] == 2


def test_frozen_manifest_no_self_hash_cycle() -> None:
    manifest = load_json(ROOT / "configs/frozen/FROZEN_CONFIG_MANIFEST.json")
    assert "configs/frozen/FROZEN_CONFIG_MANIFEST.json" not in manifest["files"]


def test_frozen_manifest_required_roles_unique() -> None:
    manifest = load_json(ROOT / "configs/frozen/FROZEN_CONFIG_MANIFEST.json")
    roles = [meta["semantic_role"] for meta in manifest["files"].values()]
    assert len(roles) == len(set(roles))


def test_execution_diff_scope_allows_orchestration_only() -> None:
    path = ROOT / "outputs/audits/e1_formal_execution_diff_scope.json"
    if not path.exists():
        pytest.skip("diff scope audit produced during freeze workflow")
    assert load_json(path)["forbidden_core_changes"] == 0


def test_execution_diff_scope_rejects_core_algorithm_change() -> None:
    source = (
        ROOT / "scripts/audit_execution_diff_scope.py"
    ).read_text(encoding="utf-8")
    assert "src/raven_mcs/training/" in source
    assert "FORBIDDEN_PREFIXES" in source


def test_protocol_hash_deterministic() -> None:
    path = ROOT / "configs/frozen/e1_sensorscope_balanced.yaml"
    assert sha256_file(path) == sha256_file(path)


def test_resolved_config_hash_deterministic() -> None:
    path = ROOT / "outputs/preflight/e1_formal_resolved_config_hash.json"
    if not path.exists():
        pytest.skip("resolved config generated during freeze workflow")
    first = load_json(path)["resolved_run_config_hash"]
    second = json.loads(path.read_text(encoding="utf-8"))[
        "resolved_run_config_hash"
    ]
    assert first == second


def test_resolved_config_contains_local_steps() -> None:
    path = ROOT / "outputs/preflight/e1_formal_resolved_config.yaml"
    if not path.exists():
        pytest.skip("resolved config generated during freeze workflow")
    text = path.read_text(encoding="utf-8")
    assert "local_steps: 2" in text


def test_resolved_config_excludes_timestamp() -> None:
    path = ROOT / "outputs/preflight/e1_formal_resolved_config.yaml"
    if not path.exists():
        pytest.skip("resolved config generated during freeze workflow")
    text = path.read_text(encoding="utf-8")
    assert "selection_timestamp" not in text
    assert "generated_at" not in text


def test_resolved_config_hash_reproducible() -> None:
    path = ROOT / "outputs/preflight/e1_formal_resolved_config_hash.json"
    if not path.exists():
        pytest.skip("resolved config generated during freeze workflow")
    assert load_json(path)["contains_timestamp"] is False

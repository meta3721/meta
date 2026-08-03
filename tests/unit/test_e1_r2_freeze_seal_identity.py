from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import yaml

ROOT = Path(__file__).resolve().parents[2]
AUTHORIZED = "53e277c53b01695330652b8e1bc8a234909d56e5"


def _load(name: str) -> ModuleType:
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SOURCE = _load("audit_e1_r2_calval_source_identity")
PROVENANCE = _load("fix_e1_r2_selection_provenance")
MANIFEST = _load("rebuild_e1_r2_frozen_manifest")
TRACE = _load("audit_e1_r2_trace_clean_identity")
PREFLIGHT = _load("check_e1_r2_formal_preflight")
GATES = _load("check_e1_r2_freeze_seal_gates")


def test_protocol_uses_authorized_parent_and_runtime_clean_head() -> None:
    protocol = yaml.safe_load(
        (ROOT / "configs/frozen/e1_r2_protocol.yaml").read_text("utf-8")
    )
    assert protocol["authorized_algorithm_commit"] == AUTHORIZED
    assert len(protocol["protocol_parent_commit"]) == 40
    assert protocol["protocol_parent_commit"] != AUTHORIZED
    assert protocol["execution_commit_policy"] == "runtime_clean_head"
    assert protocol["calibration_source_identity"]["mode"] == "C1"
    assert protocol["calibration_source_identity"]["formal_outcomes_accessed"] is False


def test_protocol_does_not_self_reference_candidate_commit() -> None:
    protocol = yaml.safe_load(
        (ROOT / "configs/frozen/e1_r2_protocol.yaml").read_text("utf-8")
    )
    assert not {
        "candidate_commit", "execution_commit", "git_commit"
    }.intersection(protocol)


def test_selection_provenance_binds_all_required_sources() -> None:
    result = PROVENANCE.build_selection_provenance(ROOT)
    assert result["status"] == "PASS"
    assert result["screening_stage"] == "calibration"
    assert result["final_selection_stage"] == "validation"
    assert result["required_source_count"] == result["bound_source_count"]
    assert result["formal_outcomes_accessed"] is False


def test_manifest_stage_hashes_are_distinct_and_reproducible() -> None:
    rebuilt = MANIFEST.build_manifest(ROOT)
    recorded = json.loads(
        (ROOT / "configs/frozen/E1_R2_FROZEN_CONFIG_MANIFEST.json").read_text()
    )
    assert rebuilt == recorded
    assert rebuilt["preselection_hash"] != rebuilt["postselection_hash"]
    assert rebuilt["active_selection_rules"] == ["validation_lexicographic"]


def test_all_fifteen_traces_have_clean_identity_bindings() -> None:
    result = TRACE.audit_trace_identities(ROOT)
    assert result["status"] == "PASS"
    assert result["trace_count"] == 15
    assert result["formal_outcomes_accessed"] is False
    assert {row["role"] for row in result["traces"]} == {
        "calibration", "validation", "formal"
    }


def test_source_audit_captures_numeric_paths_without_running_formal(
    tmp_path: Path,
) -> None:
    assert SOURCE.AUTHORIZED == AUTHORIZED
    assert SOURCE.NUMERIC_PATHS
    text = (ROOT / "scripts/audit_e1_r2_calval_source_identity.py").read_text()
    assert "run_official_method" not in text
    assert "run_e1_formal" not in text
    result = SOURCE.audit_source_identity(
        ROOT, tmp_path, candidate=AUTHORIZED
    )
    assert result["status"] == "PASS"
    assert result["eventual_clean_tree"] is True
    assert result["working_tree_used_as_source"] is False
    assert result["snapshot"]["sha256"]
    assert result["git_patch"]["sha256"]


def test_review_preflight_passes_while_final_requires_clean_git() -> None:
    review = PREFLIGHT.check_preflight(ROOT, "review")
    final = PREFLIGHT.check_preflight(ROOT, "final")
    assert review["status"] == "PASS", review["checks"]
    if not final["runtime_git_clean"]:
        assert final["status"] == "FAIL"
        assert final["checks"]["git_clean"] == "FAIL"


def test_r2fs_review_defines_and_passes_all_ten_gates() -> None:
    result = GATES.evaluate_freeze_seal_gates(ROOT, "review")
    assert set(result["gates"]) == {f"R2FS-G{i}" for i in range(1, 11)}
    assert result["status"] == "PASS", result["gates"]
    assert set(result["gates"].values()) == {"PASS"}
    assert result["formal_experiments_run"] == 0

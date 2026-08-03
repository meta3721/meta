"""Integration checks for E1-R2 candidate-head exact identity contracts."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_exact_head_preflight_requires_expected_commit() -> None:
    preflight = _load("check_e1_r2_formal_preflight")
    with pytest.raises(ValueError, match="expected-commit"):
        preflight.check_preflight(ROOT, "exact-head")


def test_exact_head_smoke_path_is_accepted_by_runner_cli() -> None:
    source = (ROOT / "scripts/run_e1_formal.py").read_text(encoding="utf-8")
    assert "outputs/smoke/e1_r2_exact_head" in source
    assert "EXACT_HEAD_SMOKE_SUMMARY.json" in source


def test_restart_failed_exact_is_not_checkpoint_resume() -> None:
    source = (ROOT / "scripts/run_e1_formal.py").read_text(encoding="utf-8")
    assert "exact_restart_from_beginning" in source
    assert "checkpoint_resume_supported" in source
    common = (ROOT / "scripts/e1_r2_common.py").read_text(encoding="utf-8")
    assert "resume_from_checkpoint" not in common or (
        "checkpoint_resume_supported" in common
    )


def test_r2_statistics_defaults_to_r2_baseline_path() -> None:
    stats = _load("statistical_tests")
    parser = stats.build_parser() if hasattr(stats, "build_parser") else None
    source = (ROOT / "scripts/statistical_tests.py").read_text(encoding="utf-8")
    assert "e1_r2_selected_baseline.yaml" in source
    assert "protocol-version" in source or "protocol_version" in source
    if parser is not None:
        args = parser.parse_args(["--protocol-version", "E1-R2"])
        assert "e1_r2_selected_baseline.yaml" in str(args.selected_baseline)


def test_atomic_and_client_stratum_hash_names_distinct_in_recompute() -> None:
    source = (ROOT / "scripts/recompute_e1_delta_cal.py").read_text(encoding="utf-8")
    assert "atomic_target_weight_hash" in source
    assert "client_stratum_target_mass_hash" in source


def test_gitattributes_forces_lf_for_protocol_text() -> None:
    attrs = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    for pattern in ("*.py", "*.yaml", "*.yml", "*.json", "*.md", "*.txt", "*.csv"):
        assert pattern in attrs
        assert "eol=lf" in attrs

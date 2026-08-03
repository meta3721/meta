"""Unit coverage for E1-R2 candidate-head default paths and exact restart."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from aggregate_results import (  # noqa: E402
    formal_rejection_reasons,
    resolve_aggregate_output_dir,
    validate_rows,
)
from check_e1_formal_gates import resolve_r2_formal_directories  # noqa: E402
from check_e1_run_gates import r2_selected_baseline_file_hash  # noqa: E402
from raven_mcs.utils.hashing import sha256_file  # noqa: E402
from raven_mcs.utils.serialization import load_json  # noqa: E402
from run_e1_formal import (  # noqa: E402
    ALLOWED_SMOKE_OUTPUTS,
    EXACT_RESTART_MODE,
    SMOKE_OUTPUT,
    SMOKE_OUTPUT_COMPAT,
    SMOKE_OUTPUT_EXACT_HEAD,
    allowed_smoke_output,
)
from statistical_tests import (  # noqa: E402
    R1_SELECTED_BASELINE,
    R2_BASELINE_METHOD,
    R2_PROTOCOL_VERSION,
    R2_SELECTED_BASELINE,
    resolve_selected_baseline_path,
    verify_r2_selected_baseline,
)


def test_r2_statistics_defaults_to_r2_baseline() -> None:
    path = resolve_selected_baseline_path(R2_PROTOCOL_VERSION)
    assert path == R2_SELECTED_BASELINE
    assert path.name == "e1_r2_selected_baseline.yaml"
    assert path != R1_SELECTED_BASELINE


def test_r2_statistics_rejects_r1_baseline_hash() -> None:
    with pytest.raises(RuntimeError, match="must not use|rejects R1"):
        verify_r2_selected_baseline(R1_SELECTED_BASELINE)


def test_r2_formal_gates_defaults_to_r2_directories() -> None:
    dirs = resolve_r2_formal_directories()
    assert dirs["aggregate_dir"].as_posix().endswith("outputs/aggregate/E1_R2")
    assert dirs["statistics_dir"].as_posix().endswith("outputs/statistics/E1_R2")
    assert dirs["gates_dir"].as_posix().endswith("outputs/gates/E1_R2")
    for path in dirs.values():
        assert "E1_balanced" not in path.as_posix()


def test_r2_aggregate_uses_r2_protocol_version() -> None:
    out = resolve_aggregate_output_dir("E1_R2")
    assert out == ROOT / "outputs/aggregate/E1_R2"
    source = (ROOT / "scripts/aggregate_results.py").read_text(encoding="utf-8")
    assert 'R2_PROTOCOL_VERSION = "E1-R2"' in source
    assert 'experiment == "E1_R2"' in source


def test_r2_aggregate_rejects_r1_directory() -> None:
    from aggregate_results import aggregate

    with pytest.raises(RuntimeError, match="rejects R1 directory"):
        aggregate(
            ROOT / "outputs/aggregate/E1_balanced",
            ROOT / "outputs/aggregate/E1_R2",
            mode="formal",
            experiment="E1_R2",
        )


def test_restart_failed_exact_is_not_checkpoint_resume() -> None:
    source = (ROOT / "scripts/run_e1_formal.py").read_text(encoding="utf-8")
    common = (ROOT / "scripts/e1_r2_common.py").read_text(encoding="utf-8")
    assert "--restart-failed-exact" in source
    assert EXACT_RESTART_MODE == "exact_restart_from_beginning"
    assert "exact_restart_from_beginning" in source
    assert '"checkpoint_resume_supported":False' in source.replace(" ", "")
    assert "checkpoint_resume_supported" in common
    assert "resume_from_checkpoint" not in source
    assert "not checkpoint resume" in source.lower()
    assert "exact-restart" in source.lower() or "exact restart" in source.lower()


def test_r2_default_baseline_path() -> None:
    assert resolve_selected_baseline_path("E1-R2") == (
        ROOT / "configs/frozen/e1_r2_selected_baseline.yaml"
    )
    assert resolve_selected_baseline_path(None) == (
        ROOT / "configs/frozen/e1_selected_baseline.yaml"
    )
    recorded = load_json(
        ROOT / "configs/frozen/E1_R2_FROZEN_CONFIG_MANIFEST.json"
    )["files"]["configs/frozen/e1_r2_selected_baseline.yaml"]["sha256"]
    assert verify_r2_selected_baseline(R2_SELECTED_BASELINE) == recorded
    assert r2_selected_baseline_file_hash() == recorded
    assert sha256_file(R2_SELECTED_BASELINE) == recorded
    selected = verify_r2_selected_baseline(R2_SELECTED_BASELINE)
    assert selected
    from raven_mcs.utils.serialization import load_yaml

    assert load_yaml(R2_SELECTED_BASELINE)["selected_baseline"] == R2_BASELINE_METHOD


def test_r2_default_gate_directories() -> None:
    dirs = resolve_r2_formal_directories()
    assert dirs == {
        "aggregate_dir": ROOT / "outputs/aggregate/E1_R2",
        "statistics_dir": ROOT / "outputs/statistics/E1_R2",
        "gates_dir": ROOT / "outputs/gates/E1_R2",
    }
    assert SMOKE_OUTPUT == SMOKE_OUTPUT_EXACT_HEAD
    assert allowed_smoke_output(SMOKE_OUTPUT_EXACT_HEAD)
    assert allowed_smoke_output(SMOKE_OUTPUT_COMPAT)
    assert ALLOWED_SMOKE_OUTPUTS == {
        SMOKE_OUTPUT_COMPAT.resolve(),
        SMOKE_OUTPUT_EXACT_HEAD.resolve(),
    }


def test_formal_rejection_reasons_include_required_phrases() -> None:
    import pandas as pd

    frame = pd.DataFrame([{
        "seed": 27001,
        "formal": False,
        "num_windows": 2,
        "smoke": True,
        "method": "raven",
    }])
    reasons = formal_rejection_reasons(frame)
    assert "formal=false" in reasons
    assert "windows=2" in reasons
    assert "seed not in formal registry" in reasons
    assert "incomplete 25-run matrix" in reasons
    with pytest.raises(RuntimeError, match="formal=false"):
        validate_rows(frame, mode="formal")

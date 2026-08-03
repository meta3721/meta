from __future__ import annotations

import importlib.util
import json
import zipfile
from pathlib import Path
from types import ModuleType

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _load_script(name: str) -> ModuleType:
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FREEZE = _load_script("freeze_e1_r2_protocol")
AUDIT = _load_script("audit_e1_r2_formal_seed_noninspection")
GATES = _load_script("check_e1_r2_protocol_gates")
EXPORT = _load_script("export_e1_r2_protocol_calibration_evidence")


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _selection_inputs(root: Path) -> tuple[Path, Path]:
    calibration = root / "outputs/e1_r2/calibration/calibration_summary.json"
    validation = root / "outputs/e1_r2/validation/validation_summary.json"
    _write_json(
        calibration,
        {
            "calibration_complete": True,
            "candidate_status": {"C1": "PASSED"},
            "selection_split": "calibration",
            "calibration_seeds": [27001, 27002, 27003, 27004, 27005],
            "passed_candidates": ["C1"],
            "test_read_count": 0,
            "selected_protocol": {
                "dataset": "sensorscope",
                "methods": ["fedavg_window", "raven"],
                "formal_seeds": [28001, 28002, 28003, 28004, 28005],
                "num_windows": 100,
            },
            "protocol": {"num_windows": 100},
            "selected_weight_safety": {
                "selected_candidate": "C1",
                "selected_parameters": {
                    "p_min": 0.1,
                    "pi_min": 1e-6,
                    "a_max": 20.0,
                    "q_min": 0.1,
                    "d_max": 10.0,
                },
                "gates": {
                    "first_stage_clip_rate_max": 0.05,
                    "second_stage_clip_rate_max": 0.05,
                },
            },
            "analysis_plan": {
                "primary_estimand": "RMSE_mu",
                "multiplicity": "Holm",
            },
        },
    )
    _write_json(
        validation,
        {
            "validation_pass": True,
            "evaluation_split": "validation",
            "validation_seeds": [27101, 27102, 27103, 27104, 27105],
            "selected_validation_baseline": "fedasync_window",
            "selected_candidate": "C1",
            "selected_a_max": 20.0,
            "passed_candidates": ["C1"],
            "candidates": {"C1": {"status": "PASSED", "a_max": 20.0}},
            "test_read_count": 0,
            "formal_seed_read_count": 0,
            "test_metrics_read": False,
        },
    )
    return calibration, validation


def test_missing_prerequisites_block_without_frozen_writes(tmp_path: Path) -> None:
    output = tmp_path / "configs/frozen"
    result = FREEZE.freeze_protocol(
        tmp_path / "missing-calibration.json",
        tmp_path / "missing-validation.json",
        output,
    )
    assert result["status"] == "BLOCKED"
    assert result["formal_experiments_run"] == 0
    assert not output.exists()


def test_freeze_generates_only_new_r2_configs_and_sealed_manifest(
    tmp_path: Path,
) -> None:
    calibration, validation = _selection_inputs(tmp_path)
    output = tmp_path / "configs/frozen"
    result = FREEZE.freeze_protocol(calibration, validation, output)
    assert result["status"] == "PASS", result
    assert result["formal_experiments_run"] == 0
    expected = {
        "e1_r2_protocol.yaml",
        "e1_r2_weight_safety.yaml",
        "e1_r2_selected_baseline.yaml",
        "e1_r2_candidate_selection.json",
        "e1_r2_seed_registry.yaml",
        "e1_r2_eventtrace_manifest.json",
        "e1_r2_analysis.yaml",
        "e1_r2_scheduler.yaml",
        "E1_R2_FROZEN_CONFIG_MANIFEST.json",
    }
    assert {path.name for path in output.iterdir()} == expected
    manifest = json.loads(
        (output / "E1_R2_FROZEN_CONFIG_MANIFEST.json").read_text()
    )
    assert manifest["formal_seeds"] == [28001, 28002, 28003, 28004, 28005]
    assert manifest["formal_experiments_run"] == 0
    assert {
        metadata["semantic_role"]
        for metadata in manifest["files"].values()
    } == {
        "protocol", "weight_safety", "selected_baseline",
        "candidate_selection", "seed_registry", "eventtrace_manifest",
        "analysis", "scheduler",
    }
    scheduler = yaml.safe_load((output / "e1_r2_scheduler.yaml").read_text())
    assert scheduler["matrix_size"] == 10
    assert scheduler["formal_execution_performed"] is False


def test_formal_seed_overlap_blocks_freeze(tmp_path: Path) -> None:
    calibration, validation = _selection_inputs(tmp_path)
    value = json.loads(validation.read_text())
    value["validation_seeds"] = [27101, 27102, 27103, 27104, 28001]
    _write_json(validation, value)
    result = FREEZE.freeze_protocol(
        calibration, validation, tmp_path / "configs/frozen"
    )
    assert result["status"] == "BLOCKED"
    assert "formal seed" in result["reason"]


def test_freeze_consumes_calibration_and_validation_summary_contract(
    tmp_path: Path,
) -> None:
    calibration = tmp_path / "outputs/e1_r2/calibration/calibration_summary.json"
    validation = tmp_path / "outputs/e1_r2/validation/validation_summary.json"
    _write_json(
        calibration,
        {
            "status": "PASS",
            "seeds": [27001, 27002, 27003, 27004, 27005],
            "calibration_seeds": [27001, 27002, 27003, 27004, 27005],
            "passed_candidates": ["C1", "C2"],
            "formal_authorized": False,
        },
    )
    _write_json(
        validation,
        {
            "status": "PASS",
            "selection_split": "validation",
            "test_read_count": 0,
            "formal_seed_read_count": 0,
            "validation_seeds": [27101, 27102, 27103, 27104, 27105],
            "selected_validation_baseline": "fedasync_window",
            "passed_candidates": ["C1", "C2"],
            "candidates": {
                "C1": {"status": "PASSED", "a_max": 30.0},
                "C2": {"status": "PASSED", "a_max": 40.0},
            },
            "formal_authorized": False,
        },
    )
    frozen = tmp_path / "configs/frozen"
    result = FREEZE.freeze_protocol(calibration, validation, frozen)
    assert result["status"] == "PASS"
    protocol = yaml.safe_load((frozen / "e1_r2_protocol.yaml").read_text())
    safety = yaml.safe_load((frozen / "e1_r2_weight_safety.yaml").read_text())
    assert protocol["formal_seeds"] == [28001, 28002, 28003, 28004, 28005]
    assert protocol["selected_validation_baseline"] == "fedasync_window"
    assert safety["selected_candidate"] == "C1"
    assert safety["selected_parameters"]["a_max"] == 30.0


def test_noninspection_audit_proves_zero_records(tmp_path: Path) -> None:
    calibration, validation = _selection_inputs(tmp_path)
    frozen = tmp_path / "configs/frozen"
    assert FREEZE.freeze_protocol(calibration, validation, frozen)["status"] == "PASS"
    result = AUDIT.audit_noninspection(
        frozen / "E1_R2_FROZEN_CONFIG_MANIFEST.json",
        [
            tmp_path / "outputs/e1_r2/calibration",
            tmp_path / "outputs/e1_r2/validation",
        ],
    )
    assert result["status"] == "PASS"
    assert result["formal_seed_training_records"] == 0
    assert result["formal_seed_metric_records"] == 0
    assert result["formal_seed_prediction_records"] == 0


def test_noninspection_audit_detects_formal_seed_metrics(tmp_path: Path) -> None:
    calibration, validation = _selection_inputs(tmp_path)
    frozen = tmp_path / "configs/frozen"
    FREEZE.freeze_protocol(calibration, validation, frozen)
    _write_json(
        tmp_path / "outputs/e1_r2/validation/forbidden.json",
        {"seed": 28001, "metrics": {"RMSE_mu": 1.0}},
    )
    result = AUDIT.audit_noninspection(
        frozen / "E1_R2_FROZEN_CONFIG_MANIFEST.json",
        [tmp_path / "outputs/e1_r2/validation"],
    )
    assert result["status"] == "FAIL"
    assert result["formal_seed_metric_records"] > 0


def test_r2p_gates_pass_with_complete_post_selection_evidence(
    tmp_path: Path,
) -> None:
    calibration, validation = _selection_inputs(tmp_path)
    frozen = tmp_path / "configs/frozen"
    freeze = FREEZE.freeze_protocol(calibration, validation, frozen)
    _write_json(
        tmp_path / "outputs/audits/E1_R2_PROTOCOL_FREEZE_STATUS.json",
        freeze,
    )
    audit = AUDIT.audit_noninspection(
        frozen / "E1_R2_FROZEN_CONFIG_MANIFEST.json",
        [
            tmp_path / "outputs/e1_r2/calibration",
            tmp_path / "outputs/e1_r2/validation",
        ],
    )
    _write_json(
        tmp_path / "outputs/audits/E1_R2_FORMAL_SEED_NONINSPECTION.json",
        audit,
    )
    archive = tmp_path / "archive/e1_r1_weight_safety_failure"
    archived = archive / "evidence.txt"
    archived.parent.mkdir(parents=True, exist_ok=True)
    archived.write_text("retained\n", encoding="utf-8")
    import hashlib
    _write_json(archive / "ARCHIVE_HASHES.json", {
        "algorithm": "sha256",
        "files": {"evidence.txt": hashlib.sha256(archived.read_bytes()).hexdigest()},
    })
    _write_json(archive / "E1_R1_FINAL_STATUS.json", {
        "E1_R1_weight_safety": "FAIL",
        "remaining_runs": "PERMANENTLY_STOPPED",
    })
    registry = tmp_path / "configs/e1_r2/candidate_registry.yaml"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(yaml.safe_dump({
        "registry_stage": "PRE_RUN",
        "candidates": {"C0": {"a_max": 20.0}},
        "candidate_registry_hash": "fixture",
    }), encoding="utf-8")
    result = GATES.evaluate_gates(tmp_path)
    assert result["status"] == "PASS", result["gates"]
    assert set(result["gates"]) == {f"R2P-G{index}" for index in range(1, 11)}
    assert set(result["gates"].values()) == {"PASS"}
    assert result["scheduler_dry_run"]["formal_execution_performed"] is False


def test_gate_checker_reports_blocked_when_outputs_absent(tmp_path: Path) -> None:
    result = GATES.evaluate_gates(tmp_path)
    assert result["status"] == "BLOCKED"
    assert result["all_pass"] is False
    assert result["formal_experiments_run"] == 0


def test_partial_export_still_creates_report_readme_and_zip(
    tmp_path: Path,
) -> None:
    result = EXPORT.export_evidence(tmp_path, tmp_path / "deliverables")
    assert result["status"] == "PARTIAL"
    assert result["formal_experiments_run"] == 0
    assert Path(result["report"]).is_file()
    assert Path(result["readme"]).is_file()
    with zipfile.ZipFile(result["archive"]) as archive:
        assert EXPORT.REPORT_NAME in archive.namelist()
        assert EXPORT.README_NAME in archive.namelist()


def test_post_selection_scripts_cannot_invoke_formal_runner() -> None:
    for name in (
        "freeze_e1_r2_protocol.py",
        "audit_e1_r2_formal_seed_noninspection.py",
        "check_e1_r2_protocol_gates.py",
        "export_e1_r2_protocol_calibration_evidence.py",
    ):
        source = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        assert "run_official_method" not in source
        assert "run_e1_formal" not in source
        assert "subprocess" not in source

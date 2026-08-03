"""Identity and scaffolding tests for E1-R2 candidate-head check."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
AUTHORIZED = "53e277c53b01695330652b8e1bc8a234909d56e5"
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))


def _load(name: str) -> ModuleType:
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


PREFLIGHT = _load("check_e1_r2_formal_preflight")
GATES = _load("check_e1_r2_candidate_head_gates")
REPLAY = _load("replay_e1_r2_calval_source_identity")
EXPORT = _load("export_e1_r2_candidate_head_check_evidence")
RECOMPUTE = _load("recompute_e1_delta_cal")


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def _payload_hash(value: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, default=str,
        ).encode("utf-8")
    ).hexdigest()


def _head(root: Path = ROOT) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_exact_head_preflight_requires_expected_commit() -> None:
    with pytest.raises(ValueError, match="expected-commit"):
        PREFLIGHT.check_preflight(ROOT, "exact-head")
    with pytest.raises(ValueError, match="expected-commit"):
        PREFLIGHT.check_preflight(ROOT, "exact_head", expected_commit=None)
    wrong = "0" * 40
    result = PREFLIGHT.check_preflight(
        ROOT, "exact-head", expected_commit=wrong
    )
    assert result["mode"] == "exact-head"
    assert result["checks"]["expected_commit_match"] == "FAIL"
    assert result["status"] == "FAIL"


def test_exact_head_smoke_manifest_commit_matches_head(tmp_path: Path) -> None:
    head = "a" * 40
    smoke = tmp_path / "outputs/smoke/e1_r2_exact_head/run1"
    _write(
        smoke / "manifest.json",
        json.dumps({
            "formal": False,
            "smoke": True,
            "performance_claim": False,
            "seed": 27001,
            "num_windows": 2,
            "execution_commit": head,
            "git_commit": head,
        }),
    )
    _write(
        smoke / "metrics_run.json",
        json.dumps({
            "first_stage_clip_observed_micro_true_exceed": 0.01,
            "first_stage_clip_rate_legacy_macro": 0.02,
            "first_stage_clip_hard_gate_metric": (
                "first_stage_clip_observed_micro_true_exceed"
            ),
        }),
    )
    _write(smoke / "RUN_GATE_REPORT.json", json.dumps({"all_pass": True}))
    assert PREFLIGHT._smoke_ok(tmp_path, smoke.parent, require_head=head) is True
    assert PREFLIGHT._smoke_ok(
        tmp_path, smoke.parent, require_head="b" * 40
    ) is False


def test_exact_head_replay_commit_matches_head(monkeypatch: pytest.MonkeyPatch) -> None:
    head = _head()
    monkeypatch.setattr(REPLAY, "_clean", lambda root: True)
    monkeypatch.setattr(REPLAY, "_head", lambda root: head)

    def _boom(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("run must not execute in this unit test")

    monkeypatch.setattr(REPLAY, "run_r2_method", _boom)
    with pytest.raises(RuntimeError, match="does not match"):
        # Fail before any numeric work when candidate differs from HEAD.
        REPLAY.replay(
            ROOT,
            ROOT / "outputs/replay/e1_r2_exact_head",
            candidate_commit="c" * 40,
        )


def test_head_gate_detects_mixed_commits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = "a" * 40
    other = "b" * 40
    def _fake_git(root: Path, *args: str) -> str:
        if args[:2] == ("rev-parse", "HEAD"):
            return expected
        if args[:2] == ("status", "--porcelain"):
            return ""
        return expected

    monkeypatch.setattr(GATES, "_git", _fake_git)
    _write(
        tmp_path / "outputs/preflight/E1_R2_EXACT_HEAD_PREFLIGHT.json",
        json.dumps({
            "expected_commit": expected,
            "candidate_commit": expected,
            "runtime_head": expected,
            "runtime_execution_commit": expected,
            "runtime_git_clean": True,
            "status": "PASS",
            "formal_experiments_run": 0,
            "protocol_file_hash": "f" * 64,
            "protocol_payload_hash": "p" * 64,
        }),
    )
    _write(
        tmp_path / "outputs/replay/e1_r2_exact_head/E1_R2_EXACT_HEAD_REPLAY.json",
        json.dumps({
            "candidate_commit": other,
            "replay_status": "PASS",
            "status": "PASS",
            "unexplained_numeric_difference_count": 0,
        }),
    )
    for method in ("fedavg_window", "raven"):
        _write(
            tmp_path / f"outputs/smoke/e1_r2_exact_head/{method}/manifest.json",
            json.dumps({
                "method": method,
                "execution_commit": expected,
                "git_commit": expected,
                "formal": False,
                "smoke": True,
                "seed": 27001,
                "git_clean_at_start": True,
            }),
        )
    _write(
        tmp_path / "outputs/audits/E1_R2_FINAL_CANDIDATE_SOURCE_IDENTITY.json",
        json.dumps({
            "candidate_commit": expected,
            "bundle_verify_status": "PASS",
            "bundle_sha256": "1" * 64,
            "archive_sha256": "2" * 64,
        }),
    )
    _write(
        tmp_path / "configs/frozen/e1_r2_protocol.yaml",
        f"authorized_algorithm_commit: {AUTHORIZED}\n",
    )
    result = GATES.evaluate_candidate_head_gates(
        tmp_path, expected_commit=expected
    )
    assert result["mixed_commits"] is True
    assert result["gates"]["HEAD-G4"] == "FAIL"
    assert result["status"] == "FAIL"


def test_atomic_and_client_stratum_hash_names_distinct() -> None:
    _, summary = RECOMPUTE.recompute(ROOT)
    assert "atomic_target_weight_hash" in summary
    assert "client_stratum_target_mass_hash" in summary
    assert (
        summary["atomic_target_weight_hash"]
        != summary["client_stratum_target_mass_hash"]
    )
    pi = json.loads(
        (ROOT / "configs/frozen/e1_pi_target_manifest.json").read_text(encoding="utf-8")
    )
    assert summary["atomic_target_weight_hash"] == pi["atomic_target_weight_hash"]
    assert (
        summary["client_stratum_target_mass_hash"]
        == pi["client_stratum_target_mass_hash"]
    )
    source = (ROOT / "scripts/recompute_e1_delta_cal.py").read_text(encoding="utf-8")
    assert 'sha256_json(\n            selected[["unit_id", "target_weight"]' not in source


def test_protocol_payload_hash_cross_platform() -> None:
    protocol_path = ROOT / "configs/frozen/e1_r2_protocol.yaml"
    text_lf = protocol_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    text_crlf = text_lf.replace("\n", "\r\n")
    payload_lf = yaml.safe_load(text_lf)
    payload_crlf = yaml.safe_load(text_crlf)
    assert _payload_hash(payload_lf) == _payload_hash(payload_crlf)
    assert PREFLIGHT._payload_hash(payload_lf) == _payload_hash(payload_lf)


def test_protocol_file_hash_matches_clean_checkout() -> None:
    protocol_path = ROOT / "configs/frozen/e1_r2_protocol.yaml"
    checkout_hash = hashlib.sha256(protocol_path.read_bytes()).hexdigest()
    manifest = json.loads(
        (ROOT / "configs/frozen/E1_R2_FROZEN_CONFIG_MANIFEST.json").read_text(
            encoding="utf-8"
        )
    )
    assert (
        manifest["files"]["configs/frozen/e1_r2_protocol.yaml"]["sha256"]
        == checkout_hash
    )
    protocol = yaml.safe_load(protocol_path.read_text(encoding="utf-8"))
    assert checkout_hash != PREFLIGHT._payload_hash(protocol)


def test_bundle_contains_candidate_commit(tmp_path: Path) -> None:
    candidate = "d" * 40
    bundle = {
        "candidate_commit": candidate,
        "package": "E1_R2_CANDIDATE_HEAD_CHECK_R1",
        "status": "PASS",
    }
    path = tmp_path / "outputs/audits/E1_R2_CANDIDATE_HEAD_BUNDLE_IDENTITY.json"
    _write(path, json.dumps(bundle))
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["candidate_commit"] == candidate
    # Exporter hash JSON also records candidate_commit outside the ZIP.
    _write(
        tmp_path / "outputs/preflight/E1_R2_EXACT_HEAD_PREFLIGHT.json",
        json.dumps({"expected_commit": candidate, "checks": {}}),
    )
    _write(tmp_path / "configs/frozen/e1_r2_protocol.yaml", "protocol_version: E1-R2\n")
    _write(
        tmp_path / "configs/frozen/E1_R2_FROZEN_CONFIG_MANIFEST.json", "{}\n"
    )
    _write(
        tmp_path / "configs/frozen/e1_r2_selected_baseline.yaml",
        "selected_baseline: flamf_timealign_adapted\n",
    )
    _write(tmp_path / ".gitattributes", "*.py text eol=lf\n")
    for relative in (
        "scripts/check_e1_r2_formal_preflight.py",
        "scripts/replay_e1_r2_calval_source_identity.py",
        "scripts/check_e1_r2_candidate_head_gates.py",
        "scripts/export_e1_r2_candidate_head_check_evidence.py",
        "scripts/run_e1_r2_candidate_head_logged.py",
        "tests/unit/test_e1_r2_candidate_head_identity.py",
        "docs/reports/E1_TARGET_HASH_SEMANTICS.md",
        "outputs/diagnostics/E1_TARGET_HASH_SEMANTICS.json",
        "outputs/audits/E1_R2_CANDIDATE_HEAD_GATES.json",
        "outputs/replay/e1_r2_exact_head/E1_R2_EXACT_HEAD_REPLAY.json",
        "logs/E1_R2_CANDIDATE_HEAD_CHECK_R1_EXACT_COMMANDS.jsonl",
    ):
        _write(tmp_path / relative, "{}\n" if relative.endswith(".json") else "x\n")
    _write(
        tmp_path / "outputs/smoke/e1_r2_exact_head/run1/manifest.json",
        json.dumps({"execution_commit": candidate}),
    )
    result = EXPORT.export_evidence(
        tmp_path, tmp_path / "deliverables/TO_SUBMIT_E1_R2_CANDIDATE_HEAD_CHECK_R1"
    )
    hash_json = json.loads(
        Path(result["hash_json"]).read_text(encoding="utf-8")
    )
    assert hash_json["candidate_commit"] == candidate
    import zipfile

    with zipfile.ZipFile(result["archive"]) as zf:
        assert "FINAL_DELIVERABLE_HASHES.json" not in zf.namelist()


def test_exact_head_aggregate_rejects_smoke(tmp_path: Path) -> None:
    stderr = tmp_path / "logs/e1_r2_candidate_head/aggregate.stderr.log"
    _write(
        stderr,
        "RuntimeError: nonformal two-window smoke rejected (formal=false)\n",
    )
    ledger = tmp_path / "logs/E1_R2_CANDIDATE_HEAD_CHECK_R1_EXACT_COMMANDS.jsonl"
    _write(
        ledger,
        json.dumps({
            "stage": "aggregate_rejection_exact_head",
            "exit_code": 1,
            "stderr_log": stderr.relative_to(tmp_path).as_posix(),
            "runtime_commit": "a" * 40,
        })
        + "\n",
    )
    assert PREFLIGHT._aggregate_ok(tmp_path, [ledger]) is True
    empty = tmp_path / "logs/empty.jsonl"
    _write(empty, "")
    assert PREFLIGHT._aggregate_ok(tmp_path, [empty]) is False
    _write(
        tmp_path / "outputs/audits/E1_R2_EXACT_HEAD_AGGREGATE_REJECTION.json",
        json.dumps({
            "rejection_status": "PASS",
            "rejected_as_expected": True,
            "error": "nonformal two-window smoke rejected (formal=false)",
            "reasons": ["formal=false", "windows=2"],
        }),
    )
    assert PREFLIGHT._aggregate_ok(tmp_path, [empty]) is True


def test_gitattributes_declares_lf_for_text_patterns() -> None:
    text = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    for pattern in ("*.py", "*.yaml", "*.yml", "*.json", "*.md", "*.txt", "*.csv"):
        assert f"{pattern}" in text
        assert "text eol=lf" in text
        assert any(
            line.split()[:3] == [pattern, "text", "eol=lf"]
            for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )


def test_export_defines_twenty_two_report_sections() -> None:
    assert len(EXPORT.REPORT_SECTIONS) == 22

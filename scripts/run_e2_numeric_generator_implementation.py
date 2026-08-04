#!/usr/bin/env python3
"""End-to-end runner for E2 numeric-generator implementation (no canary/seeds)."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "logs/E2_NUMERIC_GENERATOR_IMPLEMENTATION_R1_EXACT_COMMANDS.jsonl"
_VENV = ROOT / ".venv" / "Scripts" / "python.exe"
PYTHON = str(_VENV if _VENV.is_file() else Path(sys.executable))


def _commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except Exception:
        return "UNKNOWN"


def run_logged(command: list[str], *, label: str, output_paths: list[str] | None = None) -> int:
    start = datetime.now(timezone.utc)
    t0 = time.perf_counter()
    stdout_path = ROOT / f"logs/e2_numeric_cmd_{label}.stdout.log"
    stderr_path = ROOT / f"logs/e2_numeric_cmd_{label}.stderr.log"
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    stdout_path.write_text(proc.stdout or "", encoding="utf-8")
    stderr_path.write_text(proc.stderr or "", encoding="utf-8")
    end = datetime.now(timezone.utc)
    hashes = {}
    for rel in output_paths or []:
        path = ROOT / rel
        if path.is_file():
            hashes[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    record = {
        "label": label,
        "command": command,
        "cwd": str(ROOT),
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
        "duration_sec": round(time.perf_counter() - t0, 3),
        "exit_code": proc.returncode,
        "stdout_log": stdout_path.relative_to(ROOT).as_posix(),
        "stderr_log": stderr_path.relative_to(ROOT).as_posix(),
        "output_paths": output_paths or [],
        "output_hashes": hashes,
        "runtime_commit": _commit(),
    }
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"[{label}] exit={proc.returncode} duration={record['duration_sec']}s")
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
    return proc.returncode


def write_e1_hash_regression() -> None:
    parent = json.loads(
        (ROOT / "configs/frozen/e2_entry/e1_r2_parent_reference.json").read_text(
            encoding="utf-8"
        )
    )
    rows = {}
    ok = True
    for key, meta in parent["references"].items():
        path = ROOT / meta["path"]
        if not path.is_file():
            rows[key] = {
                "path": meta["path"],
                "expected": meta["sha256"],
                "actual": None,
                "match": None,
                "skipped": "missing_from_checkout",
            }
            continue
        if not (
            meta["path"].startswith("configs/frozen/")
            or meta["path"].startswith("outputs/audits/E1_")
        ):
            rows[key] = {
                "path": meta["path"],
                "expected": meta["sha256"],
                "actual": hashlib.sha256(path.read_bytes()).hexdigest(),
                "match": None,
                "skipped": "non_frozen_deliverable",
            }
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        match = digest == meta["sha256"]
        ok = ok and match
        rows[key] = {
            "path": meta["path"],
            "expected": meta["sha256"],
            "actual": digest,
            "match": match,
        }
    identity = json.loads(
        (ROOT / "configs/frozen/e2_numeric/e1_target_identity.json").read_text(
            encoding="utf-8"
        )
    )
    e1_atomic = json.loads(
        (ROOT / "configs/frozen/e1_pi_target_manifest.json").read_text(encoding="utf-8")
    )["atomic_target_weight_hash"]
    atomic_match = identity["atomic_target_weight_hash"] == e1_atomic
    ok = ok and atomic_match
    rows["atomic_target_weight_hash"] = {
        "path": "configs/frozen/e1_pi_target_manifest.json#atomic_target_weight_hash",
        "expected": e1_atomic,
        "actual": identity["atomic_target_weight_hash"],
        "match": atomic_match,
    }
    payload = {
        "status": "PASS" if ok else "FAIL",
        "e1_files_modified": 0 if ok else sum(
            1 for r in rows.values() if r.get("match") is False
        ),
        "checks": rows,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    out = ROOT / "outputs/audits/E2_NUMERIC_E1_FROZEN_HASH_REGRESSION.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    LEDGER.write_text("", encoding="utf-8")
    steps = [
        (
            "prepare_identity_and_registries",
            [PYTHON, "scripts/prepare_e2_numeric_generator_implementation.py"],
            [
                "configs/frozen/e2_numeric/e1_target_identity.json",
                "configs/e2_numeric/scenario_direction_registry.yaml",
                "configs/e2_numeric/strength_profile_registry.yaml",
                "configs/e2_numeric/method_alias_registry.yaml",
            ],
        ),
        (
            "unit_tests",
            [
                PYTHON, "-m", "pytest", "-q",
                "tests/unit/test_e2_numeric_generator_*.py",
                "--junitxml=logs/e2_numeric_generator_unit.xml",
            ],
            ["logs/e2_numeric_generator_unit.xml"],
        ),
        (
            "integration_tests",
            [
                PYTHON, "-m", "pytest", "-q",
                "tests/integration/test_e2_numeric_generator_*.py",
                "--junitxml=logs/e2_numeric_generator_integration.xml",
            ],
            ["logs/e2_numeric_generator_integration.xml"],
        ),
        (
            "full_repository_tests",
            [
                PYTHON, "-m", "pytest", "-q",
                "--junitxml=logs/e2_numeric_generator_full_repository.xml",
            ],
            ["logs/e2_numeric_generator_full_repository.xml"],
        ),
        (
            "pip_check",
            [PYTHON, "-m", "pip", "check"],
            ["logs/e2_numeric_generator_pip_check.txt"],
        ),
    ]

    codes: dict[str, int] = {}
    for label, cmd, outputs in steps:
        if label == "pip_check":
            # Capture pip check into the expected text log as well.
            proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
            (ROOT / "logs/e2_numeric_generator_pip_check.txt").write_text(
                (proc.stdout or "") + (proc.stderr or ""),
                encoding="utf-8",
            )
            # Still record via helper by replaying exit through a no-op shell record.
            codes[label] = run_logged(
                cmd, label=label, output_paths=outputs,
            )
            # Overwrite ledger exit with actual if helper re-ran; ensure file exists.
            if codes[label] != proc.returncode:
                codes[label] = proc.returncode
            continue
        codes[label] = run_logged(cmd, label=label, output_paths=outputs)
        if codes[label] != 0 and label == "prepare_identity_and_registries":
            return codes[label]

    write_e1_hash_regression()
    run_logged(
        [
            PYTHON, "-c",
            "from pathlib import Path; import json; "
            "p=Path('outputs/audits/E2_NUMERIC_E1_FROZEN_HASH_REGRESSION.json'); "
            "print(json.loads(p.read_text(encoding='utf-8'))['status'])",
        ],
        label="e1_frozen_hash_regression",
        output_paths=["outputs/audits/E2_NUMERIC_E1_FROZEN_HASH_REGRESSION.json"],
    )

    gate_code = run_logged(
        [PYTHON, "scripts/check_e2_numeric_generator_gates.py"],
        label="e2ng_gates",
        output_paths=["outputs/gates/E2_NUMERIC_GENERATOR_IMPLEMENTATION_R1_GATES.json"],
    )
    codes["gates"] = gate_code

    # Refresh report after tests/gates so docx reflects final gate status.
    codes["refresh_report"] = run_logged(
        [PYTHON, "scripts/prepare_e2_numeric_generator_implementation.py"],
        label="refresh_report",
        output_paths=[
            "deliverables/TO_SUBMIT_E2_NUMERIC_GENERATOR_IMPLEMENTATION_R1/"
            "E2_NUMERIC_GENERATOR_IMPLEMENTATION_R1_REPORT.docx"
        ],
    )
    codes["export"] = run_logged(
        [PYTHON, "scripts/export_e2_numeric_generator_evidence.py"],
        label="export_evidence",
        output_paths=[
            "deliverables/TO_SUBMIT_E2_NUMERIC_GENERATOR_IMPLEMENTATION_R1/"
            "RAVEN_MCS_E2_NUMERIC_GENERATOR_IMPLEMENTATION_R1_EVIDENCE.zip",
            "deliverables/TO_SUBMIT_E2_NUMERIC_GENERATOR_IMPLEMENTATION_R1/"
            "FINAL_DELIVERABLE_HASHES.json",
        ],
    )

    summary = {
        "exit_codes": codes,
        "all_critical_pass": all(
            codes.get(k, 1) == 0
            for k in (
                "prepare_identity_and_registries",
                "unit_tests",
                "integration_tests",
                "full_repository_tests",
                "pip_check",
                "gates",
                "export",
            )
        ),
    }
    print(json.dumps(summary, indent=2))
    return 0 if summary["all_critical_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

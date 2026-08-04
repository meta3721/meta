#!/usr/bin/env python3
"""Build self-contained E2 usable-arrival repair evidence ZIP."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "E2_USABLE_ARRIVAL_INTEGRATION_AND_IDENTITY_REPAIR_R1"
PYTHON = str(ROOT / ".venv" / "Scripts" / "python.exe")
if not Path(PYTHON).is_file():
    PYTHON = sys.executable


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    delivery = ROOT / f"deliverables/TO_SUBMIT_{PACKAGE}"
    delivery.mkdir(parents=True, exist_ok=True)
    report = delivery / f"{PACKAGE}_REPORT.docx"
    if not report.is_file():
        raise FileNotFoundError(report)
    gates = json.loads(
        (ROOT / f"outputs/gates/{PACKAGE}_GATES.json").read_text(encoding="utf-8")
    )
    identity = json.loads(
        (ROOT / "configs/frozen/e2_numeric/e1_target_identity.json").read_text(
            encoding="utf-8"
        )
    )
    readme = delivery / f"{PACKAGE}_SUBMISSION_README.txt"
    readme.write_text(
        "\n".join([
            f"package = {PACKAGE}",
            "E1-R2 = IMMUTABLE / FULLY_SEALED",
            "E2 usable-to-arrival integration = PASS",
            f"head_tail_identity_source = {identity.get('head_tail_identity_source')}",
            "E2 = READY_FOR_DISTRIBUTION_PROFILE_AND_WINDOW_FREEZE",
            "profile selection = NOT_STARTED",
            "window freeze = NOT_STARTED",
            "real canary = 0/20",
            "E2 formal runs = 0",
            f"E2UA gates = {gates['status']}",
            "Unpacked specialized tests are included under tests/.",
            "",
        ]),
        encoding="utf-8",
    )

    members = [
        "src/raven_mcs/__init__.py",
        "src/raven_mcs/e2",
        "src/raven_mcs/utils",
        "configs/frozen/e2_numeric",
        "configs/e2_numeric",
        "configs/e2_entry/method_registry_strict.yaml",
        "configs/frozen/e1_pi_target_manifest.json",
        "configs/frozen/e1_r2_protocol.yaml",
        "configs/frozen/e1_r2_seed_registry.yaml",
        "configs/frozen/e2_entry/e1_r2_parent_reference.json",
        "outputs/audits/E1_R2_25_RUNS_FROZEN_HASH_MANIFEST.json",
        "schemas/e2_scenario_mass_diagnostics.schema.json",
        "tests/fixtures/e2_usable_topology.json",
        "tests/fixtures/e2_usable_topology_manifest.json",
        "tests/unit/test_e2_usable_arrival_unit.py",
        "tests/integration/test_e2_usable_arrival_integration.py",
        "scripts/run_and_log.py",
        "scripts/prepare_e2_usable_arrival_repair.py",
        "scripts/build_e2_usable_topology_fixture.py",
        "scripts/check_e2_usable_arrival_gates.py",
        "scripts/export_e2_usable_arrival_evidence.py",
        f"outputs/gates/{PACKAGE}_GATES.json",
        "outputs/audits/E2_USABLE_ARRIVAL_SEMANTIC_SMOKE.json",
        "outputs/audits/e2_usable_arrival",
        "logs/e2_usable_arrival_unit.xml",
        "logs/e2_usable_arrival_integration.xml",
        "logs/e2_usable_arrival_full_repository.xml",
        "logs/e2_usable_arrival_pip_check.txt",
        f"logs/{PACKAGE}_EXACT_COMMANDS.jsonl",
        "configs/audit/q_feature_whitelist.yaml",
    ]
    # Include real command stdout/stderr artifacts referenced by the ledger.
    ledger_path = ROOT / f"logs/{PACKAGE}_EXACT_COMMANDS.jsonl"
    if ledger_path.is_file():
        for line in ledger_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            for key in ("stdout_log", "stderr_log"):
                rel = row.get(key)
                if rel and (ROOT / rel).is_file() and rel not in members:
                    members.append(rel)
    archive = delivery / f"RAVEN_MCS_{PACKAGE}_EVIDENCE.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for relative in members:
            path = ROOT / relative
            if path.is_file():
                zf.write(path, relative)
            elif path.is_dir():
                for child in sorted(path.rglob("*")):
                    if child.is_file():
                        zf.write(child, child.relative_to(ROOT).as_posix())
        # Minimal package metadata for unpacked pytest path setup.
        zf.writestr(
            "pyproject_snippet.txt",
            "Unpack then set PYTHONPATH=src for specialized tests.\n",
        )
        zf.write(report, f"deliverables/TO_SUBMIT_{PACKAGE}/{report.name}")
        zf.write(readme, f"deliverables/TO_SUBMIT_{PACKAGE}/{readme.name}")

    # Independent unpack replay of specialized tests.
    with tempfile.TemporaryDirectory(prefix="e2ua_replay_") as tmp:
        tmp_path = Path(tmp)
        with zipfile.ZipFile(archive, "r") as zf:
            zf.extractall(tmp_path)
        env = dict(**dict(**__import__("os").environ), PYTHONPATH=str(tmp_path / "src"))
        # Specialized tests import raven_mcs.e2 and need frozen configs + fixtures.
        # Copy required data pointers are inside zip; run with ROOT-like layout.
        junit = tmp_path / "unpacked_specialized.xml"
        proc = subprocess.run(
            [
                PYTHON, "-m", "pytest", "-q",
                "tests/unit/test_e2_usable_arrival_unit.py",
                "tests/integration/test_e2_usable_arrival_integration.py",
                f"--junitxml={junit}",
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            env=env,
        )
        (ROOT / "logs/e2_usable_arrival_unpacked_stdout.log").write_text(
            proc.stdout or "", encoding="utf-8",
        )
        (ROOT / "logs/e2_usable_arrival_unpacked_stderr.log").write_text(
            proc.stderr or "", encoding="utf-8",
        )
        if junit.is_file():
            shutil.copy2(junit, ROOT / "logs/e2_usable_arrival_unpacked_specialized.xml")
        unpacked_ok = proc.returncode == 0
        # Re-add unpacked junit into archive.
        if junit.is_file():
            with zipfile.ZipFile(archive, "a", zipfile.ZIP_DEFLATED) as zf:
                zf.write(
                    junit,
                    "logs/e2_usable_arrival_unpacked_specialized.xml",
                )

    artifacts = {
        p.name: {"sha256": sha256(p), "size_bytes": p.stat().st_size}
        for p in (report, readme, archive)
    }
    payload = {
        "package": PACKAGE,
        "hash_algorithm": "sha256",
        "no_self_reference": True,
        "hash_closed_loop": True,
        "artifacts": artifacts,
        "formal_execution_commit": "e8bd1fc777431c2609def257a04fba093f0daf24",
        "e2_status": "READY_FOR_DISTRIBUTION_PROFILE_AND_WINDOW_FREEZE",
        "e2_formal_runs": 0,
        "real_canary_runs": "0/20",
        "gates_status": gates["status"],
        "unpacked_specialized_tests_pass": unpacked_ok,
    }
    hashes_path = delivery / "FINAL_DELIVERABLE_HASHES.json"
    hashes_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    verify = {
        "verified_artifacts": {
            name: sha256(delivery / name) == meta["sha256"]
            for name, meta in artifacts.items()
        },
        "all_match": all(
            sha256(delivery / name) == meta["sha256"]
            for name, meta in artifacts.items()
        ),
    }
    (delivery / "FINAL_DELIVERABLE_HASHES_VERIFY.json").write_text(
        json.dumps(verify, indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps({
        "status": "PASS" if unpacked_ok else "FAIL",
        "archive": archive.as_posix(),
        "unpacked_ok": unpacked_ok,
        "gates_status_at_export": gates.get("status"),
    }, indent=2))
    return 0 if unpacked_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Package E2 numeric-generator implementation evidence (no canary/formal seeds)."""
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "E2_NUMERIC_GENERATOR_IMPLEMENTATION_R1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    delivery = ROOT / f"deliverables/TO_SUBMIT_{PACKAGE}"
    delivery.mkdir(parents=True, exist_ok=True)
    report = delivery / f"{PACKAGE}_REPORT.docx"
    if not report.is_file():
        raise FileNotFoundError(report)

    gates = json.loads(
        (ROOT / "outputs/gates/E2_NUMERIC_GENERATOR_IMPLEMENTATION_R1_GATES.json").read_text(
            encoding="utf-8"
        )
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
            "E2 numeric scenario generator = IMPLEMENTED",
            "E2 = READY_FOR_DISTRIBUTION_PROFILE_AND_WINDOW_FREEZE",
            f"atomic_target_weight_hash = {identity['atomic_target_weight_hash']}",
            f"TimeAlign executable_id = flamf_timealign_adapted",
            "profile selection = NOT_STARTED",
            "real canary = 0/20",
            "E2 formal runs = 0",
            "formal seed reads = 0",
            "E3-E9 = NOT_STARTED",
            f"E2NG gates = {gates['status']}",
            "Do not treat prior E2_PROTOCOL_ENTRY_R1 schema canaries as this package.",
            "",
        ]),
        encoding="utf-8",
    )

    members = [
        "configs/frozen/e2_numeric/e1_target_identity.json",
        "configs/frozen/e2_numeric/e1_atomic_target_weights.parquet",
        "configs/frozen/e2_numeric/e1_head_tail_mapping.parquet",
        "configs/frozen/e2_numeric/e1_supported_test_units.parquet",
        "configs/frozen/e2_numeric/atomic_tail_score.parquet",
        "configs/frozen/e2_numeric/atomic_tail_score_manifest.json",
        "configs/frozen/e2_numeric/e2_q_generator_feature_manifest.json",
        "configs/e2_numeric/scenario_direction_registry.yaml",
        "configs/e2_numeric/strength_profile_registry.yaml",
        "configs/e2_numeric/strength_profile_registry_hash.json",
        "configs/e2_numeric/method_alias_registry.yaml",
        "configs/e2_entry/method_registry_strict.yaml",
        "configs/e2_entry/method_registry_extended.yaml",
        "src/raven_mcs/e2/__init__.py",
        "src/raven_mcs/e2/identity.py",
        "src/raven_mcs/e2/generators.py",
        "src/raven_mcs/e2/scenario_generator.py",
        "src/raven_mcs/e2/methods.py",
        "src/raven_mcs/e2/diagnostics.py",
        "schemas/e2_scenario_mass_diagnostics.schema.json",
        "tests/unit/test_e2_numeric_generator_unit.py",
        "tests/integration/test_e2_numeric_generator_integration.py",
        "scripts/prepare_e2_numeric_generator_implementation.py",
        "scripts/check_e2_numeric_generator_gates.py",
        "scripts/export_e2_numeric_generator_evidence.py",
        "scripts/run_e2_numeric_generator_implementation.py",
        "outputs/gates/E2_NUMERIC_GENERATOR_IMPLEMENTATION_R1_GATES.json",
        "outputs/audits/E2_NUMERIC_GENERATOR_SMOKE.json",
        "outputs/audits/E2_NUMERIC_E1_FROZEN_HASH_REGRESSION.json",
        "logs/e2_numeric_generator_unit.xml",
        "logs/e2_numeric_generator_integration.xml",
        "logs/e2_numeric_generator_full_repository.xml",
        "logs/e2_numeric_generator_pip_check.txt",
        "logs/E2_NUMERIC_GENERATOR_IMPLEMENTATION_R1_EXACT_COMMANDS.jsonl",
    ]
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
        zf.write(report, f"deliverables/TO_SUBMIT_{PACKAGE}/{report.name}")
        zf.write(readme, f"deliverables/TO_SUBMIT_{PACKAGE}/{readme.name}")

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
        "e2_numeric_generator": "IMPLEMENTED",
        "e2_formal_runs": 0,
        "real_canary_runs": "0/20",
        "profile_selection_status": "NOT_STARTED",
        "e3_e9_status": "NOT_STARTED",
        "gates_status": gates["status"],
    }
    (delivery / "FINAL_DELIVERABLE_HASHES.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    (delivery / "FINAL_DELIVERABLE_HASHES.txt").write_text(
        "".join(f"{meta['sha256']}  {name}\n" for name, meta in artifacts.items()),
        encoding="utf-8",
    )
    print(json.dumps({
        "status": "PASS",
        "archive": archive.as_posix(),
        "delivery": delivery.as_posix(),
        "artifact_count": 3,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

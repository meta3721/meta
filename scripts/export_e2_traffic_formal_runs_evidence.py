#!/usr/bin/env python3
"""Export E2-TRAFFIC-FORMAL-RUNS-R1 submission ZIP."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "E2_TRAFFIC_FORMAL_RUNS_R1"
ART = ROOT / "artifacts/e2_traffic_formal_runs_r1"
OUT = ROOT / f"deliverables/TO_SUBMIT_{PACKAGE}"
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_report(stop: dict, gates: dict) -> Path:
    path = OUT / f"{PACKAGE}_REPORT.md"
    lines = [
        f"# {PACKAGE} Report",
        "",
        "## 1. Executive conclusion",
        f"- Status: `{stop.get('status')}`",
        f"- Accepted runs: {stop.get('accepted_runs')} / {stop.get('expected_runs')}",
        f"- Next: `{stop.get('next_authorized_round')}`",
        "",
        "## 2. Frozen configuration",
        f"- Profile: PROFILE-S1",
        f"- Registry SHA256: `{stop.get('registry_sha256')}`",
        f"- Runtime commit: `{stop.get('runtime_commit')}`",
        "",
        "## 3. Formal seeds",
        "- 30001–30020 inclusive",
        "",
        "## 4–9. Identity / traces / completion / retries / semantics / numerical",
        "See machine-readable audits under `artifacts/e2_traffic_formal_runs_r1/audits/`.",
        "",
        "## 10–11. Performance & paired statistics",
        "See `formal_statistics.csv` and `paired_comparisons.csv`.",
        "No superiority claim is made from means alone; paired tests and CIs are reported transparently.",
        "",
        "## 12. Runtime summary",
        f"- min/median/max seconds: {stop.get('runtime_min')} / {stop.get('runtime_median')} / {stop.get('runtime_max')}",
        "",
        "## 13–14. Tests and gates",
        json.dumps(gates.get("gates"), indent=2),
        "",
        "## 15. Known limitations",
        "- Mean CI uses fixed normal approximation (z=1.96).",
        "- Wilcoxon signed-rank uses scipy default zero omission; no family-wise correction.",
        "",
        "## 16. Next-step recommendation",
        f"- `{stop.get('next_authorized_round')}`" if stop.get("next_authorized_round") else "- Resolve blockers; do not retune.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    # Also copy into ART for evidence
    shutil.copy2(path, ART / f"{PACKAGE}_REPORT.md")
    return path


def copy_path(staging: Path, relative: str) -> None:
    src = ROOT / relative
    if not src.exists():
        return
    dst = staging / relative
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        # For runs/, copy manifests/configs/metrics but inventory checkpoints.
        if relative.endswith("runs"):
            for man in src.rglob("runtime_manifest.json"):
                rel = man.relative_to(ROOT)
                copy_path(staging, rel.as_posix())
                parent = man.parent
                for name in ("config_snapshot.json", "window_metrics.parquet", "runner_diagnostics.parquet", "final_metrics.json"):
                    p = parent / name
                    if p.is_file():
                        copy_path(staging, p.relative_to(ROOT).as_posix())
            return
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        shutil.copy2(src, dst)


def main() -> int:
    python = str(PYTHON if PYTHON.is_file() else Path(sys.executable))
    OUT.mkdir(parents=True, exist_ok=True)
    stop = json.loads((ART / "E2_TRAFFIC_FORMAL_RUNS_STOP_STATUS.json").read_text(encoding="utf-8"))
    gates = json.loads((ART / "gate_results.json").read_text(encoding="utf-8"))
    report = write_report(stop, gates)

    # Checkpoint inventory
    inv = []
    for p in (ART / "runs").rglob("checkpoints/final.pt"):
        inv.append({"path": p.relative_to(ROOT).as_posix(), "sha256": sha256(p), "bytes": p.stat().st_size})
    (ART / "checkpoint_hash_inventory.json").write_text(json.dumps(inv, indent=2) + "\n", encoding="utf-8")

    staging = OUT / "_staging"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    include = [
        "artifacts/e2_traffic_formal_runs_r1/FORMAL_RUN_CONFIG.json",
        "artifacts/e2_traffic_formal_runs_r1/SOURCE_HASHES.json",
        "artifacts/e2_traffic_formal_runs_r1/FROZEN_INPUT_IDENTITY.json",
        "artifacts/e2_traffic_formal_runs_r1/formal_results.csv",
        "artifacts/e2_traffic_formal_runs_r1/formal_results.parquet",
        "artifacts/e2_traffic_formal_runs_r1/formal_statistics.csv",
        "artifacts/e2_traffic_formal_runs_r1/formal_statistics.json",
        "artifacts/e2_traffic_formal_runs_r1/paired_comparisons.csv",
        "artifacts/e2_traffic_formal_runs_r1/formal_group_metrics.csv",
        "artifacts/e2_traffic_formal_runs_r1/formal_runtime_metrics.csv",
        "artifacts/e2_traffic_formal_runs_r1/eventtrace_manifest.csv",
        "artifacts/e2_traffic_formal_runs_r1/eventtrace_manifest.parquet",
        "artifacts/e2_traffic_formal_runs_r1/formal_run_manifest.parquet",
        "artifacts/e2_traffic_formal_runs_r1/gate_results.json",
        "artifacts/e2_traffic_formal_runs_r1/gate_diagnostics.json",
        "artifacts/e2_traffic_formal_runs_r1/checkpoint_hash_inventory.json",
        "artifacts/e2_traffic_formal_runs_r1/E2_TRAFFIC_FORMAL_RUNS_STOP_STATUS.json",
        "artifacts/e2_traffic_formal_runs_r1/audits",
        "artifacts/e2_traffic_formal_runs_r1/eventtraces",
        "artifacts/e2_traffic_formal_runs_r1/runs",
        f"artifacts/e2_traffic_formal_runs_r1/{PACKAGE}_REPORT.md",
        "logs/E2_TRAFFIC_FORMAL_RUNS_R1_EXACT_COMMANDS.jsonl",
        "logs/e2_traffic_formal_runs_unit.xml",
        "logs/e2_traffic_formal_runs_full_repository.xml",
        "logs/e2fr_pip_check.txt",
        "scripts/prepare_e2_traffic_formal_runs.py",
        "scripts/_run_e2fr_ledger_sequence.py",
        "scripts/check_e2_traffic_formal_runs_gates.py",
        "scripts/export_e2_traffic_formal_runs_evidence.py",
        "scripts/run_and_log.py",
        "src/raven_mcs/e2/traffic_formal_runs",
        "src/raven_mcs/e2/traffic_real_runner",
        "tests/unit/test_e2_traffic_formal_runs_core.py",
        "configs/frozen/e2_traffic_profiles_s1",
    ]
    for rel in include:
        copy_path(staging, rel)
    for path in (ROOT / "logs").glob("e2fr_*.stdout.log"):
        copy_path(staging, path.relative_to(ROOT).as_posix())
    for path in (ROOT / "logs").glob("e2fr_*.stderr.log"):
        copy_path(staging, path.relative_to(ROOT).as_posix())

    shutil.copy2(report, staging / report.name)
    (staging / "python-version.txt").write_text(subprocess.check_output([python, "--version"], text=True), encoding="utf-8")
    (staging / "git-HEAD.txt").write_text(subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True), encoding="utf-8")
    freeze = subprocess.run([python, "-m", "pip", "freeze"], capture_output=True, text=True)
    (staging / "environment-freeze.txt").write_text(freeze.stdout or "", encoding="utf-8")
    if (ROOT / "requirements-lock.txt").is_file():
        shutil.copy2(ROOT / "requirements-lock.txt", staging / "requirements-lock.txt")

    evidence = OUT / f"RAVEN_MCS_{PACKAGE}_EVIDENCE.zip"
    if evidence.is_file():
        evidence.unlink()
    with zipfile.ZipFile(evidence, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in staging.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(staging).as_posix())

    # Hash manifest for critical deliverables
    critical = {
        f"{PACKAGE}_REPORT.md": report,
        "formal_results.csv": ART / "formal_results.csv",
        "formal_statistics.csv": ART / "formal_statistics.csv",
        "paired_comparisons.csv": ART / "paired_comparisons.csv",
        "gate_results.json": ART / "gate_results.json",
        "EXACT_COMMANDS.jsonl": ROOT / "logs/E2_TRAFFIC_FORMAL_RUNS_R1_EXACT_COMMANDS.jsonl",
        f"RAVEN_MCS_{PACKAGE}_EVIDENCE.zip": evidence,
    }
    hash_manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "artifacts": {k: sha256(v) for k, v in critical.items() if v.is_file()},
    }
    hash_path = OUT / "FINAL_DELIVERABLE_HASHES.json"
    hash_path.write_text(json.dumps(hash_manifest, indent=2) + "\n", encoding="utf-8")
    dump_art = ART / "hash_manifest.json"
    dump_art.write_text(json.dumps(hash_manifest, indent=2) + "\n", encoding="utf-8")

    verify = {"created_utc": datetime.now(timezone.utc).isoformat(), "verified_artifact_count": 0, "hash_mismatch_count": 0, "rows": []}
    for name, digest in hash_manifest["artifacts"].items():
        path = critical[name]
        actual = sha256(path)
        ok = actual == digest
        verify["rows"].append({"artifact": name, "match": ok, "expected": digest, "actual": actual})
        verify["verified_artifact_count"] += int(ok)
        verify["hash_mismatch_count"] += int(not ok)
    verify["status"] = "PASS" if verify["hash_mismatch_count"] == 0 else "FAIL"
    (OUT / "FINAL_DELIVERABLE_HASHES_VERIFY.json").write_text(json.dumps(verify, indent=2) + "\n", encoding="utf-8")

    outer = OUT / f"TO_SUBMIT_{PACKAGE}.zip"
    if outer.is_file():
        outer.unlink()
    with zipfile.ZipFile(outer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in (
            f"{PACKAGE}_REPORT.md",
            f"RAVEN_MCS_{PACKAGE}_EVIDENCE.zip",
            "FINAL_DELIVERABLE_HASHES.json",
            "FINAL_DELIVERABLE_HASHES_VERIFY.json",
        ):
            zf.write(OUT / name, name)
        # include ART report copy name consistency
    shutil.rmtree(staging, ignore_errors=True)
    print(json.dumps({"submission_zip": outer.as_posix(), "verify": verify["status"], "stop": stop.get("status")}, indent=2))
    return 0 if verify["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

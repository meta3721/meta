#!/usr/bin/env python3
"""Immutably archive the failed E1 R1 formal weight-safety round."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARCHIVE = Path("archive/e1_r1_weight_safety_failure")
FAILED_RUN_GLOB = "E1_FORMAL_fedavg_window_26001_*"

FORMAL_DELIVERABLES = (
    "deliverables/E1_FORMAL_R1_REPORT.docx",
    "deliverables/E1_FORMAL_R1_SUBMISSION_README.txt",
    "deliverables/RAVEN_MCS_E1_FORMAL_R1_EVIDENCE.zip",
)
DIAG_DELIVERABLES = (
    "deliverables/E1_WEIGHT_SAFETY_DIAG_R1_REPORT.docx",
    "deliverables/E1_WEIGHT_SAFETY_DIAG_R1_SUBMISSION_README.txt",
    "deliverables/RAVEN_MCS_E1_WEIGHT_SAFETY_DIAG_R1_EVIDENCE.zip",
)
FAILED_RUN_FILES = ("manifest.json", "RUN_GATE_REPORT.json")

FINAL_STATUS: dict[str, Any] = {
    "E1_R1_harness": "PASS",
    "E1_R1_weight_safety": "FAIL",
    "E1_R1_performance": "NOT_EVALUATED",
    "formal_runs_completed": 1,
    "formal_runs_admitted": 0,
    "remaining_runs": "PERMANENTLY_STOPPED",
    "failure_reason": "first_stage_clip_rate_exceeds_5_percent",
    "retuning_on_R1": False,
    "superseded_by": "E1-R2-PROTOCOL-CALIBRATION-R1",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _find_failed_run(root: Path, run_dir: Path | None) -> Path:
    if run_dir is not None:
        candidate = run_dir if run_dir.is_absolute() else root / run_dir
        if not candidate.is_dir():
            raise FileNotFoundError(f"failed run directory missing: {candidate}")
        return candidate
    candidates = sorted(
        path for path in (root / "outputs/runs").glob(FAILED_RUN_GLOB)
        if path.is_dir()
    )
    matching = []
    for candidate in candidates:
        manifest_path = candidate / "manifest.json"
        gates_path = candidate / "RUN_GATE_REPORT.json"
        if not manifest_path.exists() or not gates_path.exists():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        gates = json.loads(gates_path.read_text(encoding="utf-8"))
        if (
            manifest.get("hard_gate_status") == "FAIL"
            and gates.get("all_pass") is False
        ):
            matching.append(candidate)
    if len(matching) != 1:
        raise RuntimeError(
            "expected exactly one retained failed fedavg_window/26001 run, "
            f"found {len(matching)}"
        )
    return matching[0]


def _validate_failure(run_dir: Path) -> None:
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    gates = json.loads(
        (run_dir / "RUN_GATE_REPORT.json").read_text(encoding="utf-8")
    )
    failed = {
        row.get("gate")
        for row in gates.get("gates", [])
        if row.get("status") == "FAIL"
    }
    if (
        manifest.get("method") != "fedavg_window"
        or int(manifest.get("seed", -1)) != 26001
        or manifest.get("hard_gate_status") != "FAIL"
        or failed != {"E1-RUN-G6"}
    ):
        raise RuntimeError("run identity is not the retained E1 R1 weight-safety failure")


def archive_failure(
    root: Path = ROOT,
    *,
    run_dir: Path | None = None,
    archive_dir: Path | None = None,
) -> Path:
    """Copy required evidence into a new archive without changing any source."""
    root = Path(root).resolve()
    failed_run = _find_failed_run(root, run_dir)
    _validate_failure(failed_run)
    destination = (
        Path(archive_dir)
        if archive_dir is not None
        else root / DEFAULT_ARCHIVE
    )
    if not destination.is_absolute():
        destination = root / destination
    if destination.exists():
        raise FileExistsError(f"refusing to replace immutable archive: {destination}")

    source_pairs: list[tuple[Path, Path]] = []
    for relative in (*FORMAL_DELIVERABLES, *DIAG_DELIVERABLES):
        source_pairs.append((root / relative, Path(relative)))
    run_relative = Path("failed_run") / failed_run.name
    for name in FAILED_RUN_FILES:
        source_pairs.append((failed_run / name, run_relative / name))
    missing = [str(source) for source, _ in source_pairs if not source.is_file()]
    if missing:
        raise FileNotFoundError("required E1 R1 evidence missing: " + ", ".join(missing))

    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent))
    try:
        for source, relative in source_pairs:
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        status_path = staging / "E1_R1_FINAL_STATUS.json"
        status_path.write_text(
            json.dumps(FINAL_STATUS, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        hashes = {
            path.relative_to(staging).as_posix(): _sha256(path)
            for path in sorted(staging.rglob("*"))
            if path.is_file()
        }
        (staging / "ARCHIVE_HASHES.json").write_text(
            json.dumps(
                {"algorithm": "sha256", "files": hashes},
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        staging.replace(destination)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--archive-dir", type=Path)
    args = parser.parse_args(argv)
    print(archive_failure(run_dir=args.run_dir, archive_dir=args.archive_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

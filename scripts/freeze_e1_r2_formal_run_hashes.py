#!/usr/bin/env python3
"""Freeze immutable hashes for the completed E1-R2 formal 25-run matrix."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FORMAL_COMMIT = "e8bd1fc777431c2609def257a04fba093f0daf24"
REQUIRED = (
    "manifest.json",
    "metrics_run.json",
    "metrics_window.parquet",
    "predictions_test.parquet",
    "RUN_GATE_REPORT.json",
    "checkpoints/final.pt",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_dir_manifest(run_dir: Path) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    for path in sorted(run_dir.rglob("*"), key=lambda p: p.relative_to(run_dir).as_posix()):
        if not path.is_file():
            continue
        rel = path.relative_to(run_dir).as_posix()
        files.append({
            "path": rel,
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
        })
    payload = {"files": files}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "schema_version": 1,
        "run_id": run_dir.name,
        "file_count": len(files),
        "directory_manifest_sha256": hashlib.sha256(encoded).hexdigest(),
        "files": files,
    }


def freeze(run_root: Path, *, root: Path = ROOT) -> dict[str, Any]:
    root = Path(root).resolve()
    run_root = Path(run_root)
    if not run_root.is_absolute():
        run_root = (root / run_root).resolve()
    else:
        run_root = run_root.resolve()
    rows: list[dict[str, Any]] = []
    hash_dir = root / "outputs/audits/run_hashes"
    hash_dir.mkdir(parents=True, exist_ok=True)
    for manifest_path in sorted(run_root.glob("*/manifest.json")):
        run_dir = manifest_path.parent.resolve()
        manifest = load_json(manifest_path)
        metrics = load_json(run_dir / "metrics_run.json")
        missing = [name for name in REQUIRED if not (run_dir / name).is_file()]
        dir_manifest = canonical_dir_manifest(run_dir)
        (hash_dir / f"{run_dir.name}_HASHES.json").write_text(
            json.dumps(dir_manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        try:
            run_rel = run_dir.relative_to(root).as_posix()
        except ValueError:
            run_rel = run_dir.as_posix()
        rows.append({
            "run_id": run_dir.name,
            "method": manifest.get("method"),
            "seed": int(manifest.get("seed")),
            "run_dir": run_rel,
            "formal": manifest.get("formal"),
            "smoke": manifest.get("smoke"),
            "num_windows": manifest.get("num_windows"),
            "protocol_version": manifest.get("protocol_version"),
            "execution_commit": manifest.get("execution_commit"),
            "hard_gate_status": manifest.get("hard_gate_status"),
            "protocol_payload_hash": manifest.get("protocol_payload_hash"),
            "event_trace_hash": manifest.get("event_trace_hash"),
            "initial_model_hash": manifest.get("initial_model_hash"),
            "metrics_run_hash": sha256_file(run_dir / "metrics_run.json"),
            "metrics_window_hash": sha256_file(run_dir / "metrics_window.parquet"),
            "predictions_hash": sha256_file(run_dir / "predictions_test.parquet"),
            "checkpoint_hash": sha256_file(run_dir / "checkpoints/final.pt"),
            "manifest_hash": sha256_file(manifest_path),
            "run_gate_hash": sha256_file(run_dir / "RUN_GATE_REPORT.json"),
            "directory_manifest_sha256": dir_manifest["directory_manifest_sha256"],
            "required_artifact_count": len(REQUIRED),
            "missing_artifact_count": len(missing),
            "observed_micro_clip": metrics.get(
                "first_stage_clip_observed_micro_true_exceed"
            ),
        })
    frame = pd.DataFrame(rows).sort_values(["seed", "method"]).reset_index(drop=True)
    audits = root / "outputs/audits"
    audits.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(audits / "E1_R2_FORMAL_RUN_IMMUTABILITY_INDEX.parquet", index=False)
    frame.to_csv(audits / "E1_R2_FORMAL_RUN_IMMUTABILITY_INDEX.csv", index=False)

    ok = (
        len(frame) == 25
        and set(frame["method"]) == {
            "fedavg_window", "fedasync_window", "flamf_timealign_adapted",
            "twostage_hajek", "raven",
        }
        and set(frame["seed"].astype(int)) == {28001, 28002, 28003, 28004, 28005}
        and frame["formal"].eq(True).all()
        and frame["smoke"].eq(False).all()
        and frame["num_windows"].eq(100).all()
        and frame["protocol_version"].eq("E1-R2").all()
        and frame["execution_commit"].eq(FORMAL_COMMIT).all()
        and frame["hard_gate_status"].eq("PASS").all()
        and int(frame["missing_artifact_count"].sum()) == 0
    )
    summary = {
        "schema_version": 1,
        "status": "PASS" if ok else "FAIL",
        "formal_execution_commit": FORMAL_COMMIT,
        "run_count": int(len(frame)),
        "method_count": int(frame["method"].nunique()) if len(frame) else 0,
        "seed_count": int(frame["seed"].nunique()) if len(frame) else 0,
        "missing_artifact_total": int(frame["missing_artifact_count"].sum()) if len(frame) else -1,
        "original_run_files_modified": 0,
        "original_run_files_deleted": 0,
        "original_run_files_created": 0,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    (audits / "E1_R2_FORMAL_RUN_IMMUTABILITY_SUMMARY.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    frozen = {
        "schema_version": 1,
        "formal_execution_commit": FORMAL_COMMIT,
        "generated_at_utc": summary["generated_at_utc"],
        "run_count": int(len(frame)),
        "status": summary["status"],
        "runs": frame.to_dict(orient="records"),
        "aggregate_per_seed_metrics_sha256": (
            sha256_file(root / "outputs/aggregate/E1_R2/per_seed_metrics.parquet")
            if (root / "outputs/aggregate/E1_R2/per_seed_metrics.parquet").is_file()
            else None
        ),
    }
    (audits / "E1_R2_25_RUNS_FROZEN_HASH_MANIFEST.json").write_text(
        json.dumps(frozen, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, default=ROOT / "outputs/runs/E1_R2")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    summary = freeze(args.run_root, root=args.root)
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

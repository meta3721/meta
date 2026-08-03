#!/usr/bin/env python3
"""Re-verify E1-R2 formal 25-run hashes against the frozen manifest."""
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
KEY_FIELDS = (
    ("manifest_hash", "manifest.json"),
    ("metrics_run_hash", "metrics_run.json"),
    ("metrics_window_hash", "metrics_window.parquet"),
    ("predictions_hash", "predictions_test.parquet"),
    ("checkpoint_hash", "checkpoints/final.pt"),
    ("run_gate_hash", "RUN_GATE_REPORT.json"),
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify(
    root: Path,
    *,
    output_prefix: str = "E1_R2_RESULTS_EVIDENCE_FIX_IMMUTABILITY_CHECK",
) -> dict[str, Any]:
    root = Path(root).resolve()
    frozen_path = root / "outputs/audits/E1_R2_25_RUNS_FROZEN_HASH_MANIFEST.json"
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    runs = frozen.get("runs", [])
    rows: list[dict[str, Any]] = []
    mismatches = 0
    for entry in runs:
        run_id = entry.get("run_id")
        run_dir = root / "outputs/runs/E1_R2" / str(run_id)
        if not run_dir.is_dir() and entry.get("run_dir"):
            candidate = Path(entry["run_dir"])
            run_dir = candidate if candidate.is_absolute() else root / candidate
        row: dict[str, Any] = {
            "run_id": run_id,
            "method": entry.get("method"),
            "seed": entry.get("seed"),
            "run_dir": str(run_dir),
            "exists": run_dir.is_dir(),
            "mismatch_fields": [],
        }
        if not run_dir.is_dir():
            mismatches += 1
            row["status"] = "MISSING"
            rows.append(row)
            continue
        for field, rel in KEY_FIELDS:
            expected = entry.get(field)
            path = run_dir / rel
            observed = sha256_file(path) if path.is_file() else None
            row[f"expected_{field}"] = expected
            row[f"observed_{field}"] = observed
            if expected != observed:
                mismatches += 1
                row["mismatch_fields"].append(field)
        row["status"] = "PASS" if not row["mismatch_fields"] else "FAIL"
        rows.append(row)

    frame = pd.DataFrame(rows)
    summary = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "formal_execution_commit": FORMAL_COMMIT,
        "formal_run_count": len(runs),
        "checked_run_count": len(rows),
        "hash_mismatch_count": int(mismatches),
        "original_run_files_modified": int(mismatches),
        "original_run_files_deleted": int(sum(1 for r in rows if r["status"] == "MISSING")),
        "original_run_files_created": 0,
        "status": "PASS" if mismatches == 0 and len(runs) == 25 else "FAIL",
        "frozen_manifest": frozen_path.relative_to(root).as_posix(),
    }
    audits = root / "outputs/audits"
    audits.mkdir(parents=True, exist_ok=True)
    json_path = audits / f"{output_prefix}.json"
    csv_path = audits / f"{output_prefix}.csv"
    json_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    frame.to_csv(csv_path, index=False)
    summary["outputs"] = {
        "json": json_path.relative_to(root).as_posix(),
        "csv": csv_path.relative_to(root).as_posix(),
    }
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--output-prefix",
        default="E1_R2_RESULTS_EVIDENCE_FIX_IMMUTABILITY_CHECK",
        help="Audit artifact basename without extension.",
    )
    args = parser.parse_args(argv)
    summary = verify(args.root, output_prefix=args.output_prefix)
    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

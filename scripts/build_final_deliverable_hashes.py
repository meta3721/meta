#!/usr/bin/env python3
"""Build FINAL_DELIVERABLE_HASHES.json without self-reference."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "E1_R2_RESULTS_EVIDENCE_SEAL_FIX_R1"
FORMAL_COMMIT = "e8bd1fc777431c2609def257a04fba093f0daf24"
PARENT_AUDIT = "38210700bdb6b3365930a1a4ed92a2488913d874"

ALLOWED_PREFIXES = (
    f"RAVEN_MCS_{PACKAGE}_EVIDENCE.zip",
    f"{PACKAGE}_REPORT.docx",
    f"{PACKAGE}_SUBMISSION_README.txt",
    f"RAVEN_MCS_{PACKAGE}.bundle",
    f"RAVEN_MCS_{PACKAGE}_SOURCE.tar.gz",
    "GIT_BUNDLE_VERIFY.txt",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_hashes(
    deliverables: Path,
    *,
    results_evidence_seal_commit: str,
    no_self_reference: bool = True,
) -> dict[str, Any]:
    deliverables = Path(deliverables).resolve()
    artifacts: dict[str, Any] = {}
    for path in sorted(deliverables.iterdir()):
        if not path.is_file():
            continue
        if path.name.startswith("FINAL_DELIVERABLE_HASHES"):
            if no_self_reference:
                continue
        if not any(path.name == name or path.name.endswith(name) for name in ALLOWED_PREFIXES):
            # Allow exact allowed names only.
            if path.name not in ALLOWED_PREFIXES:
                continue
        artifacts[path.name] = {
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
        }
    payload = {
        "package": PACKAGE,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "formal_execution_commit": FORMAL_COMMIT,
        "parent_results_audit_commit": PARENT_AUDIT,
        "results_evidence_seal_commit": results_evidence_seal_commit,
        "no_self_reference": no_self_reference,
        "artifacts": artifacts,
    }
    json_path = deliverables / "FINAL_DELIVERABLE_HASHES.json"
    txt_path = deliverables / "FINAL_DELIVERABLE_HASHES.txt"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    txt_path.write_text(
        "".join(f"{meta['sha256']}  {name}\n" for name, meta in artifacts.items()),
        encoding="utf-8",
    )
    # Verify closed loop against files on disk.
    mismatches = []
    for name, meta in artifacts.items():
        actual = sha256_file(deliverables / name)
        if actual != meta["sha256"]:
            mismatches.append(name)
    payload["hash_closed_loop"] = len(mismatches) == 0
    payload["hash_mismatches"] = mismatches
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--deliverables", type=Path, required=True)
    parser.add_argument("--results-evidence-seal-commit", default="UNKNOWN")
    parser.add_argument("--no-self-reference", action="store_true", default=True)
    args = parser.parse_args(argv)
    payload = build_hashes(
        args.deliverables,
        results_evidence_seal_commit=args.results_evidence_seal_commit,
        no_self_reference=args.no_self_reference,
    )
    print(json.dumps(payload, indent=2))
    return 0 if payload.get("hash_closed_loop") else 1


if __name__ == "__main__":
    raise SystemExit(main())

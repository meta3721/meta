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
DEFAULT_PACKAGE = "E1_R2_FINAL_PACKAGE_AND_PRESENTATION_FIX_R1"
FORMAL_COMMIT = "e8bd1fc777431c2609def257a04fba093f0daf24"
EVIDENCE_COMMIT = "255bd0be433059a3e1bcc3cc497297d6818845e9"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def allowed_names(package: str) -> set[str]:
    return {
        f"RAVEN_MCS_{package}_EVIDENCE.zip",
        f"{package}_REPORT.docx",
        f"{package}_SUBMISSION_README.txt",
        f"RAVEN_MCS_{package}.bundle",
        f"RAVEN_MCS_{package}_SOURCE.tar.gz",
        "GIT_BUNDLE_VERIFY.txt",
    }


def build_hashes(
    deliverables: Path,
    *,
    package: str = DEFAULT_PACKAGE,
    formal_execution_commit: str = FORMAL_COMMIT,
    results_evidence_seal_commit: str = EVIDENCE_COMMIT,
    final_package_presentation_commit: str = "UNKNOWN",
    no_self_reference: bool = True,
    exclude_self: bool = True,
) -> dict[str, Any]:
    deliverables = Path(deliverables).resolve()
    allowed = allowed_names(package)
    artifacts: dict[str, Any] = {}
    for path in sorted(deliverables.iterdir()):
        if not path.is_file():
            continue
        if path.name.startswith("FINAL_DELIVERABLE_HASHES") and (no_self_reference or exclude_self):
            continue
        if path.name not in allowed:
            continue
        artifacts[path.name] = {
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
        }
    payload = {
        "package": package,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "formal_execution_commit": formal_execution_commit,
        "results_evidence_seal_commit": results_evidence_seal_commit,
        "final_package_presentation_commit": final_package_presentation_commit,
        "no_self_reference": True,
        "artifacts": artifacts,
    }
    json_path = deliverables / "FINAL_DELIVERABLE_HASHES.json"
    txt_path = deliverables / "FINAL_DELIVERABLE_HASHES.txt"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    txt_path.write_text(
        "".join(f"{meta['sha256']}  {name}\n" for name, meta in artifacts.items()),
        encoding="utf-8",
    )
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
    parser.add_argument("--package", default=DEFAULT_PACKAGE)
    parser.add_argument("--results-evidence-seal-commit", default=EVIDENCE_COMMIT)
    parser.add_argument("--final-package-presentation-commit", default="UNKNOWN")
    parser.add_argument("--no-self-reference", action="store_true", default=True)
    parser.add_argument("--exclude-self", action="store_true", default=True)
    args = parser.parse_args(argv)
    payload = build_hashes(
        args.deliverables,
        package=args.package,
        results_evidence_seal_commit=args.results_evidence_seal_commit,
        final_package_presentation_commit=args.final_package_presentation_commit,
        no_self_reference=args.no_self_reference,
        exclude_self=args.exclude_self,
    )
    print(json.dumps(payload, indent=2))
    return 0 if payload.get("hash_closed_loop") else 1


if __name__ == "__main__":
    raise SystemExit(main())

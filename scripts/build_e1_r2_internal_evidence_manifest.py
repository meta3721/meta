#!/usr/bin/env python3
"""Build and verify INTERNAL_EVIDENCE_MANIFEST for self-contained ZIP contents."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "E1_R2_FINAL_PACKAGE_AND_PRESENTATION_FIX_R1"

EXCLUDE_NAMES = {
    "INTERNAL_EVIDENCE_MANIFEST.json",
    "INTERNAL_EVIDENCE_MANIFEST_VERIFY.json",
    "FINAL_DELIVERABLE_HASHES.json",
    "FINAL_DELIVERABLE_HASHES.txt",
}

ROLE_HINTS = (
    ("outputs/audits/", "audit"),
    ("outputs/statistics/", "statistics"),
    ("outputs/gates/", "gates"),
    ("outputs/paper/", "paper"),
    ("scripts/", "script"),
    ("tests/", "test"),
    ("logs/", "log"),
    ("docs/", "docs"),
    ("configs/", "config"),
    ("ISSUES.md", "issues"),
    ("SELF_CONTAINED_REPLAY", "replay"),
    ("REPORT.docx", "report_copy"),
    ("SUBMISSION_README", "readme_copy"),
    ("GIT_BUNDLE_VERIFY", "bundle_verify_copy"),
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _role(rel: str) -> str:
    for prefix, role in ROLE_HINTS:
        if prefix in rel or rel.endswith(prefix):
            return role
    return "other"


def build_manifest(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    files: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.name in EXCLUDE_NAMES:
            continue
        rel = path.relative_to(root).as_posix()
        files.append({
            "relative_path": rel,
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
            "role": _role(rel),
            "required": True,
        })
    payload = {
        "schema_version": 1,
        "package": PACKAGE,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "internal_file_count": len(files),
        "files": files,
    }
    out = root / "INTERNAL_EVIDENCE_MANIFEST.json"
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def verify_manifest(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    manifest_path = root / "INTERNAL_EVIDENCE_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    missing = 0
    mismatches = 0
    verified = 0
    details: list[dict[str, Any]] = []
    for entry in manifest.get("files", []):
        rel = entry["relative_path"]
        path = root / rel
        if not path.is_file():
            missing += 1
            details.append({"relative_path": rel, "status": "MISSING"})
            continue
        actual = sha256_file(path)
        if actual != entry.get("sha256"):
            mismatches += 1
            details.append({"relative_path": rel, "status": "HASH_MISMATCH"})
            continue
        verified += 1
    status = "PASS" if missing == 0 and mismatches == 0 else "FAIL"
    result = {
        "schema_version": 1,
        "package": PACKAGE,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "internal_file_count": int(manifest.get("internal_file_count", 0)),
        "verified_file_count": verified,
        "missing_file_count": missing,
        "hash_mismatch_count": mismatches,
        "status": status,
        "details": details[:50],
    }
    (root / "INTERNAL_EVIDENCE_MANIFEST_VERIFY.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args(argv)
    if args.verify_only:
        result = verify_manifest(args.root)
    else:
        build_manifest(args.root)
        result = verify_manifest(args.root)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

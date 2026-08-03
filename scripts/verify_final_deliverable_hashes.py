#!/usr/bin/env python3
"""Independently verify FINAL_DELIVERABLE_HASHES.json against delivery artifacts."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify(manifest: Path, delivery_root: Path) -> dict[str, Any]:
    manifest = Path(manifest)
    delivery_root = Path(delivery_root)
    if not manifest.is_absolute():
        manifest = delivery_root / manifest
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    artifacts = payload.get("artifacts", {})
    self_reference = any(name.startswith("FINAL_DELIVERABLE_HASHES") for name in artifacts)
    verified = []
    missing = []
    mismatches = []
    for name, meta in artifacts.items():
        path = delivery_root / name
        if not path.is_file():
            missing.append(name)
            continue
        actual = sha256_file(path)
        if actual != meta.get("sha256"):
            mismatches.append({"name": name, "expected": meta.get("sha256"), "actual": actual})
        else:
            verified.append(name)
    status = (
        "PASS"
        if not self_reference and not missing and not mismatches and len(artifacts) > 0
        else "FAIL"
    )
    result = {
        "schema_version": 1,
        "status": status,
        "manifest": manifest.as_posix(),
        "delivery_root": delivery_root.as_posix(),
        "artifact_count": len(artifacts),
        "verified_count": len(verified),
        "missing_count": len(missing),
        "hash_mismatch_count": len(mismatches),
        "self_reference": self_reference,
        "no_self_reference": payload.get("no_self_reference") is True and not self_reference,
        "hash_closed_loop": payload.get("hash_closed_loop") is True and not mismatches,
        "verified": verified,
        "missing": missing,
        "mismatches": mismatches,
        "formal_execution_commit": payload.get("formal_execution_commit"),
        "final_report_synchronization_commit": payload.get("final_report_synchronization_commit"),
        "package_fix_commit": payload.get("package_fix_commit"),
    }
    out = delivery_root / "FINAL_DELIVERABLE_HASHES_VERIFY.json"
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=Path("FINAL_DELIVERABLE_HASHES.json"))
    parser.add_argument("--delivery-root", type=Path, required=True)
    args = parser.parse_args(argv)
    result = verify(args.manifest, args.delivery_root)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""SHA-256 verifier for RAVEN_MCS_PUBLIC_REPRO_R1."""
from __future__ import annotations

import csv
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    manifest = ROOT / "MANIFEST.csv"
    if not manifest.is_file():
        print("MANIFEST.csv missing", file=sys.stderr)
        return 2
    n = 0
    bad = 0
    with manifest.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            rel = row["path"].replace("\\", "/")
            path = ROOT / rel
            n += 1
            if not path.is_file():
                print(f"MISSING {rel}")
                bad += 1
                continue
            got = sha256_file(path)
            if got != row["sha256"]:
                print(f"HASH_MISMATCH {rel}")
                bad += 1
    print(f"checked={n} mismatches={bad}")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Audit an already prepared dataset and verify its frozen hashes."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from raven_mcs.data.audit import audit_processed_bundle, write_audit_report
from raven_mcs.data.manifest import verify_data_manifest
from raven_mcs.data.pipeline import dataset_paths, load_processed_bundle
from raven_mcs.utils.cli import add_common_run_flags


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    add_common_run_flags(parser)
    parser.set_defaults(output_dir=Path("outputs/data-audits"))
    args = parser.parse_args(argv)
    paths = dataset_paths(args.data_root, args.dataset)
    report_path = args.output_dir / f"{args.dataset}_audit.json"
    if args.dry_run:
        print(f"would_audit={paths.processed}")
        print(f"would_write={report_path}")
        return 0

    bundle = load_processed_bundle(paths)
    audit = audit_processed_bundle(bundle)
    if paths.manifest.exists():
        hash_errors = verify_data_manifest(
            paths.manifest,
            raw_root=paths.raw,
            interim_root=paths.interim,
            processed_root=paths.processed,
        )
        for error in hash_errors:
            audit.fail(error)
    else:
        audit.warnings.append("Dataset is not frozen: manifest missing")
    write_audit_report(audit, report_path)
    print(f"dataset={args.dataset}")
    print(f"passed={audit.passed}")
    print(f"report={report_path}")
    if audit.errors:
        for error in audit.errors:
            print(f"ERROR: {error}")
    return 0 if audit.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

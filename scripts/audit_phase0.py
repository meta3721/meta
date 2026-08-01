#!/usr/bin/env python3
"""Run and persist the constitution-required Phase 0 repository scans."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from raven_mcs.experiments.phase0_audit import run_phase0_audit
from raven_mcs.utils.cli import add_common_run_flags
from raven_mcs.utils.manifest import utc_now_iso
from raven_mcs.utils.serialization import dump_json, load_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_run_flags(parser)
    parser.set_defaults(output_dir=Path("docs/audits"))
    args = parser.parse_args(argv)
    if args.device != "cpu":
        parser.error("Phase 0 audit is CPU-only; use --device cpu")

    report_path = args.output_dir / "phase0_audit.json"
    if report_path.exists() and not args.dry_run:
        if not args.resume:
            raise FileExistsError(
                f"Audit report exists; refusing overwrite: {report_path}"
            )
        report = load_json(report_path)
        print(f"resumed_report={report_path}")
        print(f"audit_version={report.get('audit_version')}")
        return 0

    report = run_phase0_audit(_ROOT, max_workers=args.max_workers)
    report["generated_at"] = utc_now_iso()
    report["invocation"] = {
        "dry_run": args.dry_run,
        "resume": args.resume,
        "max_workers": args.max_workers,
        "fail_fast": args.fail_fast,
        "device": args.device,
        "seed": args.seed,
        "output_dir": str(args.output_dir),
    }
    if args.dry_run:
        print(f"scan_files={len(report['scan_files'])}")
        print(f"would_write={report_path}")
        return 0

    dump_json(report, report_path)
    print(f"report={report_path}")
    print(f"tree_files={len(report['tree_files'])}")
    print(f"scan_files={len(report['scan_files'])}")
    print(f"main_experiment_status={report['main_experiment_status']}")
    if report["read_errors"]:
        print(f"read_errors={len(report['read_errors'])}")
        return 1 if args.fail_fast else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

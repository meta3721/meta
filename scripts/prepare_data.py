#!/usr/bin/env python3
"""Prepare and optionally freeze one dataset into canonical Parquet tables."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from raven_mcs.data.pipeline import prepare_dataset
from raven_mcs.utils.cli import add_common_run_flags


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True)
    parser.add_argument(
        "--freeze", action="store_true", help="Write immutable stage hashes."
    )
    add_common_run_flags(parser)
    parser.set_defaults(output_dir=Path("data"))
    args = parser.parse_args(argv)
    seed = 26001 if args.seed is None else args.seed
    result = prepare_dataset(
        args.dataset,
        data_root=args.output_dir,
        seed=seed,
        freeze=args.freeze,
        resume=args.resume,
        dry_run=args.dry_run,
    )
    print(f"dataset={result.paths.dataset}")
    print(f"processed={result.paths.processed}")
    print(f"dry_run={result.dry_run} resumed={result.resumed}")
    print(f"audit_passed={result.audit_passed}")
    print(f"data_hash={result.data_hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

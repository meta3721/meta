#!/usr/bin/env python3
"""Download official raw datasets with provenance and checksum verification."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from raven_mcs.data.download import download_dataset
from raven_mcs.utils.cli import add_common_run_flags


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--data-root", type=Path, default=None)
    add_common_run_flags(parser)
    parser.set_defaults(output_dir=Path("data"))
    args = parser.parse_args(argv)
    data_root = args.data_root or args.output_dir
    result = download_dataset(
        args.dataset,
        data_root=data_root,
        resume=args.resume or True,
        dry_run=args.dry_run,
    )
    print(f"dataset={result.dataset}")
    print(f"raw_root={result.raw_root}")
    print(f"dry_run={result.dry_run} resumed={result.resumed} ok={result.ok}")
    for item in result.files:
        print(
            f"file={item.get('filename')} status={item.get('status')} "
            f"md5={item.get('md5')} bytes={item.get('size_bytes')}"
        )
    for error in result.errors:
        print(f"ERROR: {error}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

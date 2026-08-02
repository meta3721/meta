#!/usr/bin/env python3
"""Independently recompute EventTrace parquet and identity hashes."""
from __future__ import annotations

import argparse
from pathlib import Path

from raven_mcs.simulation.event_trace import load_event_trace
from raven_mcs.utils.hashing import sha256_file
from raven_mcs.utils.serialization import load_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("trace_dirs", nargs="+", type=Path)
    args = parser.parse_args()
    for trace_dir in args.trace_dirs:
        manifest = load_json(trace_dir / "event_trace_manifest.json")
        trace, identity = load_event_trace(trace_dir)
        trace.validate()
        events_hash = sha256_file(trace_dir / "events.parquet")
        if events_hash != manifest["events_sha256"]:
            raise RuntimeError(f"events hash mismatch: {trace_dir}")
        if identity["trace_hash"] != manifest["event_trace_hash"]:
            raise RuntimeError(f"trace hash mismatch: {trace_dir}")
        print(f"{trace_dir}: PASS {identity['trace_hash']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

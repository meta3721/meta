#!/usr/bin/env python3
"""Re-audit all frozen official E1 EventTraces."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from raven_mcs.experiments.e1_entry import E1_SEEDS, audit_e1_trace, sensorscope_dataset
from raven_mcs.simulation.event_trace import load_event_trace, verify_event_trace_hash
from raven_mcs.utils.serialization import dump_json, load_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", default="E1_balanced")
    parser.add_argument("--trace-root", type=Path, default=ROOT / "outputs/event_traces")
    args = parser.parse_args(argv)
    dataset = sensorscope_dataset(ROOT)
    all_pass = True
    for seed in E1_SEEDS:
        trace_dir = args.trace_root / f"e1_balanced_seed{seed}"
        manifest = load_json(trace_dir / "event_trace_manifest.json")
        hash_errors = verify_event_trace_hash(
            trace_dir, manifest["event_trace_hash"],
        )
        trace, _ = load_event_trace(trace_dir)
        audit = audit_e1_trace(trace, dataset)
        audit["hash_errors"] = hash_errors
        audit["hard_gate_pass"] = bool(audit["hard_gate_pass"] and not hash_errors)
        dump_json(audit, ROOT / f"outputs/audits/e1_eventtrace_audit_seed{seed}.json")
        all_pass &= audit["hard_gate_pass"]
        print(f"seed={seed}: {'PASS' if audit['hard_gate_pass'] else 'FAIL'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Audit E1-R4 attempted-set and q-training population semantics."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", default="E1_balanced")
    parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    paths = sorted((root / "outputs/entry_r4_smoke").rglob(
        "q_attempt_diagnostics.parquet"
    ))
    if not paths:
        raise RuntimeError("run R4 smoke before q-attempt audit")
    frames = []
    for path in paths[-5:]:
        frame = pd.read_parquet(path)
        frame["run_path"] = str(path.parent.relative_to(root))
        frames.append(frame)
    audit = pd.concat(frames, ignore_index=True)
    attempts = audit["attempted"].astype(bool)
    included = audit["included_in_q_training"].astype(bool)
    failed = attempts & (audit["U"].astype(int) == 0)
    summary = {
        "total_clients": int(len(audit)),
        "total_attempts": int(attempts.sum()),
        "total_failed_attempts": int(failed.sum()),
        "total_successful_attempts": int((attempts & ~failed).sum()),
        "total_nonattempts": int((~attempts).sum()),
        "q_history_rows": int(included.sum()),
        "nonattempt_leakage_count": int((~attempts & included).sum()),
        "failed_attempt_omission_count": int((failed & ~included).sum()),
    }
    if (
        summary["q_history_rows"] != summary["total_attempts"]
        or summary["nonattempt_leakage_count"]
        or summary["failed_attempt_omission_count"]
    ):
        raise RuntimeError("q attempt semantics audit failed")
    out = root / "outputs/audits"
    out.mkdir(parents=True, exist_ok=True)
    audit.to_parquet(out / "e1_r4_q_attempt_semantics.parquet", index=False)
    (out / "e1_r4_q_attempt_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

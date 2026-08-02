#!/usr/bin/env python3
"""Audit zero arrival contribution outside frozen E1 support."""
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
        "arrival_support_diagnostics.parquet"
    ))
    if not paths:
        raise RuntimeError("run R4 smoke before arrival-support audit")
    frames = []
    for path in paths[-5:]:
        frame = pd.read_parquet(path)
        frame["run_path"] = str(path.parent.relative_to(root))
        frames.append(frame)
    audit = pd.concat(frames, ignore_index=True)
    unsupported = audit["support_mask"].astype(int) == 0
    summary = {
        "row_count": int(len(audit)),
        "unsupported_pair_rows": int(unsupported.sum()),
        "unsupported_positive_contribution_count": int(
            audit["unsupported_positive_contribution"].sum()
        ),
        "unsupported_contribution_sum": float(
            audit.loc[unsupported, "contribution"].sum()
        ),
    }
    if summary["unsupported_positive_contribution_count"] or abs(
        summary["unsupported_contribution_sum"]
    ) > 0.0:
        raise RuntimeError("arrival-support audit failed")
    out = root / "outputs/audits"
    out.mkdir(parents=True, exist_ok=True)
    audit.to_parquet(out / "e1_r4_arrival_support_audit.parquet", index=False)
    (out / "e1_r4_arrival_support_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

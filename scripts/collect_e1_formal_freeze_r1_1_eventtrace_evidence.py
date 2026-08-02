#!/usr/bin/env python3
"""Collect and independently hash frozen E1 EventTrace evidence."""
from __future__ import annotations

import csv
import shutil
from pathlib import Path

import pandas as pd

from raven_mcs.utils.hashing import sha256_file
from raven_mcs.utils.serialization import dump_json, load_json

SEEDS = (26001, 26002, 26003, 26004, 26005)
COPY_NAMES = ("event_trace_manifest.json", "audit.json", "trace_identity.json",
              "generation_config.yaml", "metadata.json")
COPY_EVENTS_UNDER_BYTES = 50 * 1024 * 1024


def event_row(path: Path, manifest: dict) -> dict:
    events = path / "events.parquet"
    if not events.exists():
        return {"events_exists": False, "events_sha256": None, "size_bytes": None,
                "row_count": None, "copied": False}
    size = events.stat().st_size
    row = {"events_exists": True, "events_sha256": sha256_file(events),
           "size_bytes": size, "row_count": int(len(pd.read_parquet(events))),
           "copied": size < COPY_EVENTS_UNDER_BYTES,
           "manifest_events_sha256": manifest.get("events_sha256"),
           "hash_match": sha256_file(events) == manifest.get("events_sha256")}
    return row


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    traces = root / "outputs/event_traces"
    evidence = root / "evidence/eventtrace"
    evidence.mkdir(parents=True, exist_ok=True)
    records, evolution = [], []
    for seed in SEEDS:
        source = traces / f"e1_balanced_seed{seed}"
        target = evidence / f"seed_{seed}"
        target.mkdir(parents=True, exist_ok=True)
        result = {"seed": seed, "source": str(source.relative_to(root)), "available": source.exists()}
        if source.exists() and (source / "event_trace_manifest.json").exists():
            manifest = load_json(source / "event_trace_manifest.json")
            for name in COPY_NAMES:
                if (source / name).exists():
                    shutil.copy2(source / name, target / name)
            event = event_row(source, manifest)
            if event["copied"]:
                shutil.copy2(source / "events.parquet", target / "events.parquet")
            result.update({"manifest": manifest, **event,
                           "event_trace_hash": manifest.get("event_trace_hash")})
            prior = next(iter(sorted(traces.glob(f"sensorscope_balanced_seed{seed}*"))), None)
            prior_manifest = (load_json(prior / "event_trace_manifest.json")
                              if prior and (prior / "event_trace_manifest.json").exists() else {})
            evolution.append({"seed": seed, "current_path": str(source.relative_to(root)),
                              "current_event_trace_hash": manifest.get("event_trace_hash"),
                              "prior_r3_path": str(prior.relative_to(root)) if prior else None,
                              "prior_event_trace_hash": prior_manifest.get("event_trace_hash"),
                              "comparison": (
                                  "PRIOR_MANIFEST_UNAVAILABLE" if not prior_manifest else
                                  "MATCH" if prior_manifest.get("event_trace_hash") ==
                                  manifest.get("event_trace_hash") else "DIFFERENT"
                              )})
        else:
            result["reason"] = "trace directory or event_trace_manifest.json unavailable"
            evolution.append({"seed": seed, "current_path": str(source.relative_to(root)),
                              "current_event_trace_hash": None, "prior_r3_path": None,
                              "prior_event_trace_hash": None, "comparison": "CURRENT_UNAVAILABLE"})
        records.append(result)
    with (evidence / "EVENTTRACE_HASH_EVOLUTION.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(evolution[0]))
        writer.writeheader()
        writer.writerows(evolution)
    summary = {"seeds": records,
               "all_available": all(row["available"] for row in records),
               "all_manifest_event_hashes_match": all(
                   row.get("hash_match", False) for row in records if row["available"]),
               "verification": "events.parquet SHA-256 recomputed with sha256_file; "
                               "event_trace_hash compared from supplied manifests."}
    dump_json(summary, evidence / "EVENTTRACE_RECOMPUTE_SUMMARY.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

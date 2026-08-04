#!/usr/bin/env python3
"""Build fixed synthetic client-window topology for usable-arrival tests."""
from __future__ import annotations

import json
from pathlib import Path

from raven_mcs.e2.identity import load_e1_head_tail_mapping, load_e1_supported_test_units
from raven_mcs.utils.hashing import sha256_json
from raven_mcs.utils.serialization import dump_json

ROOT = Path(__file__).resolve().parents[1]


def _take(ids: list[str], start: int, count: int) -> list[str]:
    if len(ids) < start + count:
        raise RuntimeError(f"need {count} units from {start}, have {len(ids)}")
    return ids[start:start + count]


def _partition_windows(
    unit_ids: list[str],
    *,
    client_prefix: str,
    kind: str,
    chunk: int,
) -> list[dict]:
    windows = []
    for offset in range(0, len(unit_ids), chunk):
        part = unit_ids[offset:offset + chunk]
        idx = offset // chunk
        windows.append({
            "client_id": f"{client_prefix}_{idx}",
            "window_id": f"w_{kind}_{idx}",
            "kind": kind,
            "unit_ids": part,
            "attempt_eligible": True,
        })
    return windows


def main() -> int:
    mapping = load_e1_head_tail_mapping(ROOT)
    supported = load_e1_supported_test_units(ROOT)["unit_id"].astype(str).tolist()
    supported_set = set(supported)
    head = [
        u for u in mapping.loc[mapping["role"] == "head", "unit_id"].astype(str)
        if u in supported_set
    ]
    tail = [
        u for u in mapping.loc[mapping["role"] == "tail", "unit_id"].astype(str)
        if u in supported_set
    ]
    neutral = [
        u for u in mapping.loc[mapping["role"] == "neutral", "unit_id"].astype(str)
        if u in supported_set
    ]

    # Directional specialty windows (at least two of each required kind).
    windows: list[dict] = [
        {
            "client_id": "c_head_a", "window_id": "w_head_0", "kind": "head_heavy",
            "unit_ids": _take(head, 0, 8) + _take(tail, 0, 1) + _take(neutral, 0, 1),
            "attempt_eligible": True,
        },
        {
            "client_id": "c_head_b", "window_id": "w_head_1", "kind": "head_heavy",
            "unit_ids": _take(head, 8, 8) + _take(tail, 1, 1) + _take(neutral, 1, 1),
            "attempt_eligible": True,
        },
        {
            "client_id": "c_tail_a", "window_id": "w_tail_0", "kind": "tail_heavy",
            "unit_ids": _take(tail, 2, 8) + _take(head, 16, 1) + _take(neutral, 2, 1),
            "attempt_eligible": True,
        },
        {
            "client_id": "c_tail_b", "window_id": "w_tail_1", "kind": "tail_heavy",
            "unit_ids": _take(tail, 10, 8) + _take(head, 17, 1) + _take(neutral, 3, 1),
            "attempt_eligible": True,
        },
        {
            "client_id": "c_mix_a", "window_id": "w_mix_0", "kind": "mixed",
            "unit_ids": _take(head, 18, 4) + _take(tail, 18, 4) + _take(neutral, 4, 2),
            "attempt_eligible": True,
        },
        {
            "client_id": "c_mix_b", "window_id": "w_mix_1", "kind": "mixed",
            "unit_ids": _take(head, 22, 4) + _take(tail, 22, 4) + _take(neutral, 6, 2),
            "attempt_eligible": True,
        },
        {
            "client_id": "c_neu_a", "window_id": "w_neu_0", "kind": "neutral_heavy",
            "unit_ids": _take(neutral, 10, 8) + _take(head, 26, 1) + _take(tail, 26, 1),
            "attempt_eligible": True,
        },
        {
            "client_id": "c_neu_b", "window_id": "w_neu_1", "kind": "neutral_heavy",
            "unit_ids": _take(neutral, 20, 8) + _take(head, 27, 1) + _take(tail, 27, 1),
            "attempt_eligible": True,
        },
    ]

    # Role-pure coverage partitions: every supported atom appears; z ≈ ±1 or 0.
    windows.extend(_partition_windows(head, client_prefix="c_cov_head", kind="coverage_head", chunk=50))
    windows.extend(_partition_windows(tail, client_prefix="c_cov_tail", kind="coverage_tail", chunk=50))
    windows.extend(
        _partition_windows(neutral, client_prefix="c_cov_neu", kind="coverage_neutral", chunk=50)
    )

    kind_counts: dict[str, int] = {}
    for window in windows:
        kind = str(window["kind"])
        kind_counts[kind] = kind_counts.get(kind, 0) + 1
        n = len(window["unit_ids"])
        # Specialty/mixed windows get larger weights so they matter vs coverage.
        base = 5.0 if kind in {"head_heavy", "tail_heavy", "mixed", "neutral_heavy"} else 1.0
        window["opportunity_weights"] = [
            base + 0.1 * ((i + len(window["window_id"])) % 5) for i in range(n)
        ]
        window["pre_outcome_features"] = {"source": "synthetic_fixture"}
        window.pop("kind")

    unit_count = len({u for w in windows for u in w["unit_ids"]})
    if unit_count != len(supported_set):
        raise RuntimeError(
            f"topology must cover all supported units: {unit_count} != {len(supported_set)}"
        )
    payload = {
        "protocol": "E2-USABLE-ARRIVAL-INTEGRATION-AND-IDENTITY-REPAIR-R1",
        "description": "Fixed synthetic client-window topology; no seed execution",
        "windows": windows,
    }
    fixture_hash = sha256_json(payload)
    out = ROOT / "tests/fixtures/e2_usable_topology.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "fixture_hash": fixture_hash,
        "window_count": len(windows),
        "unit_count": unit_count,
        "head_heavy_count": kind_counts.get("head_heavy", 0),
        "tail_heavy_count": kind_counts.get("tail_heavy", 0),
        "mixed_count": kind_counts.get("mixed", 0),
        "neutral_count": kind_counts.get("neutral_heavy", 0),
        "coverage_head_count": kind_counts.get("coverage_head", 0),
        "coverage_tail_count": kind_counts.get("coverage_tail", 0),
        "coverage_neutral_count": kind_counts.get("coverage_neutral", 0),
    }
    dump_json(manifest, ROOT / "tests/fixtures/e2_usable_topology_manifest.json")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Shared per-seed 300-window client-window topology over E1 supported test units."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from raven_mcs.e2.identity import (
    load_e1_atomic_target_weights,
    load_e1_head_tail_mapping,
    load_e1_supported_test_units,
)
from raven_mcs.utils.hashing import sha256_json

ROOT = Path(__file__).resolve().parents[4]
NUM_WINDOWS = 300
BLOCK_WINDOWS = 100
CLIENTS_PER_WINDOW = 8


def _take_cycle(ids: list[str], start: int, count: int) -> list[str]:
    if not ids:
        raise RuntimeError("empty unit pool")
    out: list[str] = []
    seen: set[str] = set()
    cursor = start
    guard = 0
    while len(out) < min(count, len(ids)) and guard < len(ids) * 3:
        unit_id = ids[cursor % len(ids)]
        cursor += 1
        guard += 1
        if unit_id in seen:
            continue
        seen.add(unit_id)
        out.append(unit_id)
    return out


def _specialty_template(
    kind: str,
    head: list[str],
    tail: list[str],
    neutral: list[str],
    idx: int,
) -> dict[str, Any]:
    if kind == "head_heavy":
        unit_ids = (
            _take_cycle(head, 8 * idx, 8)
            + _take_cycle(tail, idx, 1)
            + _take_cycle(neutral, idx, 1)
        )
        base = 5.0
    elif kind == "tail_heavy":
        unit_ids = (
            _take_cycle(tail, 8 * idx, 8)
            + _take_cycle(head, idx, 1)
            + _take_cycle(neutral, idx + 3, 1)
        )
        base = 5.0
    elif kind == "mixed":
        unit_ids = (
            _take_cycle(head, 4 * idx, 4)
            + _take_cycle(tail, 4 * idx, 4)
            + _take_cycle(neutral, 4 * idx, 2)
        )
        base = 5.0
    else:  # neutral_heavy
        unit_ids = (
            _take_cycle(neutral, 8 * idx, 8)
            + _take_cycle(head, 2 * idx, 1)
            + _take_cycle(tail, 2 * idx, 1)
        )
        base = 5.0
    return {"kind": kind, "unit_ids": list(dict.fromkeys(unit_ids)), "base_weight": base}


def _coverage_templates(
    head: list[str],
    tail: list[str],
    neutral: list[str],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for pool, kind in (
        (head, "coverage_head"),
        (tail, "coverage_tail"),
        (neutral, "coverage_neutral"),
    ):
        chunk = 50
        for offset in range(0, len(pool), chunk):
            part = pool[offset:offset + chunk]
            if not part:
                continue
            out.append({"kind": kind, "unit_ids": part, "base_weight": 1.0})
    return out


def _build_block(
    *,
    seed: int,
    head: list[str],
    tail: list[str],
    neutral: list[str],
    weight_map: dict[str, float],
    block_windows: int = BLOCK_WINDOWS,
    clients_per_window: int = CLIENTS_PER_WINDOW,
) -> list[list[dict[str, Any]]]:
    """Return list[window][client_slot] templates for one 100-window block."""
    rng = np.random.default_rng(int(seed) ^ 0x544F504F)
    head_p = list(rng.permutation(head))
    tail_p = list(rng.permutation(tail))
    neu_p = list(rng.permutation(neutral))

    coverage = _coverage_templates(head_p, tail_p, neu_p)
    specialty_kinds = (
        ["head_heavy"] * 20
        + ["tail_heavy"] * 20
        + ["mixed"] * 12
        + ["neutral_heavy"] * 8
    )
    specialty = [
        _specialty_template(kind, head_p, tail_p, neu_p, i)
        for i, kind in enumerate(specialty_kinds)
    ]

    # Ensure every window has a mix: slot0 specialty (or cycle), remaining slots
    # drawn from coverage+specialty so coverage appears every window-prefix.
    block: list[list[dict[str, Any]]] = []
    cov_cycle = 0
    for wid in range(block_windows):
        slots: list[dict[str, Any]] = []
        slots.append(specialty[wid % len(specialty)])
        for slot in range(1, clients_per_window):
            if coverage:
                slots.append(coverage[cov_cycle % len(coverage)])
                cov_cycle += 1
            else:
                slots.append(specialty[(wid + slot) % len(specialty)])
        # Materialize weights.
        materialized = []
        for local_slot, template in enumerate(slots):
            unit_ids = list(dict.fromkeys(template["unit_ids"]))
            base = float(template["base_weight"])
            weights = [
                base * weight_map[u] * 1000.0 + 0.1 * ((i + wid + local_slot) % 5)
                for i, u in enumerate(unit_ids)
            ]
            materialized.append({
                "kind": template["kind"],
                "unit_ids": unit_ids,
                "opportunity_weights": weights,
                "client_slot": local_slot,
            })
        block.append(materialized)

    covered = {u for window in block for slot in window for u in slot["unit_ids"]}
    supported = set(head) | set(tail) | set(neutral)
    missing = sorted(supported - covered)
    if missing:
        raise RuntimeError(f"topology block missing {len(missing)} supported units")
    return block


def build_seed_topology(
    seed: int,
    *,
    root: Path | None = None,
    num_windows: int = NUM_WINDOWS,
    schedule_uniforms: np.ndarray | None = None,
) -> dict[str, Any]:
    """Build a 300-window mother topology as three nested-stable 100-window blocks.

    Each window_id has multiple client risk-sets so Bernoulli rate estimates are
    stable enough for G2 bands, while 100/200/300 remain nested prefixes by window_id.
    """
    del schedule_uniforms
    root = Path(root or ROOT)
    if int(num_windows) != NUM_WINDOWS:
        raise ValueError(f"this round requires num_windows={NUM_WINDOWS}")
    mapping = load_e1_head_tail_mapping(root)
    supported = set(
        load_e1_supported_test_units(root)["unit_id"].astype(str).tolist()
    )
    atomic = load_e1_atomic_target_weights(root)
    weight_map = {
        str(r.unit_id): float(r.target_weight)
        for r in atomic.itertuples(index=False)
    }
    head = [
        u for u in mapping.loc[mapping["role"] == "head", "unit_id"].astype(str)
        if u in supported
    ]
    tail = [
        u for u in mapping.loc[mapping["role"] == "tail", "unit_id"].astype(str)
        if u in supported
    ]
    neutral = [
        u for u in mapping.loc[mapping["role"] == "neutral", "unit_id"].astype(str)
        if u in supported
    ]
    block = _build_block(
        seed=int(seed),
        head=head,
        tail=tail,
        neutral=neutral,
        weight_map=weight_map,
    )

    windows: list[dict[str, Any]] = []
    clients: set[str] = set()
    tiles = int(num_windows) // BLOCK_WINDOWS
    for tile in range(tiles):
        for local_id, slots in enumerate(block):
            window_id = tile * BLOCK_WINDOWS + local_id
            for slot in slots:
                client_id = f"client-{slot['kind']}-{slot['client_slot']:02d}"
                clients.add(client_id)
                windows.append({
                    "client_id": client_id,
                    "window_id": str(window_id),
                    "unit_ids": list(slot["unit_ids"]),
                    "opportunity_weights": list(slot["opportunity_weights"]),
                    "attempt_eligible": True,
                    "pre_outcome_features": {
                        "source": "e2_distribution_seed_topology",
                        "seed": int(seed),
                        "kind": slot["kind"],
                        "tile": tile,
                        "block_local_id": local_id,
                        "client_slot": slot["client_slot"],
                    },
                })

    clients_sorted = sorted(clients)
    payload = {
        "seed": int(seed),
        "num_windows": int(num_windows),
        "num_clients": len(clients_sorted),
        "window_count": len(windows),
        "block_windows": BLOCK_WINDOWS,
        "clients_per_window": CLIENTS_PER_WINDOW,
        "clients": clients_sorted,
    }
    return {
        "seed": int(seed),
        "windows": windows,
        "topology_hash": sha256_json({
            "seed": int(seed),
            "num_windows": int(num_windows),
            "windows": [
                {
                    "client_id": w["client_id"],
                    "window_id": w["window_id"],
                    "unit_ids": w["unit_ids"],
                    "opportunity_weights": w["opportunity_weights"],
                }
                for w in windows
            ],
        }),
        "meta": payload,
    }

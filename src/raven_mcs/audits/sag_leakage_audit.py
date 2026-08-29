"""G0-2 / G0-5 set and feature leakage audits."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from raven_mcs.sag.gate import FORBIDDEN_GATE_FEATURES


def audit_gate_features(feature_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    hits: list[str] = []
    for row in feature_rows:
        name = str(row.get("feature", ""))
        if name in FORBIDDEN_GATE_FEATURES:
            hits.append(name)
    return {"pass": not hits, "forbidden_hits": sorted(set(hits))}


def audit_b_a_sets(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    failures: list[str] = []
    for row in rows:
        a = set(row.get("A_r") or [])
        b = set(row.get("B_r") or [])
        u = set(row.get("U_r") or [])
        masses = row.get("m_by_client") or {}
        if not a.issubset(b):
            failures.append(f"window {row.get('window_id')}: A not subset B")
        if not a.issubset(u):
            failures.append(f"window {row.get('window_id')}: A not subset U")
        for cid in b:
            m = float(masses.get(cid, 0.0))
            if not (m > 0):
                failures.append(
                    f"window {row.get('window_id')}: B client {cid} has m<=0"
                )
    return {
        "pass": not failures,
        "failures": failures[:50],
        "n_failures": len(failures),
    }

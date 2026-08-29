"""G0-3 shared EventTrace hashes across Always-D / No-D / SAG."""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

import pandas as pd

from raven_mcs.utils.hashing import sha256_json


def _jsonable(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def layer_hash(events: pd.DataFrame, window_id: int, columns: Sequence[str]) -> str:
    sub = events.loc[events["window_id"] == int(window_id), ["client_id", *columns]].copy()
    sub = sub.sort_values("client_id")
    payload: dict[str, Any] = {}
    for _, rec in sub.iterrows():
        cid = str(rec["client_id"])
        payload[cid] = {col: _jsonable(rec[col]) for col in columns}
    return sha256_json(payload)


def audit_shared_eventtrace(
    hashes_by_method: Mapping[str, Mapping[str, str]],
    required_methods: Iterable[str] = ("raven", "raven_wo_design", "raven_sag"),
) -> dict[str, Any]:
    methods = [m for m in required_methods if m in hashes_by_method]
    failures: list[str] = []
    if len(methods) < 2:
        return {"pass": False, "failures": ["need at least two methods to compare"]}
    keys = set(hashes_by_method[methods[0]])
    for method in methods[1:]:
        if set(hashes_by_method[method]) != keys:
            failures.append(f"hash key mismatch for {method}")
            continue
        for key in sorted(keys):
            if hashes_by_method[method][key] != hashes_by_method[methods[0]][key]:
                failures.append(f"{key} differs: {methods[0]} vs {method}")
    return {"pass": not failures, "failures": failures, "n_keys": len(keys)}

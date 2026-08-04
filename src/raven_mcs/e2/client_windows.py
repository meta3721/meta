"""Client-window risk-set interface for E2 usable stage."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from raven_mcs.e2.generators import compute_client_window_tail_composition
from raven_mcs.e2.identity import load_e1_supported_test_units
from raven_mcs.e2.tail_score import (
    E2TailScoreError,
    load_frozen_tail_score_map,
    lookup_tail_score,
    reject_caller_tail_score_override,
)
from raven_mcs.utils.hashing import sha256_json

ROOT = Path(__file__).resolve().parents[3]


class E2ClientWindowError(RuntimeError):
    """Raised when client-window risk-set validation fails."""


REQUIRED_FIELDS = (
    "client_id",
    "window_id",
    "unit_ids",
    "opportunity_weights",
    "attempt_eligible",
)


def validate_client_window_record(
    record: Mapping[str, Any],
    *,
    supported_units: set[str],
    frozen_tail_score_map: Mapping[str, int],
) -> dict[str, Any]:
    reject_caller_tail_score_override(record)
    missing = [name for name in REQUIRED_FIELDS if name not in record]
    if missing:
        raise E2ClientWindowError(f"client-window missing fields: {missing}")
    unit_ids = [str(u) for u in record["unit_ids"]]
    weights = np.asarray(record["opportunity_weights"], dtype=np.float64).reshape(-1)
    if len(unit_ids) != weights.size:
        raise E2ClientWindowError("unit_ids/opportunity_weights length mismatch")
    if weights.size == 0:
        if bool(record["attempt_eligible"]):
            raise E2ClientWindowError(
                "empty risk set cannot be attempt_eligible; mark ineligible or error"
            )
        return {
            "client_id": str(record["client_id"]),
            "window_id": str(record["window_id"]),
            "unit_ids": unit_ids,
            "opportunity_weights": weights,
            "attempt_eligible": False,
            "tail_score": np.asarray([], dtype=np.int8),
            "nu_opp": np.asarray([], dtype=np.float64),
            "z_tail": None,
        }
    if np.any(~np.isfinite(weights)) or np.any(weights < 0):
        raise E2ClientWindowError("opportunity_weights must be finite and nonnegative")
    total = float(weights.sum())
    if total <= 0:
        raise E2ClientWindowError("opportunity_weights must sum to a positive value")
    unknown = [u for u in unit_ids if u not in supported_units]
    if unknown:
        raise E2ClientWindowError(
            f"unit_ids outside E1 supported test identity: {unknown[:5]}"
        )
    scores = lookup_tail_score(unit_ids, frozen_tail_score_map)
    nu = weights / total
    z = compute_client_window_tail_composition(nu, scores)
    return {
        "client_id": str(record["client_id"]),
        "window_id": str(record["window_id"]),
        "unit_ids": unit_ids,
        "opportunity_weights": weights,
        "attempt_eligible": bool(record["attempt_eligible"]),
        "tail_score": scores,
        "nu_opp": nu,
        "z_tail": float(z),
        "pre_outcome_features": dict(record.get("pre_outcome_features") or {}),
    }


def build_client_window_compositions(
    records: Sequence[Mapping[str, Any]],
    *,
    root: Path | None = None,
) -> tuple[list[dict[str, Any]], pd.DataFrame]:
    root = Path(root or ROOT)
    supported = set(
        load_e1_supported_test_units(root)["unit_id"].astype(str).tolist()
    )
    mapping = load_frozen_tail_score_map(root)
    validated: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    for record in records:
        item = validate_client_window_record(
            record, supported_units=supported, frozen_tail_score_map=mapping,
        )
        validated.append(item)
        scores = item["tail_score"]
        nu = item["nu_opp"]
        head_mass = float(nu[scores == -1].sum()) if nu.size else 0.0
        tail_mass = float(nu[scores == 1].sum()) if nu.size else 0.0
        neutral_mass = float(nu[scores == 0].sum()) if nu.size else 0.0
        feature_payload = {
            "client_id": item["client_id"],
            "window_id": item["window_id"],
            "unit_ids": item["unit_ids"],
            "opportunity_weights": item["opportunity_weights"].tolist(),
            "z_tail": item["z_tail"],
        }
        rows.append({
            "client_id": item["client_id"],
            "window_id": item["window_id"],
            "attempt_eligible": bool(item["attempt_eligible"]),
            "risk_set_size": int(len(item["unit_ids"])),
            "head_opportunity_mass": head_mass,
            "tail_opportunity_mass": tail_mass,
            "neutral_opportunity_mass": neutral_mass,
            "z_tail": item["z_tail"] if item["z_tail"] is not None else np.nan,
            "feature_payload_hash": sha256_json(feature_payload),
        })
    frame = pd.DataFrame(rows)
    return validated, frame

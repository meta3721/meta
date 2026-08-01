"""Static usable-propensity feature leakage bans (E0.6 / paper F2.6)."""

from __future__ import annotations

import re
from typing import Iterable

FORBIDDEN_Q_FEATURE_TOKENS = (
    "realized",
    "actual",
    "arrival",
    "future",
    "post_outcome",
    "update_norm",
    "update_value",
    "update_vector",
    "actual_delay",
    "realized_delay",
    "completion_time",
    "network_delay",
    "loss_improvement",
    "gradient_norm",
)


def _normalize_token(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")


def scan_q_feature_names(feature_names: Iterable[str]) -> list[str]:
    """Return forbidden tokens found in q / usable feature names."""
    hits: list[str] = []
    for raw in feature_names:
        normalized = _normalize_token(raw)
        for token in FORBIDDEN_Q_FEATURE_TOKENS:
            if token == normalized or f"_{token}_" in f"_{normalized}_":
                hits.append(str(raw))
                break
    return hits


def assert_q_features_leakage_free(feature_names: Iterable[str]) -> None:
    hits = scan_q_feature_names(feature_names)
    if hits:
        raise ValueError(
            "Forbidden post-outcome / update-dependent q features: "
            + ", ".join(sorted(set(hits)))
        )

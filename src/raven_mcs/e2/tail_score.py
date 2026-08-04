"""Frozen atomic tail-score lookup (caller override forbidden)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from raven_mcs.e2.identity import load_e1_head_tail_mapping
from raven_mcs.utils.hashing import sha256_json
from raven_mcs.utils.serialization import load_json

ROOT = Path(__file__).resolve().parents[3]


class E2TailScoreError(RuntimeError):
    """Raised when frozen tail-score lookup fails."""


def load_frozen_tail_score_map(root: Path | None = None) -> dict[str, int]:
    root = Path(root or ROOT)
    frame = load_e1_head_tail_mapping(root)
    mapping = {
        str(row.unit_id): int(row.tail_score)
        for row in frame.itertuples(index=False)
    }
    manifest = load_json(
        root / "configs/frozen/e2_numeric/atomic_tail_score_manifest.json"
    )
    digest = sha256_json(
        [{"unit_id": k, "tail_score": mapping[k]} for k in sorted(mapping)]
    )
    if digest != manifest["score_payload_hash"]:
        raise E2TailScoreError("frozen tail-score map failed manifest hash check")
    return mapping


def lookup_tail_score(
    unit_ids: Sequence[str],
    frozen_tail_score_map: Mapping[str, int] | None = None,
    *,
    root: Path | None = None,
) -> np.ndarray:
    """Return t_subset aligned to unit_ids; unknown ids raise."""
    mapping = frozen_tail_score_map or load_frozen_tail_score_map(root)
    scores: list[int] = []
    for unit_id in unit_ids:
        key = str(unit_id)
        if key not in mapping:
            raise E2TailScoreError(f"unknown unit_id for tail-score lookup: {key}")
        scores.append(int(mapping[key]))
    out = np.asarray(scores, dtype=np.int8)
    if set(np.unique(out)) - {-1, 0, 1}:
        raise E2TailScoreError("tail scores must be in {-1,0,+1}")
    return out


def reject_caller_tail_score_override(payload: Mapping[str, Any]) -> None:
    if "tail_score" in payload or "tail_scores" in payload or "t_i" in payload:
        raise E2TailScoreError(
            "caller-provided tail_score arrays are forbidden; "
            "use frozen lookup_tail_score(unit_ids)"
        )

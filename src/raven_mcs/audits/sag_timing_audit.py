"""G0-1 timing audit."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from raven_mcs.sag.timing import SagTimingError, assert_stage_order


def audit_timing_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    failures: list[str] = []
    for row in rows:
        marks = {
            "gate": int(row["gate_stage"]),
            "R": int(row["R_stage"]),
            "p_obs_freeze": int(row["p_obs_freeze_stage"]),
            "O": int(row["O_stage"]),
            "local": int(row["local_stage"]),
            "q_use_freeze": int(row["q_use_freeze_stage"]),
            "U": int(row["U_stage"]),
            "P2": int(row["P2_stage"]),
        }
        try:
            assert_stage_order(marks)
        except SagTimingError as exc:
            failures.append(f"window {row.get('window_id')}: {exc}")
    return {"pass": not failures, "n": len(rows), "failures": failures}

"""Logical stage indices for SAG G0-1 (wall-clock optional)."""

from __future__ import annotations

from dataclasses import dataclass, field

STAGE_GATE = 1
STAGE_R = 2
STAGE_P_OBS_FREEZE = 3
STAGE_O = 4
STAGE_LOCAL = 5
STAGE_Q_USE_FREEZE = 6
STAGE_U = 7
STAGE_P2 = 8

REQUIRED_ORDER = (
    ("gate", STAGE_GATE),
    ("R", STAGE_R),
    ("p_obs_freeze", STAGE_P_OBS_FREEZE),
    ("O", STAGE_O),
    ("local", STAGE_LOCAL),
    ("q_use_freeze", STAGE_Q_USE_FREEZE),
    ("U", STAGE_U),
    ("P2", STAGE_P2),
)


class SagTimingError(RuntimeError):
    pass


@dataclass
class SagStages:
    """Monotonic logical clock for one window. Indices match the G0 instruction."""

    marks: dict[str, int] = field(default_factory=dict)
    _last: int = 0

    def mark(self, name: str, stage: int) -> int:
        if name in self.marks:
            raise SagTimingError(f"stage {name} already marked")
        if stage < self._last:
            raise SagTimingError(
                f"stage {name}={stage} is not monotonic (last={self._last})"
            )
        self.marks[name] = int(stage)
        self._last = int(stage)
        return int(stage)

    def as_dict(self) -> dict[str, int]:
        return dict(self.marks)


def assert_stage_order(marks: dict[str, int]) -> None:
    """G0-1: gate < R <= p_obs_freeze < O < local < q_use_freeze < U <= P2."""
    required = {name: stage for name, stage in REQUIRED_ORDER}
    missing = [name for name in required if name not in marks]
    if missing:
        raise SagTimingError(f"missing stages: {missing}")
    gate = marks["gate"]
    r = marks["R"]
    p = marks["p_obs_freeze"]
    o = marks["O"]
    local = marks["local"]
    q = marks["q_use_freeze"]
    u = marks["U"]
    p2 = marks["P2"]
    if not (gate < r <= p < o < local < q < u <= p2):
        raise SagTimingError(
            "timing violated: require gate < R <= p_obs_freeze < O < "
            f"local < q_use_freeze < U <= P2; got {marks}"
        )
    for name, expected in required.items():
        if int(marks[name]) != int(expected):
            raise SagTimingError(
                f"stage index mismatch for {name}: {marks[name]} != {expected}"
            )

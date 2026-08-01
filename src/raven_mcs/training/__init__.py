"""Training loop primitives."""

from raven_mcs.training.client import ClientTrainer
from raven_mcs.training.local_objective import local_hajek_loss, normalize_a_bar
from raven_mcs.training.synthetic_gate_runner import SyntheticGateRunner, build_synthetic_runner
from raven_mcs.training.window_runner import FullWindowRunner, WindowMetrics, build_full_runner
from raven_mcs.training.window_timing import WindowClock, WindowTimingError

__all__ = [
    "WindowClock",
    "SyntheticGateRunner",
    "FullWindowRunner",
    "WindowMetrics",
    "WindowTimingError",
    "ClientTrainer",
    "build_synthetic_runner",
    "build_full_runner",
    "local_hajek_loss",
    "normalize_a_bar",
]

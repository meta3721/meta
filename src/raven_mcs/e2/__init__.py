"""E2 target-risk misalignment numeric scenario layer."""

from raven_mcs.e2.diagnostics import compute_e2_mass_diagnostics
from raven_mcs.e2.identity import (
    load_e1_atomic_target_weights,
    load_e1_head_tail_mapping,
    load_e1_supported_test_units,
    load_e1_target_identity,
)
from raven_mcs.e2.methods import resolve_method
from raven_mcs.e2.scenario_generator import generate_e2_numeric_scenario
from raven_mcs.e2.tail_score import lookup_tail_score

__all__ = [
    "load_e1_target_identity",
    "load_e1_atomic_target_weights",
    "load_e1_head_tail_mapping",
    "load_e1_supported_test_units",
    "generate_e2_numeric_scenario",
    "resolve_method",
    "compute_e2_mass_diagnostics",
    "lookup_tail_score",
]

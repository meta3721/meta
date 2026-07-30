"""Experiment registry stubs."""

from __future__ import annotations

KNOWN_EXPERIMENTS = (
    "E0_unit",
    "E1_balanced",
    "E2_misalignment",
    "E3_main_complete",
    "E4_ablation",
    "E5_support_reachability",
    "E6_robustness",
    "E7_identification",
    "E8_scalability",
    "E9_tdrive",
)


def is_known_experiment(name: str) -> bool:
    return name in KNOWN_EXPERIMENTS

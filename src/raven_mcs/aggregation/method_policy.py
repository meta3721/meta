"""Method policy definitions (P10-C).

Each method declares which components it uses, so the WindowRunner can
selectively apply correction, debt, variance, etc.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MethodPolicy:
    """Declarative policy for each method's correction/training pathway."""

    uses_central_training: bool = False
    uses_design_ratio: bool = False
    uses_observation_ipw: bool = False
    uses_usable_ipw: bool = False
    uses_hajek_local_loss: bool = False
    uses_instant_calibration: bool = False
    uses_debt: bool = False
    uses_reference_penalty: bool = False
    uses_variance_penalty: bool = False
    uses_staleness_penalty: bool = False
    uses_oracle_propensity: bool = False
    is_external_baseline: bool = False
    # policy: follow uses_design_ratio; always_on/off: Mode D/0; sag: SAG certificates.
    # Never encode dataset identity here.
    gate_mode: str = "policy"


# Method policy registry
POLICY_MAP: dict[str, MethodPolicy] = {
    "central_all": MethodPolicy(
        uses_central_training=True,
    ),
    "central_delivered": MethodPolicy(
        uses_central_training=True,
    ),
    "fedavg_window": MethodPolicy(),
    "fedau_window": MethodPolicy(
        uses_usable_ipw=True,
    ),
    "obsuse_window": MethodPolicy(
        uses_observation_ipw=True,
        uses_usable_ipw=True,
    ),
    "fedasync_window": MethodPolicy(
        uses_staleness_penalty=True,
    ),
    "timealign_agg": MethodPolicy(
        uses_staleness_penalty=True,
    ),
    "flamf_timealign_adapted": MethodPolicy(),
    "flamf_original": MethodPolicy(
        is_external_baseline=True,
    ),
    "local_hajek": MethodPolicy(
        uses_design_ratio=True,
        uses_observation_ipw=True,
        uses_hajek_local_loss=True,
    ),
    "twostage_hajek": MethodPolicy(
        uses_design_ratio=True,
        uses_observation_ipw=True,
        uses_usable_ipw=True,
        uses_hajek_local_loss=True,
    ),
    "inst_cal": MethodPolicy(
        uses_design_ratio=True,
        uses_observation_ipw=True,
        uses_usable_ipw=True,
        uses_instant_calibration=True,
        uses_reference_penalty=True,
        uses_variance_penalty=True,
        uses_staleness_penalty=True,
    ),
    "debt_cal": MethodPolicy(
        uses_debt=True,
        uses_instant_calibration=True,
        uses_reference_penalty=True,
    ),
    "raven": MethodPolicy(
        uses_design_ratio=True,
        uses_observation_ipw=True,
        uses_usable_ipw=True,
        uses_hajek_local_loss=True,
        uses_instant_calibration=True,
        uses_debt=True,
        uses_reference_penalty=True,
        uses_variance_penalty=True,
        uses_staleness_penalty=True,
        gate_mode="always_on",
    ),
    # E4 one-factor-at-a-time RAVEN ablations.  Keep every non-ablated RAVEN
    # component identical; do not substitute a historical partial method.
    "raven_wo_design": MethodPolicy(
        uses_observation_ipw=True, uses_usable_ipw=True, uses_hajek_local_loss=True,
        uses_instant_calibration=True, uses_debt=True, uses_reference_penalty=True,
        uses_variance_penalty=True, uses_staleness_penalty=True,
        gate_mode="always_off",
    ),
    "raven_sag": MethodPolicy(
        uses_design_ratio=True,
        uses_observation_ipw=True,
        uses_usable_ipw=True,
        uses_hajek_local_loss=True,
        uses_instant_calibration=True,
        uses_debt=True,
        uses_reference_penalty=True,
        uses_variance_penalty=True,
        uses_staleness_penalty=True,
        gate_mode="sag",
    ),
    "raven_wo_obs": MethodPolicy(
        uses_design_ratio=True, uses_usable_ipw=True, uses_hajek_local_loss=True,
        uses_instant_calibration=True, uses_debt=True, uses_reference_penalty=True,
        uses_variance_penalty=True, uses_staleness_penalty=True,
    ),
    "raven_wo_use": MethodPolicy(
        uses_design_ratio=True, uses_observation_ipw=True, uses_hajek_local_loss=True,
        uses_instant_calibration=True, uses_debt=True, uses_reference_penalty=True,
        uses_variance_penalty=True, uses_staleness_penalty=True,
    ),
    "raven_wo_inst": MethodPolicy(
        uses_design_ratio=True, uses_observation_ipw=True, uses_usable_ipw=True,
        uses_hajek_local_loss=True, uses_debt=True, uses_reference_penalty=True,
        uses_variance_penalty=True, uses_staleness_penalty=True,
    ),
    "raven_wo_debt": MethodPolicy(
        uses_design_ratio=True, uses_observation_ipw=True, uses_usable_ipw=True,
        uses_hajek_local_loss=True, uses_instant_calibration=True,
        uses_reference_penalty=True, uses_variance_penalty=True,
        uses_staleness_penalty=True,
    ),
    "raven_simoracle": MethodPolicy(
        uses_design_ratio=True,
        uses_observation_ipw=True,
        uses_usable_ipw=True,
        uses_hajek_local_loss=True,
        uses_instant_calibration=True,
        uses_debt=True,
        uses_reference_penalty=True,
        uses_variance_penalty=True,
        uses_staleness_penalty=True,
        uses_oracle_propensity=True,
    ),
}


def get_method_policy(method: str) -> MethodPolicy:
    """Get the policy for a method by name."""
    normalized = method.strip().lower().replace("-", "_")
    if normalized in POLICY_MAP:
        return POLICY_MAP[normalized]
    # Alias mappings
    aliases = {
        "centralall": "central_all",
        "centraldelivered": "central_delivered",
        "fedavg": "fedavg_window",
        "fedau": "fedau_window",
        "fedau_window": "fedau_window",
        "obsuse": "obsuse_window",
        "obsuse_window": "obsuse_window",
        "fedasync": "fedasync_window",
        "timealign": "timealign_agg",
        "time_align": "timealign_agg",
        "time_align_agg": "timealign_agg",
        "flamf": "flamf_original",
        "local_hajek": "local_hajek",
        "twostage_hajek": "twostage_hajek",
        "two_stage_hajek": "twostage_hajek",
        "inst_cal": "inst_cal",
        "instant_calibration": "inst_cal",
        "debt_cal": "debt_cal",
        "debt_calibration": "debt_cal",
        "raven_mcs": "raven",
        "raven_simoracle": "raven_simoracle",
        "simoracle": "raven_simoracle",
        "raven_sag": "raven_sag",
        "sag": "raven_sag",
        "sag_raven": "raven_sag",
    }
    canonical = aliases.get(normalized, normalized)
    if canonical in POLICY_MAP:
        return POLICY_MAP[canonical]
    return MethodPolicy()

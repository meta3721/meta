"""Support-Aware Gate (SAG) v1.2 — predictable binary Design gate.

SAG controls only the opportunity/Design ratio. It does not replace
observation IPW, usable IPW, P2, variance, staleness, or optional Debt.
Dataset identity is never a Gate feature.
"""

from raven_mcs.sag.certificates import (
    CertificateBundle,
    FrozenSagThresholds,
    compute_certificates,
)
from raven_mcs.sag.counterfactual_audit import (
    CounterfactualAudit,
    audit_design_vs_nodesign,
)
from raven_mcs.sag.gate import (
    FORBIDDEN_GATE_FEATURES,
    LEGAL_GATE_FEATURES,
    GateDecision,
    decide_gate,
    zeta_tilde,
)
from raven_mcs.sag.sag_state import SagState
from raven_mcs.sag.timing import SagStages, assert_stage_order

__all__ = [
    "CertificateBundle",
    "CounterfactualAudit",
    "FORBIDDEN_GATE_FEATURES",
    "FrozenSagThresholds",
    "GateDecision",
    "LEGAL_GATE_FEATURES",
    "SagStages",
    "SagState",
    "assert_stage_order",
    "audit_design_vs_nodesign",
    "compute_certificates",
    "decide_gate",
    "zeta_tilde",
]

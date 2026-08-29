"""Full training pipeline WindowRunner — real Common-NDMF training (P10).

Each window (SAG v1.2 / PostAudit III–VI):
 1. Read theta_r; compute F_{r-} certificates; freeze G_r
 2. Realize R (risk sets) from EventTrace
 3. Freeze p_hat_obs from pre-O features
 4. Realize O; E_r = registered/attempted; B_r = {k in E_r : m>0}
 5. Local SGD on B_r (not A_r)
 6. Freeze q_hat_use from pre-U features
 7. Realize U → A_r = B_r ∩ U_r
 8. P2 / global update / optional debt
 9. Post-window D vs 0 audit (future Gate only)
10. After window close: update opportunity/p/q/variance state
"""

from __future__ import annotations

import copy
from collections import Counter
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd
import torch

from raven_mcs.aggregation.base import Aggregator, WindowAggregateInput
from raven_mcs.aggregation.debt import coverage_mix, update_debt
from raven_mcs.aggregation.method_policy import (
    MethodPolicy,
    get_method_policy,
)
from raven_mcs.aggregation.methods import get_aggregator
from raven_mcs.correction.design_ratio import zeta_hat_stratum
from raven_mcs.correction.effective_sample_size import effective_sample_size
from raven_mcs.correction.hajek import (
    composition,
    group_mass,
    normalized_weights,
    raw_weights,
    total_mass,
)
from raven_mcs.correction.pi_target import build_pi_target
from raven_mcs.correction.second_stage import beta_hat, d_weight, two_stage_mass
from raven_mcs.data.processed_dataset import ProcessedDataset
from raven_mcs.data.target import GroupMapper, RepeatableTimeOfDayMapper, TargetBuilder
from raven_mcs.data.window_dataset import WindowDataSlice, extract_window_slice
from raven_mcs.models.common_ndmf import CommonNDMF, deterministic_common_ndmf
from raven_mcs.models.features import extract_features
from raven_mcs.opportunities.estimator import OpportunityEstimator
from raven_mcs.propensity.observation import ObservationPropensity
from raven_mcs.propensity.usable import UsablePropensity, deadline_slack_pre
from raven_mcs.sag.certificates import FrozenSagThresholds, compute_certificates
from raven_mcs.sag.counterfactual_audit import audit_design_vs_nodesign
from raven_mcs.sag.gate import decide_gate, zeta_tilde
from raven_mcs.sag.sag_state import SagState
from raven_mcs.sag.timing import (
    STAGE_GATE,
    STAGE_LOCAL,
    STAGE_O,
    STAGE_P2,
    STAGE_P_OBS_FREEZE,
    STAGE_Q_USE_FREEZE,
    STAGE_R,
    STAGE_U,
    SagStages,
)
from raven_mcs.simulation.event_trace import EventTrace
from raven_mcs.training.client import ClientTrainer, unflatten_params
from raven_mcs.training.client import _flatten_params as flatten_params
from raven_mcs.training.window_timing import WindowClock, WindowTimingError
from raven_mcs.utils.hashing import sha256_json


@dataclass
class WindowMetrics:
    """Per-window training metrics."""
    window_id: int
    active: bool
    alpha: list[float]
    beta_hat: list[float]
    theta_hash_before: str
    theta_hash_after: str
    debt_l1: float
    omega: list[float]
    active_clients: list[str]
    n_eff_values: list[float]
    clip_rate_stage1: float
    clip_rate_stage2: float
    train_loss: float
    e_r_size: int
    a_r_size: int
    b_r_size: int = 0
    g_r: int = 0


@dataclass
class FullWindowRunner:
    """Full training WindowRunner using real Common-NDMF, local SGD, and two-stage correction.

    Each window follows the 12-step pipeline described in the P10 instruction.
    """

    trace: EventTrace
    dataset: ProcessedDataset
    model: CommonNDMF
    aggregator: Aggregator
    policy: MethodPolicy
    mu: np.ndarray
    num_groups: int
    # Local updates are normalized gradients; apply a conservative fixed server
    # step so legitimate stale updates cannot destabilize a smoke run.
    eta: float = 0.01
    learning_rate: float = 0.01
    local_steps: int = 5
    a_max: float = 20.0
    p_min: float = 0.05
    d_max: float = 10.0
    q_min: float = 0.05
    v_floor: float = 1e-4
    a_bar_floor: float = 1e-8
    pi_min: float = 1e-6
    pi_target: dict[tuple[str, str], float] = field(default_factory=dict)
    s_max: int = 5
    variance_decay: float = 0.9
    seed: int = 26001
    device: str = "cpu"
    # E3 spatial×time: never remap via coarse time blocks unless explicitly requested.
    use_coarse_time_groups: bool = False
    # Frozen joint opportunity mass on client×stratum (same scale as pi_target).
    pi_opp_joint: dict[tuple[str, str], float] = field(default_factory=dict)

    # State
    theta: dict[str, torch.Tensor] = field(default_factory=dict)
    debt: np.ndarray = field(default_factory=lambda: np.zeros(2, dtype=np.float64))
    scale: float = 0.0
    omega_sum: np.ndarray = field(default_factory=lambda: np.zeros(2, dtype=np.float64))
    metrics: list[WindowMetrics] = field(default_factory=list)
    opportunity_estimator: Optional[OpportunityEstimator] = None
    obs_propensity: Optional[ObservationPropensity] = None
    usable_propensity: Optional[UsablePropensity] = None
    variance_state: dict[str, float] = field(default_factory=dict)
    variance_mean: dict[str, np.ndarray] = field(default_factory=dict)
    variance_count: dict[str, int] = field(default_factory=dict)
    model_versions: dict[int, dict[str, torch.Tensor]] = field(default_factory=dict)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    p_propensity_history: list[dict[str, Any]] = field(default_factory=list)
    p_model_version: int = 0
    q_propensity_history: list[dict[str, Any]] = field(default_factory=list)
    q_attempt_diagnostics: list[dict[str, Any]] = field(default_factory=list)
    q_model_version: int = 0
    sag_thresholds: FrozenSagThresholds | None = None
    sag_state: SagState = field(default_factory=SagState)
    sag_window_logs: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.mu = np.asarray(self.mu, dtype=np.float64)
        if len(self.debt) != self.num_groups:
            self.debt = np.zeros(self.num_groups, dtype=np.float64)
        if len(self.omega_sum) != self.num_groups:
            self.omega_sum = np.zeros(self.num_groups, dtype=np.float64)
        self.clock = WindowClock(num_windows=int(self.trace.metadata.num_windows))
        if not self.theta:
            self.theta = dict(self.model.state_dict())
        self.model.to(self.device)
        if self.opportunity_estimator is None:
            self.opportunity_estimator = OpportunityEstimator()
        if self.pi_target:
            self.opportunity_estimator.initialize_support(
                key for key, mass in self.pi_target.items() if mass > 0.0
            )
        if self.obs_propensity is None:
            self.obs_propensity = ObservationPropensity()
        if self.usable_propensity is None:
            self.usable_propensity = UsablePropensity()
        self.model_versions.setdefault(0, copy.deepcopy(self.theta))
        self._trainer = ClientTrainer(self.model, learning_rate=self.learning_rate)
        if self.sag_thresholds is None:
            self.sag_thresholds = FrozenSagThresholds(n_groups=int(self.num_groups))
        # Lagged FedAU participation counters. Updated only after window close.
        self._fedau_usable_count: dict[str, float] = {}
        self._fedau_attempt_count: dict[str, float] = {}
        self._fedau_epsilon: float = 1e-6

    def _lagged_participation_rates(self, client_ids: list[str]) -> dict[str, float]:
        """Pre-outcome participation rates from windows strictly before the current one."""
        eps = float(self._fedau_epsilon)
        rates: dict[str, float] = {}
        for cid in client_ids:
            usable = float(self._fedau_usable_count.get(cid, 0.0))
            attempts = float(self._fedau_attempt_count.get(cid, 0.0))
            rates[cid] = (usable + eps) / (attempts + eps)
        return rates

    def _client_observation_rates(
        self,
        client_ids: list[str],
        client_data: dict[str, dict],
    ) -> dict[str, float]:
        """Lagged observation propensity, averaged over the client's current risk set."""
        p_min = float(self.p_min)
        rates: dict[str, float] = {}
        for cid in client_ids:
            p = np.asarray(
                client_data.get(cid, {}).get("p_hat_model", [1.0]),
                dtype=np.float64,
            )
            if p.size == 0:
                rates[cid] = 1.0
            else:
                rates[cid] = float(np.mean(np.maximum(p, p_min)))
        return rates

    def _theta_hash(self) -> str:
        digest = hashlib.sha256()
        for name, value in sorted(self.theta.items()):
            array = value.detach().cpu().contiguous().numpy()
            digest.update(name.encode("utf-8"))
            digest.update(str(array.dtype).encode("ascii"))
            digest.update(str(array.shape).encode("ascii"))
            digest.update(array.tobytes())
        return digest.hexdigest()

    def _get_model_checkpoint(self, version: int) -> dict[str, torch.Tensor]:
        if version not in self.model_versions:
            raise WindowTimingError(f"Checkpoint version {version} is unavailable")
        return copy.deepcopy(self.model_versions[version])

    def _compute_zeta(
        self,
        client_id: str,
        stratum_ids: list[str],
    ) -> np.ndarray:
        """Compute zeta_hat for a client's risk set records.

        When ``pi_opp_joint`` is provided (E3 production), the design-ratio
        denominator uses that joint client×stratum mass (same scale as pi_tar).
        Otherwise falls back to the online opportunity estimator.
        """
        if not self.pi_target:
            raise RuntimeError("frozen pi target is required for official correction")
        missing = [
            (client_id, str(s)) for s in stratum_ids
            if (client_id, str(s)) not in self.pi_target
        ]
        if missing:
            raise RuntimeError(f"pi target lacks opportunity support: {missing[:3]}")
        pi_tar = np.array(
            [self.pi_target[(client_id, str(s))] for s in stratum_ids],
            dtype=np.float64,
        )

        if self.pi_opp_joint:
            missing_opp = [
                (client_id, str(s))
                for s in stratum_ids
                if (client_id, str(s)) not in self.pi_opp_joint
            ]
            if missing_opp:
                raise RuntimeError(
                    f"PIOPP_SCALE_ERROR: joint pi_opp lacks support: {missing_opp[:3]}"
                )
            pi_hat_opp = np.array(
                [float(self.pi_opp_joint[(client_id, str(s))]) for s in stratum_ids],
                dtype=np.float64,
            )
        else:
            if self.opportunity_estimator is None:
                return np.ones(len(stratum_ids), dtype=np.float64)
            pi_hat_opp = np.array(
                [
                    self.opportunity_estimator.pi_hat().get((client_id, s), self.p_min)
                    for s in stratum_ids
                ],
                dtype=np.float64,
            )

        return zeta_hat_stratum(pi_tar, pi_hat_opp, pi_min=self.pi_min)

    def _compute_p_hat(self, features_list: list[dict[str, float]]) -> np.ndarray:
        """Compute observation propensity estimates."""
        if self.obs_propensity is None:
            return np.full(len(features_list), 0.5, dtype=np.float64)
        return np.array([
            self.obs_propensity.predict(
                np.array([
                    f.get("bias", 1.0),
                    f.get("hour_block", 0.0),
                    f.get("planned_workload_pre", 1.0),
                ])
            )
            for f in features_list
        ], dtype=np.float64)

    @staticmethod
    def _hour_block(stratum_id: str) -> float:
        for token in str(stratum_id).split("::"):
            if token.startswith("block") and token[5:].isdigit():
                return float(token[5:])
        return 0.0

    def _gate_mode(self) -> str:
        return str(getattr(self.policy, "gate_mode", "policy") or "policy")

    def _decide_g_r(self) -> tuple[int, dict[str, Any], str | None, dict[str, bool]]:
        """Freeze G_r from F_{r-} only. Dataset identity is not an argument."""
        assert self.sag_thresholds is not None
        bundle = compute_certificates(self.sag_state.completed(), self.sag_thresholds)
        certs = bundle.as_gate_inputs()
        decision = decide_gate(certs, self.sag_thresholds.gate_thresholds())
        mode = self._gate_mode()
        if mode == "always_on":
            return 1, certs, None, decision.passed
        if mode == "always_off":
            return 0, certs, "OFF_MODE_NO_DESIGN", decision.passed
        if mode == "sag":
            return int(decision.G_r), certs, decision.fallback_reason, decision.passed
        if self.policy.uses_design_ratio:
            return 1, certs, None, decision.passed
        return 0, certs, "OFF_MODE_NO_DESIGN", decision.passed

    def _apply_zeta(self, zeta_d: np.ndarray, g_r: int) -> np.ndarray:
        mode = self._gate_mode()
        if mode == "sag":
            return zeta_tilde(zeta_d, g_r)
        if self.policy.uses_design_ratio:
            return np.asarray(zeta_d, dtype=np.float64)
        return np.ones(len(zeta_d), dtype=np.float64)

    def _freeze_q_hat_map(
        self,
        client_ids: list[str],
        client_data: dict[str, dict],
    ) -> dict[str, float]:
        """Predict q̂_use from pre-U features. Must not read rec.U."""
        out: dict[str, float] = {}
        for cid in client_ids:
            rec = client_data[cid]["record"]
            if (
                self.policy.uses_oracle_propensity
                and getattr(rec, "oracle_q", None) is not None
            ):
                out[cid] = float(rec.oracle_q)
            elif self.usable_propensity is not None:
                out[cid] = float(
                    self.usable_propensity.predict(
                        np.array(
                            [
                                1.0,
                                float(rec.model_age),
                                0.0,
                                0.0,
                                deadline_slack_pre(
                                    rec.window_close_time,
                                    rec.registration_time,
                                ),
                            ]
                        )
                    )
                )
            else:
                out[cid] = 0.5
        return out

    def _target_coverage(self, window_slice: WindowDataSlice) -> tuple[int, int]:
        present = {
            (str(rec.client_id), str(stratum))
            for rec in window_slice.records
            for stratum in rec.opportunity_strata
        }
        positive = [
            key for key, mass in self.pi_target.items() if float(mass) > 0.0
        ]
        if not positive:
            return 0, 0
        covered = sum(1 for key in positive if key in present)
        return len(positive), covered

    def _record_sag_window(
        self,
        *,
        window_id: int,
        g_r: int,
        stages: SagStages,
        cert_inputs: dict[str, Any],
        fallback_reason: str | None,
        gate_passed: dict[str, bool],
        b_r: list[str],
        a_r: list[str],
        u_r: list[str],
        m_by_client: dict[str, float],
        audit: dict[str, Any],
        p2_invoked: bool,
        extras: dict[str, Any] | None = None,
    ) -> None:
        log = {
            "window_id": int(window_id),
            "method_gate_mode": self._gate_mode(),
            "G_r": int(g_r),
            "fallback_reason": fallback_reason,
            "gate_stage": stages.marks.get("gate", STAGE_GATE),
            "R_stage": stages.marks.get("R", STAGE_R),
            "p_obs_freeze_stage": stages.marks.get("p_obs_freeze", STAGE_P_OBS_FREEZE),
            "O_stage": stages.marks.get("O", STAGE_O),
            "local_stage": stages.marks.get("local", STAGE_LOCAL),
            "q_use_freeze_stage": stages.marks.get("q_use_freeze", STAGE_Q_USE_FREEZE),
            "U_stage": stages.marks.get("U", STAGE_U),
            "P2_stage": stages.marks.get("P2", STAGE_P2),
            "p2_invoked": bool(p2_invoked),
            "B_r": list(b_r),
            "A_r": list(a_r),
            "U_r": list(u_r),
            "m_by_client": {str(k): float(v) for k, v in m_by_client.items()},
            "gate_features": dict(cert_inputs),
            "gate_passed": dict(gate_passed),
            **audit,
        }
        if extras:
            log.update(extras)
        self.sag_window_logs.append(log)
        history_row = {
            "window_id": int(window_id),
            "G_r": int(g_r),
            "fallback_reason": fallback_reason,
            "realized_C_cov": audit.get("realized_C_cov"),
            "realized_C_ret": audit.get("realized_C_ret"),
            "realized_C_ESS": audit.get("realized_C_ESS"),
            "realized_C_clip": audit.get("realized_C_clip"),
            "active_set_mismatch": audit.get("active_set_mismatch"),
            "both_empty": audit.get("both_empty"),
            "Delta_beta": audit.get("Delta_beta"),
            "Delta_M": audit.get("Delta_M"),
            "Delta_V": audit.get("Delta_V"),
            "A_common_size": audit.get("A_common_size"),
            "A_D_size": audit.get("A_D_size"),
            "A_0_size": audit.get("A_0_size"),
        }
        self.sag_state.append_completed(history_row)

    def _policy_extras(self, client_data: dict[str, dict]) -> dict[str, Any]:
        zetas = [data.get("zeta") for data in client_data.values() if "zeta" in data]
        ones = True
        for zeta in zetas:
            arr = np.asarray(zeta, dtype=np.float64)
            if arr.size == 0:
                continue
            if not np.allclose(arr, 1.0):
                ones = False
                break
        return {
            "zeta_tilde_all_ones": bool(ones),
            "uses_observation_ipw": bool(self.policy.uses_observation_ipw),
            "uses_usable_ipw": bool(self.policy.uses_usable_ipw),
            "uses_debt": bool(self.policy.uses_debt),
            "uses_variance_penalty": bool(self.policy.uses_variance_penalty),
            "uses_staleness_penalty": bool(self.policy.uses_staleness_penalty),
            "uses_design_ratio": bool(self.policy.uses_design_ratio),
        }

    def run(self) -> list[WindowMetrics]:
        events = self.trace.events

        for window_id in range(int(self.trace.metadata.num_windows)):
            window_metrics = self._process_window(window_id, events)
            self.metrics.append(window_metrics)

        return self.metrics

    def _process_window(
        self, window_id: int, events: "pd.DataFrame",
    ) -> WindowMetrics:
        before_hash = self._theta_hash()
        version = self.clock.model_version
        stages = SagStages()
        g_r, cert_inputs, fallback_reason, gate_passed = self._decide_g_r()
        stages.mark("gate", STAGE_GATE)

        # Step 2: Realize R (risk sets). Do not use O/U for G_r.
        coarse_groups = (
            self.num_groups
            if self.use_coarse_time_groups and self.num_groups in {4, 8}
            else None
        )
        window_slice = extract_window_slice(
            window_id, events, self.dataset, coarse_time_groups=coarse_groups,
        )
        stages.mark("R", STAGE_R)

        if not window_slice.records:
            stages.mark("p_obs_freeze", STAGE_P_OBS_FREEZE)
            stages.mark("O", STAGE_O)
            stages.mark("local", STAGE_LOCAL)
            stages.mark("q_use_freeze", STAGE_Q_USE_FREEZE)
            stages.mark("U", STAGE_U)
            stages.mark("P2", STAGE_P2)
            empty_audit = {
                "A_D_size": 0,
                "A_0_size": 0,
                "active_set_mismatch": 0,
                "both_empty": 1,
                "service_diff": 0.0,
                "Delta_beta": None,
                "Delta_M": None,
                "Delta_V": None,
                "A_common_size": 0,
                "realized_C_cov": 0.0,
                "realized_C_ret": 0.0,
                "realized_C_ESS": 0.0,
                "realized_C_clip": 0.0,
            }
            self._record_sag_window(
                window_id=window_id,
                g_r=g_r,
                stages=stages,
                cert_inputs=cert_inputs,
                fallback_reason=fallback_reason,
                gate_passed=gate_passed,
                b_r=[],
                a_r=[],
                u_r=[],
                m_by_client={},
                audit=empty_audit,
                p2_invoked=False,
                extras=self._policy_extras({}),
            )
            self.clock.skip_empty_window()
            self.model_versions[self.clock.model_version] = copy.deepcopy(self.theta)
            after_hash = self._theta_hash()
            return WindowMetrics(
                window_id=window_id,
                active=False,
                alpha=[],
                beta_hat=[],
                theta_hash_before=before_hash,
                theta_hash_after=after_hash,
                debt_l1=float(np.linalg.norm(self.debt, ord=1)),
                omega=[],
                active_clients=[],
                n_eff_values=[],
                clip_rate_stage1=0.0,
                clip_rate_stage2=0.0,
                train_loss=0.0,
                e_r_size=0,
                a_r_size=0,
                b_r_size=0,
                g_r=int(g_r),
            )

        # Freeze p̂_obs from pre-O features (planned_workload_pre / hour_block).
        client_data: dict[str, dict] = {}
        for rec in window_slice.records:
            cid = rec.client_id
            zeta_d = self._compute_zeta(cid, rec.opportunity_strata)
            features_list = [
                {
                    "bias": 1.0,
                    "hour_block": self._hour_block(stratum),
                    "planned_workload_pre": float(
                        np.log1p(rec.planned_workload_pre),
                    ),
                }
                for stratum in rec.opportunity_strata
            ]
            # SimOracle: consume atomic p_obs_true(k,r,i) — never risk-set mean alone.
            if (
                self.policy.uses_oracle_propensity
                and getattr(rec, "p_obs_true_by_unit", None)
            ):
                p_map = rec.p_obs_true_by_unit or {}
                if not p_map:
                    raise RuntimeError("ATOMIC_POBS_ERROR: SimOracle missing p_obs_true_by_unit")
                p_hat = np.asarray(
                    [
                        float(p_map.get(str(uid), float("nan")))
                        for uid in rec.risk_set_unit_ids
                    ],
                    dtype=np.float64,
                )
                if np.isnan(p_hat).any():
                    raise RuntimeError(
                        "ATOMIC_POBS_ERROR: SimOracle risk unit lacks atomic p_obs_true"
                    )
            else:
                p_hat = self._compute_p_hat(features_list)
            p_hat_model = np.asarray(p_hat, dtype=np.float64).copy()
            if not self.policy.uses_observation_ipw:
                p_hat = np.ones(len(rec.opportunity_strata), dtype=np.float64)
            client_data[cid] = {
                "record": rec,
                "zeta_d": zeta_d,
                "p_hat": p_hat,
                "p_hat_model": p_hat_model,
            }
        stages.mark("p_obs_freeze", STAGE_P_OBS_FREEZE)

        # Realize O and form masses under frozen G_r / ζ̃.
        for cid, data in client_data.items():
            rec = data["record"]
            zeta = self._apply_zeta(data["zeta_d"], g_r)
            a_raw = raw_weights(zeta, data["p_hat"], a_max=self.a_max, p_min=self.p_min)
            m_g = group_mass(rec.O, a_raw, np.array(rec.target_groups), n_groups=self.num_groups)
            m_total = total_mass(m_g)
            a_bar = normalized_weights(rec.O, a_raw, m_total)
            c_g = composition(m_g, m_total)
            n_eff = effective_sample_size(rec.O, a_raw, total_mass=m_total)
            data.update({
                "zeta": zeta,
                "a_raw": a_raw,
                "a_bar": a_bar,
                "m_g": m_g,
                "m_total": m_total,
                "c_g": c_g,
                "n_eff": n_eff,
                "clip_stage1": float(np.mean(np.abs(a_raw) >= self.a_max)),
            })
        stages.mark("O", STAGE_O)

        # v2: E_r = registered/attempted; B_r = {k in E_r : m>0} = local train set.
        # Keep name e_r_clients for the m>0 set (historical source-audit alias of B_r).
        e_r_clients = [
            cid for cid, data in client_data.items()
            if data["m_total"] > 0
        ]
        b_r_clients = e_r_clients
        attempted_clients = [
            rec.client_id for rec in window_slice.records if rec.attempted == 1
        ]
        if not set(e_r_clients).issubset(set(attempted_clients)):
            raise RuntimeError("E_r must be a subset of the frozen attempted set")
        if any(rec.U == 1 and rec.attempted != 1 for rec in window_slice.records):
            raise RuntimeError("usable implies attempted")

        # Step 6: Execute local SGD for each client
        local_updates: dict[str, np.ndarray] = {}
        train_losses: dict[str, float] = {}

        for cid in e_r_clients:
            data = client_data[cid]
            rec = data["record"]
            downloaded_version = rec.downloaded_version
            self.clock.register_local_work(downloaded_version)
            checkpoint = self._get_model_checkpoint(downloaded_version)

            observed_records = []
            # PREPROCESSING_CONSISTENCY_FIX: use the dataset's frozen sorted
            # spatial_to_idx (same as eval). Rebuilding from unsorted
            # DataFrame.unique() order scrambled embeddings on U-Air/Traffic.
            spatial_to_idx = {
                str(sid): int(i) for sid, i in self.dataset._spatial_to_idx.items()
            }
            total_time_slots = int(self.dataset.atomic_df["time_index"].max()) + 1
            for i, (uid, obs_val) in enumerate(zip(rec.observed_unit_ids, rec.observed_values)):
                unit = self.dataset.get_atomic_by_id(uid)
                if unit is not None:
                    observed_records.append({
                        "spatial_id": unit.spatial_id,
                        "absolute_time": unit.absolute_time,
                        "time_index": unit.time_index,
                        "observed_value": obs_val,
                        "spatial_to_idx": spatial_to_idx,
                        "total_time_slots": total_time_slots,
                    })

            a_bar_np = data["a_bar"].astype(np.float64)
            obs_mask = rec.O > 0
            a_bar_observed = a_bar_np[obs_mask] if obs_mask.any() else a_bar_np
            if not self.policy.uses_hajek_local_loss:
                a_bar_observed = np.ones(len(observed_records), dtype=np.float64)
                a_bar_observed /= max(len(observed_records), 1)

            if len(a_bar_observed) != len(observed_records):
                raise RuntimeError(
                    f"Observed records/weights misaligned for {cid}: "
                    f"{len(observed_records)} records vs {len(a_bar_observed)} weights"
                )

            update, loss = self._trainer.train_step(
                model_state=checkpoint,
                observed_records=observed_records,
                a_bar_weights=a_bar_observed,
                local_steps=self.local_steps,
            )
            update = np.asarray(update, dtype=np.float64)
            if not np.all(np.isfinite(update)) or (
                isinstance(loss, float) and not np.isfinite(loss)
            ):
                from raven_mcs.e3.numerical.finite import NonfiniteNumericalState

                raise NonfiniteNumericalState(
                    f"NONFINITE_NUMERICAL_STATE: local update/loss nonfinite "
                    f"client={cid} window={window_id}"
                )
            local_updates[cid] = update
            train_losses[cid] = loss
            raw_local = np.ones(len(observed_records), dtype=np.float64)
            raw_local /= max(len(observed_records), 1)
            self.diagnostics.append({
                "window_id": window_id,
                "client_id": cid,
                "observed_unit_ids": list(rec.observed_unit_ids),
                "risk_set_unit_ids": list(rec.risk_set_unit_ids),
                "raw_local_weights": raw_local.tolist(),
                "hajek_local_weights": data["a_bar"][obs_mask].tolist(),
                "applied_local_weights": a_bar_observed.tolist(),
                "a_bar": a_bar_observed.tolist(),
                "w_units": a_bar_observed.tolist(),
                "zeta_hat": data["zeta"].tolist(),
                "p_hat": data["p_hat"].tolist(),
                "m": float(data["m_total"]),
                "n_eff": float(data["n_eff"]),
                "local_loss": float(loss),
                "update_vector_hash": sha256_json(update.tolist()),
            })
        stages.mark("local", STAGE_LOCAL)

        # Freeze q̂_use from pre-U features on B_r (do not form A_r yet).
        q_hat_map = self._freeze_q_hat_map(list(client_data.keys()), client_data)
        stages.mark("q_use_freeze", STAGE_Q_USE_FREEZE)

        # Realize U → A_r = B_r ∩ U_r
        a_r_clients = [
            rec.client_id for rec in window_slice.records
            if rec.U == 1 and rec.client_id in e_r_clients
        ]
        u_r_clients = [
            rec.client_id for rec in window_slice.records if rec.U == 1
        ]
        stages.mark("U", STAGE_U)

        def _run_counterfactual() -> dict[str, Any]:
            tar_n, tar_c = self._target_coverage(window_slice)
            audit_obj = audit_design_vs_nodesign(
                registered=[rec.client_id for rec in window_slice.records],
                attempted=attempted_clients,
                usable={rec.client_id: int(rec.U) for rec in window_slice.records},
                O={cid: data["record"].O for cid, data in client_data.items()},
                groups={
                    cid: np.asarray(data["record"].target_groups, dtype=np.int64)
                    for cid, data in client_data.items()
                },
                zeta_d={cid: data["zeta_d"] for cid, data in client_data.items()},
                p_hat={cid: data["p_hat"] for cid, data in client_data.items()},
                q_hat=q_hat_map,
                variance={cid: float(self.variance_state.get(cid, 1.0)) for cid in client_data},
                target_positive_count=tar_n,
                target_covered_count=tar_c,
                a_max=self.a_max,
                p_min=self.p_min,
                d_max=self.d_max,
                q_min=self.q_min,
                num_groups=self.num_groups,
            )
            return audit_obj.as_dict()

        if not a_r_clients:
            stages.mark("P2", STAGE_P2)
            audit = _run_counterfactual()
            self._record_sag_window(
                window_id=window_id,
                g_r=g_r,
                stages=stages,
                cert_inputs=cert_inputs,
                fallback_reason=fallback_reason,
                gate_passed=gate_passed,
                b_r=b_r_clients,
                a_r=[],
                u_r=u_r_clients,
                m_by_client={cid: float(client_data[cid]["m_total"]) for cid in b_r_clients},
                audit=audit,
                p2_invoked=False,
                extras=self._policy_extras(client_data),
            )
            # U=0 attempts are still valid labels for future opportunity/p/q
            # estimators.  Update only after all current-window predictions and
            # local work are complete.
            self.clock.skip_empty_window()
            self._update_lagged_estimators(window_slice, client_data)
            self.model_versions[self.clock.model_version] = copy.deepcopy(self.theta)
            after_hash = self._theta_hash()
            return WindowMetrics(
                window_id=window_id,
                active=False,
                alpha=[],
                beta_hat=[],
                theta_hash_before=before_hash,
                theta_hash_after=after_hash,
                debt_l1=float(np.linalg.norm(self.debt, ord=1)),
                omega=[],
                active_clients=[],
                n_eff_values=[],
                clip_rate_stage1=0.0,
                clip_rate_stage2=0.0,
                train_loss=0.0,
                e_r_size=len(e_r_clients),
                a_r_size=0,
                b_r_size=len(b_r_clients),
                g_r=int(g_r),
            )

        # Step 8: Compute method-specific alpha
        n_active = len(a_r_clients)
        raw_counts = np.array([
            float(np.sum(client_data[cid]["record"].O)) if cid in client_data
            else 1.0
            for cid in a_r_clients
        ], dtype=np.float64)
        corrected_masses = np.array([
            client_data[cid]["m_total"] if cid in client_data else 1.0
            for cid in a_r_clients
        ], dtype=np.float64)

        compositions_mat = np.zeros((self.num_groups, n_active), dtype=np.float64)
        for i, cid in enumerate(a_r_clients):
            if cid in client_data:
                compositions_mat[:, i] = client_data[cid]["c_g"]
            else:
                compositions_mat[:, i] = 1.0 / self.num_groups

        # Stage 2: frozen q → d → b → beta_hat
        q_hat = np.zeros(n_active, dtype=np.float64)
        for i, cid in enumerate(a_r_clients):
            q_hat[i] = float(q_hat_map.get(cid, 0.5))

        d_w = (
            d_weight(q_hat, d_max=self.d_max, q_min=self.q_min)
            if self.policy.uses_usable_ipw
            else np.ones(n_active, dtype=np.float64)
        )
        b = two_stage_mass(corrected_masses, d_w)
        beta = beta_hat(b)
        clip_stage2 = float(np.mean(np.abs(d_w) >= self.d_max))

        raw_staleness = np.array([
            client_data[cid]["record"].tau if cid in client_data else 0.0
            for cid in a_r_clients
        ], dtype=np.float64)
        staleness = raw_staleness / float(max(int(self.s_max), 1))
        if bool(np.any((staleness < 0.0) | (staleness > 1.0))):
            raise RuntimeError("normalized staleness must be in [0, 1]")

        lagged_s2 = np.array([
            self.variance_state.get(cid, 1.0) for cid in a_r_clients
        ], dtype=np.float64)
        variance_cold_start = np.array([
            self.variance_count.get(cid, 0) == 0 for cid in a_r_clients
        ], dtype=bool)
        variance_diag = np.array([
            lagged_s2[i] / max(float(client_data[cid]["n_eff"]), 1.0)
            + self.v_floor
            for i, cid in enumerate(a_r_clients)
        ], dtype=np.float64)
        variance_diag = np.where(np.isfinite(variance_diag), variance_diag, 1.0 + self.v_floor)
        variance_diag = np.maximum(variance_diag, self.v_floor)
        covered_time_slots = {
            cid: [
                int(unit.time_index)
                for unit_id in client_data[cid]["record"].observed_unit_ids
                for unit in [self.dataset.get_atomic_by_id(unit_id)]
                if unit is not None
            ]
            for cid in a_r_clients
        }

        payload = WindowAggregateInput(
            client_ids=a_r_clients,
            raw_counts=raw_counts,
            total_masses=corrected_masses,
            compositions=compositions_mat,
            beta_hat=beta,
            staleness=staleness,
            variance_diag=variance_diag,
            debt=(
                self.debt if self.policy.uses_debt
                else np.zeros(self.num_groups, dtype=np.float64)
            ),
            mu=self.mu,
            extras={
                "covered_time_slots": covered_time_slots,
                "participation_rate": self._lagged_participation_rates(a_r_clients),
                "observation_rate": self._client_observation_rates(
                    a_r_clients, client_data,
                ),
            },
        )

        # Always invoke the method aggregator. Instantaneous calibration is
        # ablated inside RavenWoInstAggregator (λ_g=0, λ_β=1e-8) rather than by
        # skipping P2; skipping previously invalidated raven_wo_inst evidence.
        alpha = self.aggregator.compute_server_weights(payload)
        if abs(float(alpha.sum()) - 1.0) > 1e-8:
            alpha = alpha / alpha.sum()
        stages.mark("P2", STAGE_P2)

        # Step 9: ONE global update
        theta_flat = flatten_params(self.theta)
        for i, cid in enumerate(a_r_clients):
            if cid in local_updates and len(local_updates[cid]) > 0:
                theta_flat = theta_flat - float(self.eta) * alpha[i] * local_updates[cid]

        self.theta = unflatten_params(theta_flat, self.theta)
        self.model.load_state_dict(self.theta)
        new_version = self.clock.apply_server_update()
        self.model_versions[new_version] = copy.deepcopy(self.theta)

        # Step 10: Update debt
        omega = coverage_mix(compositions_mat, alpha)
        if self.policy.uses_debt:
            self.debt = update_debt(
                self.debt, mu=self.mu, omega=omega, eta=float(self.eta), active=True,
            )
        self.scale += float(self.eta)
        self.omega_sum = self.omega_sum + float(self.eta) * omega

        # Step 12: Update opportunity/p/q/variance state AFTER window close
        self._update_lagged_estimators(window_slice, client_data)
        self._update_variance_state(local_updates, a_r_clients)

        after_hash = self._theta_hash()
        by_client = {row["client_id"]: row for row in self.diagnostics if row["window_id"] == window_id}
        timealign_rows = {
            str(row["client_id"]): row
            for row in (
                self.aggregator.diagnostics_history[-1]
                if getattr(self.aggregator, "diagnostics_history", [])
                else []
            )
        }
        for i, cid in enumerate(a_r_clients):
            if cid in by_client:
                by_client[cid].update({
                    "q_hat": float(q_hat[i]),
                    "beta_hat": float(beta[i]),
                    "alpha": float(alpha[i]),
                    "raw_tau": float(raw_staleness[i]),
                    "normalized_tau": float(staleness[i]),
                    "lagged_S2": float(lagged_s2[i]),
                    "variance_proxy": float(variance_diag[i]),
                    "cold_start": bool(variance_cold_start[i]),
                    "update_norm": float(np.linalg.norm(local_updates[cid])),
                    "variance_state_updated_after_close": True,
                    "global_model_hash": after_hash,
                })
                if cid in timealign_rows:
                    by_client[cid].update({
                        **timealign_rows[cid],
                        "model_hash_before": before_hash,
                        "model_hash_after": after_hash,
                        "tau": float(raw_staleness[i]),
                        "sample_count": float(raw_counts[i]),
                    })

        n_eff_values = [
            client_data[cid]["n_eff"] for cid in a_r_clients if cid in client_data
        ]
        clip_s1 = float(np.mean([
            client_data[cid]["clip_stage1"] for cid in e_r_clients if cid in client_data
        ])) if e_r_clients else 0.0

        avg_train_loss = float(np.mean(list(train_losses.values()))) if train_losses else 0.0

        audit = _run_counterfactual()
        self._record_sag_window(
            window_id=window_id,
            g_r=g_r,
            stages=stages,
            cert_inputs=cert_inputs,
            fallback_reason=fallback_reason,
            gate_passed=gate_passed,
            b_r=b_r_clients,
            a_r=a_r_clients,
            u_r=u_r_clients,
            m_by_client={cid: float(client_data[cid]["m_total"]) for cid in b_r_clients},
            audit=audit,
            p2_invoked=True,
            extras=self._policy_extras(client_data),
        )

        return WindowMetrics(
            window_id=window_id,
            active=True,
            alpha=alpha.tolist(),
            beta_hat=beta.tolist(),
            theta_hash_before=before_hash,
            theta_hash_after=after_hash,
            debt_l1=float(np.linalg.norm(self.debt, ord=1)),
            omega=omega.tolist(),
            active_clients=a_r_clients,
            n_eff_values=n_eff_values,
            clip_rate_stage1=clip_s1,
            clip_rate_stage2=clip_stage2,
            train_loss=avg_train_loss,
            e_r_size=len(e_r_clients),
            a_r_size=len(a_r_clients),
            b_r_size=len(b_r_clients),
            g_r=int(g_r),
        )

    def _update_lagged_estimators(
        self,
        window_slice: WindowDataSlice,
        client_data: dict[str, dict],
    ) -> None:
        """Update opportunity/propensity estimators using window-completed data."""
        opportunity_counts: Counter[tuple[str, str]] = Counter()
        for rec in window_slice.records:
            cid = rec.client_id
            # FedAU frequency counts: registration attempt vs usable update.
            # Must run after aggregation so the current window stays pre-outcome.
            self._fedau_attempt_count[cid] = self._fedau_attempt_count.get(cid, 0.0) + 1.0
            if int(rec.attempted) == 1 and int(rec.U) == 1:
                self._fedau_usable_count[cid] = self._fedau_usable_count.get(cid, 0.0) + 1.0
            opportunity_counts.update(
                (str(cid), str(stratum))
                for stratum in rec.opportunity_strata
            )
            if cid not in client_data:
                continue
            # Update observation propensity
            if self.obs_propensity is not None and len(rec.risk_set_unit_ids) > 0:
                features = np.asarray([
                    [
                        1.0,
                        self._hour_block(stratum),
                        float(np.log1p(rec.planned_workload_pre)),
                    ]
                    for stratum in rec.opportunity_strata
                ], dtype=np.float64)
                prediction_version = self.p_model_version
                self.obs_propensity.update_records_after_completion(
                    features, rec.O,
                )
                for index, unit_id in enumerate(rec.risk_set_unit_ids):
                    self.p_propensity_history.append({
                        "client_id": cid,
                        "window_id": rec.window_id,
                        "unit_id": str(unit_id),
                        "opportunity_stratum": rec.opportunity_strata[index],
                        "bias": float(features[index, 0]),
                        "hour_block": float(features[index, 1]),
                        "planned_workload_pre": float(features[index, 2]),
                        "O": int(rec.O[index]),
                        "prediction_time": float(rec.registration_time),
                        "update_time": float(rec.window_close_time),
                        "model_version": prediction_version,
                        "source_split": "train",
                    })
                self.p_model_version += 1
            if self.usable_propensity is not None:
                q_features = np.array([
                    1.0,
                    float(rec.model_age),
                    0.0,
                    0.0,
                    deadline_slack_pre(
                        rec.window_close_time, rec.registration_time,
                    ),
                ])
                q_hat = float(self.usable_propensity.predict(q_features))
                included = bool(rec.attempted == 1)
                audit_row = {
                    "client_id": cid,
                    "window_id": rec.window_id,
                    "risk_set_size_pre": rec.risk_set_size_pre,
                    "observed_count": rec.observed_count,
                    "attempted": rec.attempted,
                    "U": rec.U,
                    "usable": int(rec.attempted == 1 and rec.U == 1),
                    "attempt_failure": rec.attempt_failure,
                    "non_attempt": rec.non_attempt,
                    "model_age": float(rec.model_age),
                    "deadline_slack_pre": float(q_features[-1]),
                    "prediction_time": float(rec.registration_time),
                    "update_time": float(rec.window_close_time),
                    "q_hat": q_hat,
                    "model_version": self.q_model_version,
                    "included_in_q_training": included,
                    "exclusion_reason": (
                        None if included else "no_observation_buffer"
                    ),
                }
                self.q_attempt_diagnostics.append(audit_row)
                if included:
                    self.usable_propensity.update_lagged(
                        q_features, float(rec.U),
                    )
                    self.q_propensity_history.append(dict(audit_row))
                    self.q_model_version += 1
        if self.opportunity_estimator is not None:
            self.opportunity_estimator.update_window(
                window_slice.window_id, opportunity_counts,
            )

    def _update_variance_state(
        self,
        local_updates: dict[str, np.ndarray],
        a_r_clients: list[str],
    ) -> None:
        """Update EMA dispersion only after current aggregation has closed."""
        for cid in a_r_clients:
            if cid not in local_updates:
                continue
            update = np.asarray(local_updates[cid], dtype=np.float64)
            if not np.all(np.isfinite(update)):
                continue
            previous_mean = self.variance_mean.get(
                cid, np.zeros_like(update),
            )
            if previous_mean.shape != update.shape:
                raise RuntimeError("variance mean/update shape mismatch")
            deviation = float(np.mean(np.square(update - previous_mean)))
            if not np.isfinite(deviation):
                continue
            previous_s2 = self.variance_state.get(cid, 1.0)
            decay = float(self.variance_decay)
            self.variance_state[cid] = (
                decay * previous_s2 + (1.0 - decay) * deviation
            )
            self.variance_mean[cid] = decay * previous_mean + (
                1.0 - decay
            ) * update
            self.variance_count[cid] = self.variance_count.get(cid, 0) + 1

    def omega_bar(self) -> np.ndarray:
        if self.scale <= 0:
            raise RuntimeError("No active windows accumulated")
        return self.omega_sum / self.scale


def build_full_runner(
    trace: EventTrace,
    dataset: ProcessedDataset,
    *,
    method: str = "raven",
    n_groups: int | None = None,
    model_seed: int = 26001,
    learning_rate: float = 0.01,
    local_steps: int = 5,
    device: str = "cpu",
    target_mu: np.ndarray | None = None,
    pi_target: dict[tuple[str, str], float] | None = None,
    s_max: int | None = None,
    a_max: float = 20.0,
    p_min: float = 0.05,
    pi_min: float = 1e-6,
    d_max: float = 10.0,
    q_min: float = 0.05,
    use_coarse_time_groups: bool = False,
    pi_opp_joint: dict[tuple[str, str], float] | None = None,
) -> FullWindowRunner:
    """Build a FullWindowRunner for end-to-end training."""
    if n_groups is None:
        n_groups = dataset.num_groups

    if target_mu is None:
        atomic = dataset.atomic_df.copy()
        if n_groups == 4:
            atomic["target_group_main"] = RepeatableTimeOfDayMapper().map(atomic)
        else:
            atomic["target_group_main"] = pd.Categorical(
                atomic["target_group"],
            ).codes
        target = TargetBuilder(
            group_mapper=GroupMapper("target_group_main"),
        ).build(atomic, split="test")
        target_mu = np.asarray([
            float(target.group_mass.get(str(group), 0.0))
            for group in range(n_groups)
        ], dtype=np.float64)
    mu = np.asarray(target_mu, dtype=np.float64)
    if len(mu) != n_groups or abs(float(mu.sum()) - 1.0) > 1e-12:
        raise ValueError("target_mu must be normalized with n_groups entries")
    if pi_target is None:
        atomic_for_pi = dataset.atomic_df.copy()
        if n_groups == 4:
            atomic_for_pi["target_group_main"] = (
                RepeatableTimeOfDayMapper().map(atomic_for_pi)
            )
        unit_station = atomic_for_pi.set_index("unit_id")[
            "spatial_id"
        ].astype(str).to_dict()
        station_to_client: dict[str, str] = {}
        for event in trace.events.itertuples():
            client = str(event.client_id)
            for unit_id in event.risk_set_unit_ids:
                station = unit_station[str(unit_id)]
                previous = station_to_client.setdefault(station, client)
                if previous != client:
                    raise ValueError(
                        "trace station maps to multiple clients",
                    )
        pi_frame = build_pi_target(
            atomic_for_pi, station_to_client, split="test",
        )
        pi_target = {
            (str(row.client_id), str(row.opportunity_stratum)): float(
                row.pi_k_s_tar,
            )
            for row in pi_frame.itertuples()
        }
    model = deterministic_common_ndmf(dataset.num_spatial, seed=model_seed)
    aggregator = get_aggregator(method)
    policy = get_method_policy(method)

    return FullWindowRunner(
        trace=trace,
        dataset=dataset,
        model=model,
        aggregator=aggregator,
        policy=policy,
        mu=mu,
        num_groups=n_groups,
        learning_rate=learning_rate,
        local_steps=local_steps,
        a_max=float(a_max),
        p_min=float(p_min),
        pi_min=float(pi_min),
        d_max=float(d_max),
        q_min=float(q_min),
        pi_target=dict(pi_target or {}),
        s_max=int(s_max if s_max is not None else trace.metadata.s_max),
        use_coarse_time_groups=bool(use_coarse_time_groups),
        pi_opp_joint=dict(pi_opp_joint or {}),
        seed=model_seed,
        device=device,
    )

"""Full training pipeline WindowRunner — real Common-NDMF training (P10).

Each window:
 1. Read theta_r and model version
 2. Read risk sets from EventTrace
 3. Compute lagged estimators (opportunity/p/q)
 4. Construct B_{k,r} for each client
 5. Form E_r (all clients with m > 0) BEFORE reading U
 6. Execute local SGD for each client with downloaded checkpoint
 7. Read U from EventTrace → form A_r
 8. Active window: compute method-specific alpha
 9. ONE global update
10. Update debt
11. Save window metrics
12. After window close: update opportunity/p/q/variance state
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
        """Compute zeta_hat for a client's risk set records."""
        if self.opportunity_estimator is None:
            return np.ones(len(stratum_ids), dtype=np.float64)

        pi_hat_opp = np.array([
            self.opportunity_estimator.pi_hat().get((client_id, s), self.p_min)
            for s in stratum_ids
        ], dtype=np.float64)

        if not self.pi_target:
            raise RuntimeError("frozen pi target is required for official correction")
        missing = [
            (client_id, str(s)) for s in stratum_ids
            if (client_id, str(s)) not in self.pi_target
        ]
        if missing:
            raise RuntimeError(f"pi target lacks opportunity support: {missing[:3]}")
        pi_tar = np.array([
            self.pi_target[(client_id, str(s))] for s in stratum_ids
        ], dtype=np.float64)

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

        # Step 2: Read risk sets from EventTrace
        coarse_groups = self.num_groups if self.num_groups in {4, 8} else None
        window_slice = extract_window_slice(
            window_id, events, self.dataset, coarse_time_groups=coarse_groups,
        )

        if not window_slice.records:
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
            )

        # Step 3-4: Compute first-stage weights and form E_r
        client_data: dict[str, dict] = {}
        for rec in window_slice.records:
            cid = rec.client_id

            # Compute zeta_hat for this client's records
            zeta = self._compute_zeta(cid, rec.opportunity_strata)

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
            p_hat = self._compute_p_hat(features_list)

            # Stage 1: a = min(a_max, zeta_hat / max(p_hat, p_min))
            a_raw = raw_weights(zeta, p_hat, a_max=self.a_max, p_min=self.p_min)

            # Compute group masses m_{k,r,g}
            m_g = group_mass(rec.O, a_raw, np.array(rec.target_groups), n_groups=self.num_groups)
            m_total = total_mass(m_g)

            # Compute a_bar (Hajek normalized)
            a_bar = normalized_weights(rec.O, a_raw, m_total)

            # Compute composition from records
            c_g = composition(m_g, m_total)

            # Compute n_eff
            n_eff = effective_sample_size(rec.O, a_raw, total_mass=m_total)

            client_data[cid] = {
                "record": rec,
                "zeta": zeta,
                "p_hat": p_hat,
                "a_raw": a_raw,
                "a_bar": a_bar,
                "m_g": m_g,
                "m_total": m_total,
                "c_g": c_g,
                "n_eff": n_eff,
                "clip_stage1": float(np.mean(np.abs(a_raw) >= self.a_max)),
            }

        # Step 5: E_r = all clients with m > 0 (BEFORE reading U)
        e_r_clients = [
            cid for cid, data in client_data.items()
            if data["m_total"] > 0
        ]
        attempted_clients = [
            rec.client_id for rec in window_slice.records if rec.attempted == 1
        ]
        if set(e_r_clients) != set(attempted_clients):
            raise RuntimeError("E_r must equal the frozen attempted set")
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
            for i, (uid, obs_val) in enumerate(zip(rec.observed_unit_ids, rec.observed_values)):
                unit = self.dataset.get_atomic_by_id(uid)
                if unit is not None:
                    observed_records.append({
                        "spatial_id": unit.spatial_id,
                        "absolute_time": unit.absolute_time,
                        "time_index": unit.time_index,
                        "observed_value": obs_val,
                        "spatial_to_idx": {sid: i for i, sid in enumerate(
                            self.dataset.atomic_df["spatial_id"].unique())},
                        "total_time_slots": int(self.dataset.atomic_df["time_index"].max()) + 1,
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
            local_updates[cid] = update
            train_losses[cid] = loss
            raw_local = np.ones(len(observed_records), dtype=np.float64)
            raw_local /= max(len(observed_records), 1)
            self.diagnostics.append({
                "window_id": window_id,
                "client_id": cid,
                "raw_local_weights": raw_local.tolist(),
                "hajek_local_weights": data["a_bar"][obs_mask].tolist(),
                "applied_local_weights": a_bar_observed.tolist(),
                "zeta_hat": data["zeta"].tolist(),
                "p_hat": data["p_hat"].tolist(),
                "m": float(data["m_total"]),
                "n_eff": float(data["n_eff"]),
                "local_loss": float(loss),
                "update_vector_hash": sha256_json(update.tolist()),
            })

        # Step 7: Read U → form A_r
        a_r_clients = [
            rec.client_id for rec in window_slice.records
            if rec.U == 1 and rec.client_id in e_r_clients
        ]

        if not a_r_clients:
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

        # Stage 2: q → d → b → beta_hat
        q_hat = np.array([
            self.usable_propensity.predict(
                np.array([
                    1.0,
                    client_data[cid]["record"].model_age if cid in client_data else 0.0,
                    0.0,
                    0.0,
                    deadline_slack_pre(
                        client_data[cid]["record"].window_close_time,
                        client_data[cid]["record"].registration_time,
                    ) if cid in client_data else 0.0,
                ])
            )
            if self.usable_propensity is not None else 0.5
            for cid in a_r_clients
        ], dtype=np.float64)

        d_w = d_weight(q_hat, d_max=self.d_max, q_min=self.q_min)
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
            debt=self.debt,
            mu=self.mu,
            extras={"covered_time_slots": covered_time_slots},
        )

        alpha = self.aggregator.compute_server_weights(payload)
        if abs(float(alpha.sum()) - 1.0) > 1e-8:
            alpha = alpha / alpha.sum()

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
            previous_mean = self.variance_mean.get(
                cid, np.zeros_like(update),
            )
            if previous_mean.shape != update.shape:
                raise RuntimeError("variance mean/update shape mismatch")
            deviation = float(np.mean(np.square(update - previous_mean)))
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
        seed=model_seed,
        device=device,
    )

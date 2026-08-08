"""Traffic real-runner canary: EventTrace bridge + training orchestration."""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch
import yaml

from raven_mcs.data.base import DatasetMetadata
from raven_mcs.data.processed_dataset import AtomicUnit, ProcessedDataset
from raven_mcs.e2.traffic_balanced_canary import (
    N_CLIENTS,
    N_WINDOWS,
    build_traffic_schedule,
    load_traffic_targets,
    sha256_file,
)
from raven_mcs.e2.traffic_profiles import SCENARIO_ORDER, load_direction_registry
from raven_mcs.e2.traffic_profiles.runner_consistency import (
    PROB_BOUNDS,
    run_frozen_hard_trace,
)
from raven_mcs.metrics.accuracy import gap_mis, rmse_mu, rmse_rho, tail_head_rmse
from raven_mcs.simulation.event_trace import (
    EventTrace,
    EventTraceMetadata,
    freeze_event_trace,
    load_event_trace,
)
from raven_mcs.training.window_runner import build_full_runner
from raven_mcs.utils.serialization import dump_json

CANARY_SEED = 29001
METHODS = (
    "fedavg_window",
    "fedasync_window",
    "flamf_timealign_adapted",
    "twostage_hajek",
    "raven",
)
METHOD_DISPLAY = {
    "fedavg_window": "FedAvg",
    "fedasync_window": "FedAsync",
    "flamf_timealign_adapted": "TimeAlign",
    "twostage_hajek": "TwoStage",
    "raven": "RAVEN",
}
S_MAX = 5
LOCAL_STEPS = 2
N_GROUPS = 4
SELECTED_STRENGTH = "PROFILE-S1"


def traffic_dataset(root: Path) -> "TrafficRunnerDataset":
    return TrafficRunnerDataset(root)


class TrafficRunnerDataset(ProcessedDataset):
    """ProcessedDataset with station=client measurements and public-target strata."""

    def __init__(self, root: Path) -> None:
        metadata = DatasetMetadata(
            dataset="traffic",
            target_name="average_speed",
            target_unit="km_per_h",
            spatial_unit="traffic_station",
            time_unit="hour",
            source_name="Traffic dense MCS matrix",
            source_url="https://local.traffic.protocol/e2",
            raw_license="research-internal",
            filtering_rules=("Dense 43x720 protocol matrix",),
        )
        metadata.validate()
        # Build station-as-client measurements before parent init by writing temp
        data_dir = root / "data/processed/traffic"
        atomic = pd.read_parquet(data_dir / "atomic_units.parquet")
        # Overlay public-target strata/groups for protocol units
        pub = pd.read_parquet(
            root / "configs/frozen/e2_traffic_public_target/atomic_public_target.parquet"
        )
        pub_map = {
            str(r.unit_id): {
                "opportunity_stratum": str(r.opportunity_stratum),
                "target_group": str(r.target_group),
                "station_id": str(r.station_id),
            }
            for r in pub.itertuples(index=False)
        }
        self._public_unit_meta = pub_map
        # Materialize station-client measurements into a sidecar used by parent
        meas_path = root / "outputs/e2_traffic_real_runner_canary/_traffic_station_measurements.parquet"
        meas_path.parent.mkdir(parents=True, exist_ok=True)
        if not meas_path.is_file():
            rows = []
            for r in atomic.itertuples(index=False):
                rows.append({
                    "client_id": str(r.spatial_id),
                    "unit_id": str(r.unit_id),
                    "potential_measurement": float(r.target_value),
                    "controlled_generator_parameters": "{}",
                    "split": str(r.split),
                    "source_trace_id": f"station::{r.spatial_id}::{r.unit_id}",
                })
            pd.DataFrame(rows).to_parquet(meas_path, index=False)
        # Point ProcessedDataset at a temp dir with rewritten client_measurements
        staging = root / "outputs/e2_traffic_real_runner_canary/_traffic_dataset_staging"
        staging.mkdir(parents=True, exist_ok=True)
        atomic_out = staging / "atomic_units.parquet"
        client_out = staging / "client_measurements.parquet"
        if not atomic_out.is_file():
            # rewrite target_group/opportunity_stratum for protocol units
            atomic2 = atomic.copy()
            for i, row in atomic2.iterrows():
                uid = str(row["unit_id"])
                if uid in pub_map:
                    atomic2.at[i, "opportunity_stratum"] = pub_map[uid]["opportunity_stratum"]
                    atomic2.at[i, "target_group"] = pub_map[uid]["target_group"]
            atomic2.to_parquet(atomic_out, index=False)
        if not client_out.is_file() or client_out.stat().st_mtime < meas_path.stat().st_mtime:
            import shutil
            shutil.copy2(meas_path, client_out)
        super().__init__(staging, metadata)
        # Force 4 protocol groups block0..block3 encoding
        self._target_group_str_to_int = {
            "block0": 0, "block1": 1, "block2": 2, "block3": 3,
        }
        self.num_groups = 4
        self._target_groups = [0, 1, 2, 3]
        # Traffic raw targets explode CommonNDMF + frozen lr=0.01.
        # Apply train-split z-score so frozen hyperparameters remain usable.
        self._apply_train_standardization()

    def _apply_train_standardization(self) -> None:
        mean = float(self.target_mean)
        std = float(self.target_std)
        self._client_df = self._client_df.copy()
        self._client_df["potential_measurement"] = (
            self._client_df["potential_measurement"].astype(float) - mean
        ) / std
        self._atomic_df = self._atomic_df.copy()
        self._atomic_df["target_value"] = (
            self._atomic_df["target_value"].astype(float) - mean
        ) / std
        self._measurement_index = {
            (str(row["client_id"]), str(row["unit_id"])): float(
                row["potential_measurement"],
            )
            for _, row in self._client_df.iterrows()
        }
        self._atomic_df = self._atomic_df.reset_index(drop=True)
        self._unit_id_to_row = {
            str(uid): i for i, uid in enumerate(self._atomic_df["unit_id"].astype(str))
        }

    def get_atomic_by_id(self, unit_id: str) -> AtomicUnit | None:
        unit = super().get_atomic_by_id(unit_id)
        if unit is None:
            return None
        meta = self._public_unit_meta.get(str(unit_id))
        if meta is None:
            return unit
        return AtomicUnit(
            unit_id=unit.unit_id,
            spatial_id=unit.spatial_id,
            absolute_time=unit.absolute_time,
            time_index=unit.time_index,
            target_value=unit.target_value,
            split=unit.split,
            target_group=int(self._target_group_str_to_int[meta["target_group"]]),
            opportunity_stratum=meta["opportunity_stratum"],
            public_features=unit.public_features,
            support_flag=unit.support_flag,
        )


def load_profile_s1_registry(root: Path) -> dict[str, Any]:
    path = root / "configs/frozen/e2_traffic_profiles_s1/traffic_s1_s6_profile_registry.json"
    return json.loads(path.read_text(encoding="utf-8"))


def scenario_params_from_registry(registry: dict[str, Any], scenario_id: str) -> dict[str, Any]:
    sc = registry["scenarios"][scenario_id]
    return {
        "scenario_id": scenario_id,
        "a_opp": float(sc["a_opp"]),
        "a_obs": float(sc["a_obs"]),
        "a_q": float(sc["a_q"]),
        "kappa_opp": float(sc["kappa_opp"]),
        "kappa_obs": float(sc["kappa_obs"]),
        "kappa_q": float(sc["kappa_q"]),
        "d_opp": int(sc["d_opp"]),
        "d_p": int(sc["d_p"]),
        "d_q": int(sc["d_q"]),
        "profile_id": SELECTED_STRENGTH,
        "bounds": {
            "opp": list(PROB_BOUNDS["opp"]),
            "obs": list(PROB_BOUNDS["obs"]),
            "q": list(PROB_BOUNDS["q"]),
        },
    }


def load_pi_target_traffic(root: Path) -> dict[tuple[str, str], float]:
    cs = pd.read_parquet(
        root / "configs/frozen/e2_traffic_public_target/client_stratum_target.parquet"
    )
    return {
        (str(r.client_id), str(r.stratum_id)): float(r.pi_k_s_tar)
        for r in cs.itertuples(index=False)
    }


def load_target_mu_traffic(root: Path) -> np.ndarray:
    tg = pd.read_parquet(
        root / "configs/frozen/e2_traffic_public_target/target_group_mass.parquet"
    )
    order = ["block0", "block1", "block2", "block3"]
    mu = tg.set_index("target_group")["mu_g"]
    return np.asarray([float(mu[g]) for g in order], dtype=np.float64)


def hard_to_eventtrace(
    *,
    opp: pd.DataFrame,
    obs: pd.DataFrame,
    usable: pd.DataFrame,
    seed: int,
    scenario_id: str,
    s_max: int = S_MAX,
) -> EventTrace:
    """Convert hard A/O/U tables into training EventTrace rows."""
    rng = np.random.default_rng(int(seed) + 17)
    obs_sel = obs.loc[obs["observed"]].copy()
    obs_by_cw = {
        (int(w), str(c)): g["unit_id"].astype(str).tolist()
        for (w, c), g in obs_sel.groupby(["window_id", "client_id"], sort=False)
    }
    o_prob = {
        (int(r.window_id), str(r.client_id), str(r.unit_id)): float(r.observation_probability)
        for r in obs.itertuples(index=False)
    }
    use_by_cw = {}
    q_by_cw = {}
    for r in usable.itertuples(index=False):
        key = (int(r.window_id), str(r.client_id))
        use_by_cw[key] = bool(r.U) if bool(r.stage2_eligible) else False
        q_by_cw[key] = float(r.q_use) if pd.notna(r.q_use) else 0.6

    rows = []
    for (wid, cid), g in opp.groupby(["window_id", "client_id"], sort=True):
        wid = int(wid)
        cid = str(cid)
        risk = g["unit_id"].astype(str).tolist()
        # Opportunity-selected units form the risk set for training
        selected = g.loc[g["opportunity_selected"], "unit_id"].astype(str).tolist()
        risk_set = selected if selected else []
        observed = [u for u in obs_by_cw.get((wid, cid), []) if u in set(risk_set)]
        o_flags = {u: (u in set(observed)) for u in risk_set}
        attempted = int(len(observed) > 0)
        max_tau = min(s_max, wid)
        tau = int(rng.integers(0, max_tau + 1)) if max_tau >= 0 else 0
        u_raw = bool(use_by_cw.get((wid, cid), False))
        # EventTrace rule: U=1 requires attempted and tau<=s_max
        usable_flag = bool(u_raw and attempted and tau <= s_max)
        oracle_p = float(np.mean([
            o_prob.get((wid, cid, u), 0.2) for u in risk_set
        ])) if risk_set else 0.2
        oracle_q = float(q_by_cw.get((wid, cid), 0.6))
        rows.append({
            "window_id": wid,
            "client_id": cid,
            "risk_set_unit_ids": risk_set,
            "opportunity_features": {
                "hour_block": int(wid % 4),
                "client_bias": float(hash(cid) % 1000) / 1000.0,
            },
            "observed_unit_ids": observed,
            "O": o_flags,
            "registration_time": float(wid) + 0.01,
            "downloaded_version": int(wid - tau),
            "model_age": int(tau),
            "tau": int(tau),
            "device_profile": "traffic-station",
            "network_profile": "traffic-canary",
            "compute_success": True,
            "compute_duration": 0.2,
            "network_success": True,
            "network_duration": 0.1,
            "arrival_time": float(wid) + 0.5,
            "U": usable_flag,
            "risk_set_size_pre": len(risk_set),
            "observed_count": len(observed),
            "attempted": attempted,
            "usable": usable_flag,
            "attempt_failure": int(attempted == 1 and not usable_flag),
            "non_attempt": int(attempted == 0),
            "planned_workload_pre": float(len(risk_set)),
            "raw_workload": float(len(observed)),
            "oracle_p": max(oracle_p, 1e-6),
            "oracle_q": max(oracle_q, 1e-6),
            "hidden_confounder": 0.0,
        })
    # Ensure every window has all clients represented (even empty risk sets)
    # Already grouped from opp which has all exposures.
    trace = EventTrace(
        events=pd.DataFrame(rows),
        metadata=EventTraceMetadata(
            dataset="traffic",
            seed=int(seed),
            num_windows=N_WINDOWS,
            num_clients=N_CLIENTS,
            s_max=int(s_max),
            generator="traffic-profile-s1-hard-aou-bridge-v1",
            notes=(f"scenario={scenario_id}", "PROFILE-S1", "station=client"),
        ),
    )
    # Drop rows with empty risk sets from training participation but keep schema:
    # FullWindowRunner tolerates empty risk sets; EventTrace validate allows them.
    # Filter: EventTrace requires oracle_p/q > 0 even for empty — already set.
    # Empty risk set rows: U must be 0
    ev = trace.events
    empty = ev["risk_set_unit_ids"].map(len) == 0
    ev.loc[empty, "U"] = False
    ev.loc[empty, "usable"] = False
    ev.loc[empty, "attempted"] = 0
    trace = EventTrace(events=ev, metadata=trace.metadata, extras={"scenario_id": scenario_id})
    trace.validate()
    return trace


def generate_scenario_eventtrace(
    root: Path,
    *,
    scenario_id: str,
    label: str,
    registry: dict[str, Any],
    schedule: dict[str, Any],
    unit_meta: dict[str, Any],
    out_dir: Path,
    seed: int = CANARY_SEED,
) -> dict[str, Any]:
    params = scenario_params_from_registry(registry, scenario_id)
    hard_dir = out_dir / "hard"
    result = run_frozen_hard_trace(
        seed=int(seed),
        schedule=schedule,
        unit_meta=unit_meta,
        params=params,
        output_dir=hard_dir,
    )
    opp = pd.read_parquet(hard_dir / "opportunity_events.parquet")
    obs = pd.read_parquet(hard_dir / "observation_events.parquet")
    usable = pd.read_parquet(hard_dir / "usable_events.parquet")
    trace = hard_to_eventtrace(
        opp=opp, obs=obs, usable=usable, seed=int(seed), scenario_id=scenario_id,
    )
    train_dir = out_dir / "training_eventtrace"
    identity = freeze_event_trace(trace, train_dir)
    # hash hard arrival for cross-method identity
    arr_hash = sha256_file(hard_dir / "hard_arrival_events.parquet")
    payload = {
        "scenario_id": scenario_id,
        "label": label,
        "seed": int(seed),
        "profile_id": SELECTED_STRENGTH,
        "eventtrace_identity": identity,
        "hard_arrival_sha256": arr_hash,
        "training_eventtrace_dir": train_dir.relative_to(root).as_posix(),
        "hard_dir": hard_dir.relative_to(root).as_posix(),
        "n_event_rows": int(len(trace.events)),
        "params": params,
    }
    dump_json(payload, out_dir / "eventtrace_identity.json")
    return payload


def _evaluation_weights(
    *,
    unit_ids: list[str],
    groups: np.ndarray,
    hard_arrival_path: Path | None,
    public_target_path: Path,
) -> tuple[np.ndarray, np.ndarray]:
    """Target = protocol varpi; arrival = empirical I_arr mass (group-smoothed)."""
    pub = pd.read_parquet(public_target_path)
    varpi = {
        str(r.unit_id): float(r.varpi_i_tar)
        for r in pub.itertuples(index=False)
    }
    w = np.asarray([max(varpi.get(u, 0.0), 0.0) for u in unit_ids], dtype=np.float64)
    if float(w.sum()) <= 0:
        w = np.ones(len(unit_ids), dtype=np.float64)
    w = w / float(w.sum())

    arrival_counts = np.zeros(len(unit_ids), dtype=np.float64)
    uid_index = {u: i for i, u in enumerate(unit_ids)}
    if hard_arrival_path is not None and hard_arrival_path.is_file():
        arr = pd.read_parquet(hard_arrival_path)
        pos = arr.loc[arr["I_arr"].astype(bool)]
        for uid, cnt in pos.groupby("unit_id").size().items():
            idx = uid_index.get(str(uid))
            if idx is not None:
                arrival_counts[idx] = float(cnt)
    if float(arrival_counts.sum()) <= 0:
        # Fallback: empirical group mass from positive groups in target support.
        group_mass = np.zeros(N_GROUPS, dtype=np.float64)
        for g in range(N_GROUPS):
            group_mass[g] = float((groups == g).sum())
        group_mass = group_mass / max(float(group_mass.sum()), 1.0)
        arrival = np.asarray([group_mass[int(g)] for g in groups], dtype=np.float64)
    else:
        # Smooth within group so every test unit in an arrived group has mass.
        group_mass = np.zeros(N_GROUPS, dtype=np.float64)
        for g in range(N_GROUPS):
            group_mass[g] = float(arrival_counts[groups == g].sum())
        if float(group_mass.sum()) <= 0:
            arrival = w.copy()
        else:
            group_mass = group_mass / float(group_mass.sum())
            arrival = np.zeros(len(unit_ids), dtype=np.float64)
            for g in range(N_GROUPS):
                mask = groups == g
                n = int(mask.sum())
                if n > 0 and group_mass[g] > 0:
                    arrival[mask] = group_mass[g] / n
    if float(arrival.sum()) <= 0:
        arrival = w.copy()
    else:
        arrival = arrival / float(arrival.sum())
    return w, arrival


def run_method_on_trace(
    root: Path,
    *,
    method: str,
    scenario_id: str,
    label: str,
    trace_dir: Path,
    run_dir: Path,
    dataset: TrafficRunnerDataset,
    pi_target: dict[tuple[str, str], float],
    target_mu: np.ndarray,
    hard_arrival_path: Path | None = None,
    seed: int = CANARY_SEED,
) -> dict[str, Any]:
    from raven_mcs.aggregation.method_policy import get_method_policy

    run_seed = int(seed)
    run_dir.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc)
    t0 = time.perf_counter()
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    failure_reason = None
    exit_code = 0
    try:
        trace, identity = load_event_trace(trace_dir)
        runner = build_full_runner(
            trace,
            dataset,
            method=method,
            n_groups=N_GROUPS,
            model_seed=run_seed,
            local_steps=LOCAL_STEPS,
            device="cpu",
            target_mu=target_mu,
            pi_target=pi_target,
            s_max=S_MAX,
            a_max=40.0,
            p_min=0.05,
            pi_min=1e-6,
            d_max=10.0,
            q_min=0.05,
        )
        metrics = runner.run()
        completed_windows = len(metrics)
        pred = _predict_traffic(runner, dataset, split="test")
        y_true = pred["y_true"]
        y_pred = pred["y_pred"]
        groups = pred["group"]
        w, arrival = _evaluation_weights(
            unit_ids=pred["unit_ids"],
            groups=groups,
            hard_arrival_path=hard_arrival_path,
            public_target_path=root / "configs/frozen/e2_traffic_public_target/atomic_public_target.parquet",
        )
        rmse_target = float(rmse_mu(y_pred, y_true, w))
        rmse_arrival = float(rmse_rho(y_pred, y_true, arrival))
        gap = float(gap_mis(rmse_target, rmse_arrival))
        group_rmse = {}
        for g in range(N_GROUPS):
            mask = groups == g
            if mask.any():
                ww = w[mask]
                ww = ww / float(ww.sum())
                group_rmse[f"block{g}"] = float(rmse_mu(y_pred[mask], y_true[mask], ww))
            else:
                group_rmse[f"block{g}"] = float("nan")

        nonfinite_params = int(sum(
            int((~torch.isfinite(v)).sum().item()) for v in runner.theta.values()
        ))
        active = [m for m in metrics if m.active]
        nonfinite_loss = 0
        for item in runner.diagnostics:
            for key in ("loss", "local_loss", "server_loss"):
                if key in item and item[key] is not None and not np.isfinite(float(item[key])):
                    nonfinite_loss += 1

        ckpt_dir = run_dir / "checkpoints"
        ckpt_dir.mkdir(exist_ok=True)
        torch.save(runner.theta, ckpt_dir / "final.pt")

        window_rows = []
        for m in metrics:
            window_rows.append({
                "window_id": m.window_id,
                "active": bool(m.active),
                "active_client_count": len(m.active_clients) if m.active_clients else 0,
                "eligible_client_count": int(getattr(m, "e_r_size", 0) or 0),
                "usable_client_count": int(getattr(m, "a_r_size", 0) or 0),
                "theta_hash_before": m.theta_hash_before,
                "theta_hash_after": m.theta_hash_after,
                "debt_l1": m.debt_l1,
                "train_loss": m.train_loss,
                "clip_rate_stage1": m.clip_rate_stage1,
                "clip_rate_stage2": m.clip_rate_stage2,
            })
        pd.DataFrame(window_rows).to_parquet(run_dir / "window_metrics.parquet", index=False)
        if runner.diagnostics:
            pd.DataFrame(runner.diagnostics).to_parquet(
                run_dir / "runner_diagnostics.parquet", index=False,
            )

        solver_fail = 0
        denom_zero = 0
        for item in runner.diagnostics:
            if item.get("p2_solver_failure"):
                solver_fail += 1
            if item.get("denominator_zero"):
                denom_zero += 1

        policy = get_method_policy(method)
        stale_updates = int(sum(
            1 for rec in trace.events.itertuples(index=False)
            if int(getattr(rec, "tau", 0)) > 0 and bool(getattr(rec, "U", False))
        ))
        failed_attempts = int(trace.events["attempt_failure"].sum()) if "attempt_failure" in trace.events else 0
        clip_s1 = float(np.mean([m.clip_rate_stage1 for m in metrics])) if metrics else 0.0
        clip_s2 = float(np.mean([m.clip_rate_stage2 for m in metrics])) if metrics else 0.0

        runtime = float(time.perf_counter() - t0)
        final_metrics = {
            "RMSE_mu": rmse_target,
            "RMSE_rho": rmse_arrival,
            "Gap_mis": gap,
            "group_rmse": group_rmse,
            "target_risk_objective": rmse_target,
            "empirical_risk_objective": rmse_arrival,
            "completed_windows": completed_windows,
            "nonfinite_model_parameter_count": nonfinite_params,
            "nonfinite_loss_count": nonfinite_loss,
            "P2_solver_failure_count": solver_fail,
            "denominator_zero_count": denom_zero,
            "active_window_count": len(active),
            "hard_arrival_count": int(
                pd.read_parquet(hard_arrival_path)["I_arr"].astype(bool).sum()
            ) if hard_arrival_path and hard_arrival_path.is_file() else 0,
            "failed_attempt_count": failed_attempts,
            "stale_update_count": stale_updates,
            "clip_rate_stage1": clip_s1,
            "clip_rate_stage2": clip_s2,
            "effective_sample_size_mean": float(np.mean([
                float(d.get("n_eff", 0.0) or 0.0) for d in runner.diagnostics
            ])) if runner.diagnostics else 0.0,
            "policy": {
                "uses_design_ratio": policy.uses_design_ratio,
                "uses_observation_ipw": policy.uses_observation_ipw,
                "uses_usable_ipw": policy.uses_usable_ipw,
                "uses_hajek_local_loss": policy.uses_hajek_local_loss,
                "uses_debt": policy.uses_debt,
                "uses_instant_calibration": policy.uses_instant_calibration,
                "uses_variance_penalty": policy.uses_variance_penalty,
                "uses_staleness_penalty": policy.uses_staleness_penalty,
            },
            "target_weight_sum": float(w.sum()),
            "arrival_weight_sum": float(arrival.sum()),
        }
        dump_json(final_metrics, run_dir / "final_metrics.json")
        stdout_lines.append(json.dumps(final_metrics))
        status = "PASS" if (
            completed_windows == N_WINDOWS
            and nonfinite_params == 0
            and nonfinite_loss == 0
            and np.isfinite(rmse_target)
            and np.isfinite(rmse_arrival)
            and abs(gap - (rmse_target - rmse_arrival)) < 1e-12
        ) else "FAIL"
    except Exception as exc:
        exit_code = 1
        failure_reason = f"{type(exc).__name__}: {exc}"
        stderr_lines.append(failure_reason)
        runtime = float(time.perf_counter() - t0)
        status = "FAIL"
        identity = {}
        final_metrics = {}
        completed_windows = 0
        nonfinite_params = -1
        nonfinite_loss = -1
        solver_fail = -1
        denom_zero = -1

    ended = datetime.now(timezone.utc)
    (run_dir / "stdout.log").write_text("\n".join(stdout_lines) + "\n", encoding="utf-8")
    (run_dir / "stderr.log").write_text("\n".join(stderr_lines) + "\n", encoding="utf-8")
    manifest = {
        "scenario": scenario_id,
        "scenario_label": label,
        "method": method,
        "method_display": METHOD_DISPLAY[method],
        "seed": run_seed,
        "profile_id": SELECTED_STRENGTH,
        "start_time_utc": started.isoformat(),
        "end_time_utc": ended.isoformat(),
        "runtime_seconds": runtime,
        "completed_windows": completed_windows,
        "exit_code": exit_code,
        "status": status,
        "failure_reason": failure_reason,
        "retry_count": 0,
        "seed_replacement_count": 0,
        "eventtrace_dir": trace_dir.relative_to(root).as_posix(),
        "eventtrace_identity": identity if isinstance(identity, dict) else {},
        "local_steps": LOCAL_STEPS,
        "s_max": S_MAX,
        "n_groups": N_GROUPS,
        "final_metrics": final_metrics,
        "warnings": [],
        "peak_memory_mb": None,
    }
    dump_json(manifest, run_dir / "runtime_manifest.json")
    dump_json({
        "method": method,
        "scenario_id": scenario_id,
        "seed": run_seed,
        "profile_id": SELECTED_STRENGTH,
        "local_steps": LOCAL_STEPS,
        "learning_rate": 0.01,
        "a_max": 40.0,
        "s_max": S_MAX,
        "probability_bounds": PROB_BOUNDS,
        "standardization": "train_split_zscore",
    }, run_dir / "config_snapshot.json")
    dump_json({
        "eventtrace_dir": trace_dir.relative_to(root).as_posix(),
        "identity": identity if isinstance(identity, dict) else {},
    }, run_dir / "eventtrace_identity.json")
    dump_json({"method": method, "policy": METHOD_DISPLAY[method]}, run_dir / "method_identity.json")
    dump_json({"scenario_id": scenario_id, "label": label}, run_dir / "scenario_identity.json")
    return manifest


def _predict_traffic(runner, dataset: TrafficRunnerDataset, split: str = "test") -> dict[str, Any]:
    from raven_mcs.models.features import extract_features

    units = []
    for unit in dataset.get_atomic_units(split=split):
        if dataset._public_unit_meta and unit.unit_id not in dataset._public_unit_meta:
            continue
        refreshed = dataset.get_atomic_by_id(unit.unit_id)
        if refreshed is not None:
            units.append(refreshed)
    if not units:
        units = [dataset.get_atomic_by_id(u.unit_id) for u in dataset.get_atomic_units(split=split)]
        units = [u for u in units if u is not None]
    runner.model.load_state_dict(runner.theta)
    runner.model.eval()
    spatial = [unit.spatial_id for unit in units]
    absolute = [unit.absolute_time for unit in units]
    indices = [unit.time_index for unit in units]
    sp, hour, wday, trend = extract_features(
        spatial, absolute, indices, dict(dataset._spatial_to_idx),
        int(dataset.atomic_df["time_index"].max()) + 1,
    )
    with torch.no_grad():
        values = runner.model(sp, hour, wday, trend).cpu().numpy().astype(np.float64)
    return {
        "unit_ids": [unit.unit_id for unit in units],
        "y_true": np.asarray([unit.target_value for unit in units], dtype=np.float64),
        "y_pred": values,
        "group": np.asarray([unit.target_group for unit in units], dtype=np.int64),
        "opportunity_stratum": np.asarray(
            [unit.opportunity_stratum for unit in units], dtype=str,
        ),
    }

"""Official E1 entry utilities.

This module is the single production path for SensorScope E1 EventTrace
generation, frozen G=4 validation, one-method execution, and paper artifacts.
It deliberately does not import any P10/Pre-E1 smoke script.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch

from raven_mcs.correction.pi_target import load_pi_target
from raven_mcs.data.base import DatasetMetadata
from raven_mcs.data.processed_dataset import ProcessedDataset
from raven_mcs.data.target import GroupMapper, RepeatableTimeOfDayMapper, TargetBuilder
from raven_mcs.metrics.accuracy import (
    atomic_arrival_weights,
    gap_mis,
    mae_mu,
    rmse_mu,
    rmse_rho,
    tail_head_rmse,
)
from raven_mcs.metrics.distribution import avg_delta_ref, delta_group
from raven_mcs.models.features import extract_features
from raven_mcs.simulation.event_trace import EventTrace, EventTraceMetadata
from raven_mcs.training.window_runner import FullWindowRunner, build_full_runner
from raven_mcs.utils.hashing import environment_hash, sha256_file, sha256_path_tree
from raven_mcs.utils.serialization import dump_json, dump_yaml, load_json, load_yaml

E1_METHODS = (
    "fedavg_window",
    "fedasync_window",
    "timealign_agg",
    "twostage_hajek",
    "raven",
)
E1_SEEDS = (26001, 26002, 26003, 26004, 26005)
E1_GROUPS = 4
E1_S_MAX = 5
CLIENT_MAPPING_SALT = "raven-mcs-e1-sensorscope-clients-v1"


def sensorscope_dataset(root: Path) -> ProcessedDataset:
    metadata = DatasetMetadata(
        dataset="sensorscope",
        target_name="ambient_temperature",
        target_unit="degree_Celsius",
        spatial_unit="sensorscope_station",
        time_unit="hour",
        source_name="EPFL/Zenodo SensorScope Data",
        source_url="https://zenodo.org/records/2654726",
        raw_license="cc-by-4.0",
        filtering_rules=(
            "Drop rows with non-finite temperature",
            "Keep temperature in [-40, 60] Celsius",
        ),
    )
    metadata.validate()
    return ProcessedDataset(root / "data/processed/sensorscope", metadata)


def git_commit(root: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True,
        capture_output=True, text=True,
    ).stdout.strip()


def frozen_group_identity(root: Path) -> tuple[Path, str]:
    path = root / "configs/frozen/e1_sensorscope_groups.yaml"
    if not path.exists():
        raise FileNotFoundError(f"frozen E1 group config missing: {path}")
    cfg = load_yaml(path)
    if int(cfg.get("group_count", -1)) != E1_GROUPS:
        raise RuntimeError("official E1 group_count must equal four")
    digest = sha256_file(path)
    protocol_path = root / "configs/frozen/e1_sensorscope_balanced.yaml"
    if protocol_path.exists():
        protocol = load_yaml(protocol_path)
        expected = protocol.get("target_group_hash")
        if expected is not None and expected != digest:
            raise RuntimeError("E1 group mapping hash does not match frozen protocol")
    return path, digest


def add_e1_groups(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["target_group_main"] = RepeatableTimeOfDayMapper().map(out)
    out["target_group_fine"] = (
        out["spatial_id"].astype(str)
        + "::tod"
        + out["target_group_main"].astype(str)
    )
    groups = set(out["target_group_main"].unique())
    if groups != set(range(E1_GROUPS)):
        raise RuntimeError(f"E1 main groups must be 0..3, got {sorted(groups)}")
    support = out.loc[out["support_flag"].astype(bool)].groupby(
        "target_group_main",
    ).size()
    if any(int(support.get(group, 0)) <= 0 for group in range(E1_GROUPS)):
        raise RuntimeError("all E1 main groups require positive target support")
    return out


def stable_client_mapping(
    atomic: pd.DataFrame,
    num_clients: int = 10,
    client_measurements: pd.DataFrame | None = None,
) -> tuple[dict[str, str], dict[str, str]]:
    if client_measurements is not None:
        clients = sorted(client_measurements["client_id"].astype(str).unique())
        if not clients:
            raise RuntimeError("client measurement domain is empty")
        station_map = {}
        for station in sorted(atomic["spatial_id"].astype(str).unique()):
            digest = hashlib.sha256(
                f"{CLIENT_MAPPING_SALT}:{station}".encode("utf-8"),
            ).digest()
            station_map[station] = clients[
                int.from_bytes(digest[:8], "big") % len(clients)
            ]
        unit_map = dict(zip(
            atomic["unit_id"].astype(str),
            atomic["spatial_id"].astype(str).map(station_map),
        ))
        available = set(zip(
            client_measurements["client_id"].astype(str),
            client_measurements["unit_id"].astype(str),
        ))
        missing = [
            (client, unit) for unit, client in unit_map.items()
            if (client, unit) not in available
        ]
        if missing:
            raise RuntimeError(f"{len(missing)} mapped measurements are absent")
        return station_map, unit_map

    stations = sorted(atomic["spatial_id"].astype(str).unique())
    station_map: dict[str, str] = {}
    for station in stations:
        digest = hashlib.sha256(
            f"{CLIENT_MAPPING_SALT}:{station}".encode("utf-8"),
        ).digest()
        station_map[station] = f"client-{int.from_bytes(digest[:8], 'big') % num_clients:03d}"
    unit_map = dict(zip(
        atomic["unit_id"].astype(str),
        atomic["spatial_id"].astype(str).map(station_map),
    ))
    return station_map, unit_map


def generate_balanced_trace(
    dataset: ProcessedDataset,
    *,
    seed: int,
    num_windows: int = 100,
    num_clients: int = 10,
    s_max: int = E1_S_MAX,
) -> tuple[EventTrace, dict[str, str]]:
    atomic = add_e1_groups(dataset.atomic_df)
    # Training EventTrace never reads validation/test outcomes.
    train = atomic.loc[atomic["split"].astype(str) == "train"].copy()
    station_map, unit_map = stable_client_mapping(
        atomic, num_clients, dataset.client_df,
    )
    actual_num_clients = len(set(station_map.values()))
    slots = np.sort(train["time_index"].unique())
    blocks = np.array_split(slots, num_windows)
    if any(len(block) == 0 for block in blocks):
        raise ValueError("num_windows exceeds train time slots")
    rng = np.random.default_rng(int(seed))
    rows: list[dict[str, Any]] = []
    for window_id, block in enumerate(blocks):
        window = train.loc[train["time_index"].isin(block)].copy()
        window["_client"] = window["unit_id"].astype(str).map(unit_map)
        for client_id, client_frame in window.groupby("_client", sort=True):
            unit_ids = client_frame["unit_id"].astype(str).tolist()
            client_index = int(str(client_id).split("-")[-1])
            observation_rate = float(np.clip(
                0.20 + 0.015 * np.sin(window_id + client_index), 0.15, 0.25,
            ))
            usable_rate = float(np.clip(
                0.60 + 0.02 * np.cos(window_id - client_index), 0.52, 0.68,
            ))
            flags = rng.random(len(unit_ids)) < observation_rate
            observed = [unit for unit, flag in zip(unit_ids, flags) if flag]
            max_tau = min(s_max, window_id)
            tau = int(rng.integers(0, max_tau + 1))
            compute_success = bool(rng.random() < 0.97)
            network_success = bool(rng.random() < 0.96)
            usable_draw = bool(rng.random() < usable_rate)
            usable = int(compute_success and network_success and usable_draw)
            rows.append({
                "window_id": int(window_id),
                "client_id": str(client_id),
                "risk_set_unit_ids": unit_ids,
                "opportunity_features": {
                    "hour_block": int(window_id % E1_GROUPS),
                    "client_bias": float(client_index),
                },
                "observed_unit_ids": observed,
                "O": {unit: bool(flag) for unit, flag in zip(unit_ids, flags)},
                "registration_time": float(window_id) + 0.01 * client_index,
                "downloaded_version": int(window_id - tau),
                "model_age": int(tau),
                "tau": int(tau),
                "device_profile": "sensorscope-station",
                "network_profile": "balanced-wifi",
                "compute_success": compute_success,
                "compute_duration": float(rng.uniform(0.1, 0.9)),
                "network_success": network_success,
                "network_duration": float(rng.uniform(0.05, 0.45)),
                "arrival_time": float(window_id) + 0.5 + 0.001 * client_index,
                "U": usable,
                "planned_workload_pre": float(len(unit_ids)),
                "raw_workload": float(len(observed)),
                "oracle_p": observation_rate,
                "oracle_q": usable_rate,
                "hidden_confounder": 0.0,
            })
    trace = EventTrace(
        events=pd.DataFrame(rows),
        metadata=EventTraceMetadata(
            dataset="sensorscope",
            seed=int(seed),
            num_windows=int(num_windows),
            num_clients=int(actual_num_clients),
            s_max=int(s_max),
            generator="official-e1-balanced-real-ids-v1",
            notes=(
                "real SensorScope train unit IDs",
                "stable station-cluster client identity independent of seed",
            ),
        ),
    )
    trace.validate()
    return trace, station_map


def audit_e1_trace(
    trace: EventTrace, dataset: ProcessedDataset,
) -> dict[str, Any]:
    real_units = set(dataset.atomic_df["unit_id"].astype(str))
    assigned = [
        str(unit)
        for units in trace.events["risk_set_unit_ids"]
        for unit in units
    ]
    observed = [
        str(unit)
        for units in trace.events["observed_unit_ids"]
        for unit in units
    ]
    dummy = sum(unit.startswith("u") and unit[1:].isdigit() for unit in assigned)
    tau = trace.events["tau"].to_numpy(dtype=int)
    windows = trace.events["window_id"].to_numpy(dtype=int)
    downloaded = trace.events["downloaded_version"].to_numpy(dtype=int)
    usable = trace.events["U"].to_numpy(dtype=int)
    failures = int((trace.events["U"].astype(int) == 0).sum())
    _, expected_unit_client = stable_client_mapping(
        dataset.atomic_df, trace.metadata.num_clients, dataset.client_df,
    )
    event_duplicate_count = int(
        trace.events.duplicated(["window_id", "client_id"]).sum()
    )
    risk_records = pd.DataFrame([
        {
            "window_id": int(row.window_id),
            "client_id": str(row.client_id),
            "unit_id": str(unit),
        }
        for row in trace.events.itertuples()
        for unit in row.risk_set_unit_ids
    ])
    duplicate_risk = int(risk_records.duplicated(["window_id", "unit_id"]).sum())
    mapping_violations = int(sum(
        expected_unit_client.get(str(row.unit_id)) != str(row.client_id)
        for row in risk_records.itertuples()
    ))
    expected_train = set(
        dataset.atomic_df.loc[
            dataset.atomic_df["split"].astype(str) == "train", "unit_id",
        ].astype(str)
    )
    unassigned = len(expected_train - set(assigned))
    time_lookup = dataset.atomic_df.set_index(
        dataset.atomic_df["unit_id"].astype(str),
    )["absolute_time"]
    intervals = []
    for window_id, frame in risk_records.groupby("window_id"):
        times = pd.to_datetime(
            frame["unit_id"].map(time_lookup), utc=True, errors="coerce",
        )
        if not times.empty:
            intervals.append((int(window_id), times.min(), times.max()))
    intervals.sort()
    overlap = sum(
        int(current[1] <= previous[2])
        for previous, current in zip(intervals, intervals[1:])
    )
    chronological_violations = sum(
        int(current[1] < previous[1])
        for previous, current in zip(intervals, intervals[1:])
    )
    invalid_count = len(set(assigned) - real_units)
    usable_over_smax = int(np.sum(
        (usable == 1) & (tau > int(trace.metadata.s_max)),
    ))
    result = {
        "invalid_unit_id_count": invalid_count,
        "real_unit_id_lookup_failures": invalid_count,
        "dummy_unit_id_count": int(dummy),
        "duplicate_event_count": event_duplicate_count,
        "duplicate_risk_record_count": duplicate_risk,
        "duplicate_unit_assignments": len(assigned) - len(set(assigned)),
        "unassigned_risk_record_count": int(unassigned),
        "unassigned_risk_set_records": int(unassigned),
        "future_leakage_count": int(np.sum(downloaded > windows)),
        "future_leakage": int(np.sum(downloaded > windows)),
        "window_time_overlap_count": int(overlap),
        "window_overlap": int(overlap),
        "chronological_violation_count": int(chronological_violations),
        "tau_inconsistency_count": int(np.sum(tau != windows - downloaded)),
        "tau_inconsistency": int(np.sum(tau != windows - downloaded)),
        "usable_over_smax_count": usable_over_smax,
        "usable_over_smax": usable_over_smax,
        "missing_U0_attempt_count": int(failures == 0),
        "client_mapping_violation_count": mapping_violations,
        "a_r_subset_e_r": set(observed).issubset(set(assigned)),
        "retained_u0_attempts": failures,
        "chronological": chronological_violations == 0,
    }
    result["hard_gate_pass"] = bool(
        result["invalid_unit_id_count"] == 0
        and result["dummy_unit_id_count"] == 0
        and result["duplicate_event_count"] == 0
        and result["duplicate_risk_record_count"] == 0
        and result["unassigned_risk_record_count"] == 0
        and result["future_leakage_count"] == 0
        and result["window_time_overlap_count"] == 0
        and result["chronological_violation_count"] == 0
        and result["tau_inconsistency_count"] == 0
        and result["usable_over_smax_count"] == 0
        and result["missing_U0_attempt_count"] == 0
        and result["client_mapping_violation_count"] == 0
        and result["a_r_subset_e_r"]
    )
    return result


def _predict(
    runner: FullWindowRunner, dataset: ProcessedDataset, split: str,
) -> dict[str, Any]:
    units = dataset.get_atomic_units(split=split)
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
    grouped = add_e1_groups(dataset.atomic_df).set_index("unit_id")
    return {
        "unit_ids": [unit.unit_id for unit in units],
        "y_true": np.asarray([unit.target_value for unit in units], dtype=np.float64),
        "y_pred": values,
        "target_group_main": np.asarray(
            [grouped.at[unit.unit_id, "target_group_main"] for unit in units],
            dtype=np.int64,
        ),
        "target_group_fine": np.asarray(
            [grouped.at[unit.unit_id, "target_group_fine"] for unit in units],
            dtype=str,
        ),
        "opportunity_stratum": np.asarray(
            [unit.opportunity_stratum for unit in units], dtype=str,
        ),
        "support_flag": np.asarray([unit.support_flag for unit in units], dtype=bool),
        "spatial_id": np.asarray(spatial, dtype=str),
    }


def _arrival_weights(
    prediction: dict[str, Any], runner: FullWindowRunner, split: str,
) -> tuple[np.ndarray, np.ndarray, dict[str, np.ndarray]]:
    strata = prediction["opportunity_stratum"]
    unit_ids = pd.Index(prediction["unit_ids"], dtype=str)
    frame = add_e1_groups(runner.dataset.atomic_df)
    masses = TargetBuilder(
        group_mapper=GroupMapper(column="target_group_main"),
    ).build(frame, split=split)
    target = masses.atom_mass.reindex(unit_ids, fill_value=0.0).to_numpy()
    stratum_mass = pd.Series(target).groupby(strata).transform("sum").to_numpy()
    nu = np.divide(
        target, stratum_mass, out=np.zeros_like(target), where=stratum_mass > 0,
    )
    clients = sorted(str(value) for value in runner.trace.events["client_id"].unique())
    history = runner.trace.events
    mean_age = history.groupby("client_id")["tau"].mean().to_dict()
    mean_work = history.groupby("client_id")["raw_workload"].mean().to_dict()
    slack = history["window_id"] + 1.0 - history["registration_time"]
    mean_slack = slack.groupby(history["client_id"]).mean().to_dict()
    opportunity = runner.opportunity_estimator.pi_hat()
    blocks = np.asarray([runner._hour_block(value) for value in strata])
    pi = np.zeros((len(clients), len(unit_ids)), dtype=np.float64)
    p = np.zeros_like(pi)
    q = np.zeros_like(pi)
    for index, client in enumerate(clients):
        pi[index] = np.asarray([
            opportunity.get((client, value), runner.p_min) for value in strata
        ])
        p[index] = np.asarray([
            runner.obs_propensity.predict(np.asarray([
                1.0, block, np.log1p(mean_work.get(client, 1.0)),
            ]))
            for block in blocks
        ])
        q[index] = runner.usable_propensity.predict(np.asarray([
            1.0, mean_age.get(client, 0.0), 0.0, 0.0,
            mean_slack.get(client, 0.0),
        ]))
    intensity, arrival = atomic_arrival_weights(pi, nu, p, q)
    intensity = np.where(prediction["support_flag"], intensity, 0.0)
    arrival = intensity / float(intensity.sum())
    return target, arrival, {
        "arrival_intensity": intensity,
        "pi_hat_opp_contribution": pi.sum(axis=0),
        "nu_hat_contribution": nu,
        "p_hat_contribution": p.mean(axis=0),
        "q_hat_contribution": q.mean(axis=0),
    }


def _solver_rows(runner: FullWindowRunner) -> pd.DataFrame:
    rows = []
    for index, result in enumerate(getattr(runner.aggregator, "solve_results", [])):
        rows.append({
            "window_id": index,
            "primary_status": result.primary_status,
            "accepted_status": result.status,
            "fallback_used": result.fallback_used,
            "fallback_solver": result.fallback_solver,
            "fallback_status": result.fallback_status,
            "simplex_residual": result.simplex_residual,
            "nonnegative_violation": result.nonnegative_violation,
            "upper_bound_violation": result.upper_bound_violation,
            "ess_l2_violation": result.ess_l2_violation,
            "feasibility_repair_used": result.feasibility_repair_used,
            "solve_time_seconds": result.solve_time_s,
        })
    return pd.DataFrame(rows)


def run_official_method(
    root: Path,
    *,
    method: str,
    seed: int,
    num_windows: int = 100,
    local_steps: int = 2,
    device: str = "cpu",
    trace_dir: Path | None = None,
    output_root: Path | None = None,
    evaluation_split: str = "test",
    weight_safety: dict[str, float] | None = None,
) -> Path:
    if method not in E1_METHODS:
        raise ValueError(f"method is not in frozen E1 registry: {method}")
    group_path, group_hash = frozen_group_identity(root)
    dataset = sensorscope_dataset(root)
    grouped = add_e1_groups(dataset.atomic_df)
    if grouped["target_group_main"].nunique() != E1_GROUPS:
        raise RuntimeError("official E1 main debt dimension must equal four")
    trace_dir = trace_dir or root / f"outputs/event_traces/e1_balanced_seed{seed}"
    from raven_mcs.simulation.event_trace import load_event_trace
    trace, identity = load_event_trace(trace_dir)
    if num_windows > trace.metadata.num_windows:
        raise RuntimeError("requested windows exceed frozen EventTrace horizon")
    if num_windows < trace.metadata.num_windows:
        trace = EventTrace(
            events=trace.events.loc[
                trace.events["window_id"].astype(int) < int(num_windows)
            ].copy(),
            metadata=replace(trace.metadata, num_windows=int(num_windows)),
            extras=dict(trace.extras),
        )
        trace.validate()
    if trace.metadata.s_max != E1_S_MAX:
        raise RuntimeError("EventTrace S_max does not match frozen E1 protocol")
    started = datetime.now(timezone.utc)
    started_perf = time.perf_counter()
    target_for_runner = TargetBuilder(
        group_mapper=GroupMapper("target_group_main"),
    ).build(grouped, split="test")
    target_mu = np.asarray([
        float(target_for_runner.group_mass.get(str(group), 0.0))
        for group in range(E1_GROUPS)
    ], dtype=np.float64)
    pi_path = root / "configs/frozen/e1_pi_target_client_stratum.parquet"
    pi_target, pi_target_hash = load_pi_target(pi_path)
    if weight_safety is None:
        safety_path = root / "configs/frozen/e1_weight_safety.yaml"
        weight_safety = (
            load_yaml(safety_path).get("selected_parameters", {})
            if safety_path.exists() else {}
        )
    runner = build_full_runner(
        trace, dataset, method=method, n_groups=E1_GROUPS,
        model_seed=int(seed), local_steps=int(local_steps), device=device,
        target_mu=target_mu, pi_target=pi_target, s_max=E1_S_MAX,
        a_max=float(weight_safety.get("a_max", 20.0)),
        p_min=float(weight_safety.get("p_min", 0.05)),
        pi_min=float(weight_safety.get("pi_min", 1e-6)),
        d_max=float(weight_safety.get("d_max", 10.0)),
        q_min=float(weight_safety.get("q_min", 0.05)),
    )
    initial_model_hash = runner._theta_hash()
    metrics = runner.run()
    prediction = _predict(runner, dataset, evaluation_split)
    target, arrival, arrival_details = _arrival_weights(
        prediction, runner, evaluation_split,
    )
    y_true = prediction["y_true"]
    y_pred = prediction["y_pred"]
    rmse_target = rmse_mu(y_pred, y_true, target)
    rmse_arrival = rmse_rho(y_pred, y_true, arrival)
    gap = gap_mis(rmse_target, rmse_arrival)
    if abs(gap - (rmse_target - rmse_arrival)) > 1e-12:
        raise RuntimeError("official E1 Gap_mis identity failed")
    rho_group = np.asarray([
        arrival[prediction["target_group_main"] == group].sum()
        for group in range(E1_GROUPS)
    ])
    mu_group = np.asarray([
        target[prediction["target_group_main"] == group].sum()
        for group in range(E1_GROUPS)
    ])
    ratio = np.divide(rho_group, mu_group, out=np.zeros_like(rho_group), where=mu_group > 0)
    head_tail = tail_head_rmse(
        y_pred, y_true, target, ratio,
        prediction["target_group_main"], mu_group,
    )
    if not np.isfinite(head_tail["head_rmse"]) or not np.isfinite(
        head_tail["tail_rmse"],
    ):
        raise RuntimeError("Tail and Head groups require positive test support")
    active = [item for item in metrics if item.active]
    all_n_eff = [
        value for item in active for value in item.n_eff_values
        if np.isfinite(value) and value > 0
    ]
    solver_df = _solver_rows(runner)
    fallback_count = int(solver_df["fallback_used"].sum()) if not solver_df.empty else 0
    solver_failures = int(
        (~solver_df["accepted_status"].isin(["optimal", "feasible_repaired"])).sum()
    ) if not solver_df.empty else 0
    omega_bar = runner.omega_bar()
    alpha_history = [np.asarray(item.alpha) for item in active]
    beta_history = [np.asarray(item.beta_hat) for item in active]
    runtime = float(time.perf_counter() - started_perf)
    method_rows = pd.DataFrame(runner.diagnostics)
    final_model_hash = runner._theta_hash()
    run_id = (
        f"E1_BALANCED_{method}_{seed}_"
        f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')}"
    )
    output_root = output_root or root / "outputs/runs"
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "checkpoints").mkdir()
    torch.save(runner.theta, run_dir / "checkpoints/final.pt")

    pred_frame = pd.DataFrame({
        "unit_id": prediction["unit_ids"],
        "y_true": y_true,
        "y_pred": y_pred,
        "target_weight": target,
        "arrival_weight": arrival,
        "target_group_main": prediction["target_group_main"],
        "target_group_fine": prediction["target_group_fine"],
        "opportunity_stratum": prediction["opportunity_stratum"],
        "method": method,
        "seed": int(seed),
        "split": evaluation_split,
        "model_hash": final_model_hash,
    })
    pred_frame.to_parquet(run_dir / "predictions_test.parquet", index=False)
    pd.DataFrame({
        "unit_id": prediction["unit_ids"],
        "target_weight": target,
        "arrival_weight": arrival,
        **arrival_details,
    }).to_parquet(run_dir / "arrival_weights_test.parquet", index=False)

    window_rows = []
    def _diag_values(frame: pd.DataFrame, column: str) -> np.ndarray:
        if column not in frame:
            return np.asarray([], dtype=np.float64)
        values: list[float] = []
        for value in frame[column]:
            if isinstance(value, (list, tuple, np.ndarray)):
                values.extend(float(item) for item in value)
            elif value is not None:
                values.append(float(value))
        return np.asarray(values, dtype=np.float64)

    for item in metrics:
        diag = method_rows.loc[
            method_rows.get("window_id", pd.Series(dtype=int)) == item.window_id
        ] if not method_rows.empty and "window_id" in method_rows else pd.DataFrame()
        p_values = _diag_values(diag, "p_hat")
        q_values = _diag_values(diag, "q_hat")
        zeta_values = _diag_values(diag, "zeta_hat")
        window_tau = trace.events.loc[
            trace.events["window_id"].astype(int) == item.window_id, "tau",
        ].to_numpy(dtype=np.float64)
        window_rows.append({
            "r": item.window_id,
            "method": method,
            "seed": int(seed),
            "K_attempt": item.e_r_size,
            "K_usable": item.a_r_size,
            "mean_p_hat": float(p_values.mean()) if len(p_values) else np.nan,
            "min_p_hat": float(p_values.min()) if len(p_values) else np.nan,
            "max_p_hat": float(p_values.max()) if len(p_values) else np.nan,
            "mean_q_hat": float(q_values.mean()) if len(q_values) else np.nan,
            "min_q_hat": float(q_values.min()) if len(q_values) else np.nan,
            "max_q_hat": float(q_values.max()) if len(q_values) else np.nan,
            "mean_zeta_hat": float(zeta_values.mean()) if len(zeta_values) else np.nan,
            "min_zeta_hat": float(zeta_values.min()) if len(zeta_values) else np.nan,
            "max_zeta_hat": float(zeta_values.max()) if len(zeta_values) else np.nan,
            "first_stage_clip_rate": item.clip_rate_stage1,
            "second_stage_clip_rate": item.clip_rate_stage2,
            "mean_n_eff": float(np.mean(item.n_eff_values)) if item.n_eff_values else 0.0,
            "median_n_eff": float(np.median(item.n_eff_values)) if item.n_eff_values else 0.0,
            "min_n_eff": float(np.min(item.n_eff_values)) if item.n_eff_values else 0.0,
            "alpha": json.dumps(item.alpha),
            "beta": json.dumps(item.beta_hat),
            "group_mismatch": float(np.linalg.norm(np.asarray(item.omega) - runner.mu, 1)),
            "reference_deviation": float(
                np.linalg.norm(np.asarray(item.alpha) - np.asarray(item.beta_hat))
            ) if item.alpha and len(item.alpha) == len(item.beta_hat) else 0.0,
            "Q_norm1": item.debt_l1,
            "normalized_debt_prefix": item.debt_l1 / max(item.window_id + 1, 1),
            "mean_staleness": float(window_tau.mean()) if len(window_tau) else 0.0,
            "max_staleness": float(window_tau.max()) if len(window_tau) else 0.0,
            "solver_status": (
                solver_df.iloc[item.window_id]["accepted_status"]
                if item.window_id < len(solver_df) else "not_applicable"
            ),
            "solver_residuals": (
                float(solver_df.iloc[item.window_id]["ess_l2_violation"])
                if item.window_id < len(solver_df) else 0.0
            ),
            "fallback_used": (
                bool(solver_df.iloc[item.window_id]["fallback_used"])
                if item.window_id < len(solver_df) else False
            ),
            "model_hash_before": item.theta_hash_before,
            "model_hash_after": item.theta_hash_after,
        })
    pd.DataFrame(window_rows).to_parquet(run_dir / "metrics_window.parquet", index=False)
    method_rows.to_parquet(run_dir / "method_diagnostics.parquet", index=False)
    method_rows.to_parquet(run_dir / "propensity_diagnostics.parquet", index=False)
    if solver_df.empty:
        solver_df = pd.DataFrame(columns=[
            "window_id", "primary_status", "accepted_status", "fallback_used",
            "simplex_residual", "ess_l2_violation",
        ])
    solver_df.to_parquet(run_dir / "solver_diagnostics.parquet", index=False)

    metrics_run = {
        "seed": int(seed),
        "method": method,
        "RMSE_mu": rmse_target,
        "MAE_mu": mae_mu(y_pred, y_true, target),
        "RMSE_rho": rmse_arrival,
        "Gap_mis": gap,
        "Head_RMSE": head_tail["head_rmse"],
        "Tail_RMSE": head_tail["tail_rmse"],
        "Delta_group": delta_group(omega_bar, runner.mu),
        "Delta_c_s": float(np.abs(target - arrival).sum()),
        "avg_delta_group": float(np.mean([
            np.linalg.norm(np.asarray(item.omega) - runner.mu, 1) for item in active
        ])) if active else 0.0,
        "avg_delta_ref": avg_delta_ref(
            alpha_history, beta_history, [True] * len(active), [1.0] * len(active),
        ) if active else 0.0,
        "normalized_debt": float(np.linalg.norm(runner.debt, 1)) / max(len(metrics), 1),
        "median_n_eff": float(np.median(all_n_eff)) if all_n_eff else 0.0,
        "first_stage_clip_rate": float(np.mean([x.clip_rate_stage1 for x in active])) if active else 0.0,
        "second_stage_clip_rate": float(np.mean([x.clip_rate_stage2 for x in active])) if active else 0.0,
        "max_alpha": max((max(x.alpha) for x in active if x.alpha), default=0.0),
        "mean_staleness": float(trace.events["tau"].mean()),
        "max_staleness": int(trace.events["tau"].max()),
        "fallback_count": fallback_count,
        "solver_failure_count": solver_failures,
        "active_windows": len(active),
        "total_runtime": runtime,
        "total_communication": int(sum(item.a_r_size for item in active)),
        "status": "completed",
    }
    if not all(np.isfinite(value) for key, value in metrics_run.items()
               if isinstance(value, (float, int)) and key not in {"seed"}):
        raise RuntimeError("NaN/Inf in official E1 run metrics")
    dump_json(metrics_run, run_dir / "metrics_run.json")
    resolved_config = {
        "experiment": "E1_balanced",
        "dataset": "sensorscope",
        "method": method,
        "scenario": "balanced",
        "seed": int(seed),
        "num_windows": int(num_windows),
        "local_steps": int(local_steps),
        "s_max": E1_S_MAX,
        "main_groups": E1_GROUPS,
        "device": device,
        "weight_safety": weight_safety,
    }
    resolved_path = run_dir / "resolved_config.yaml"
    dump_yaml(resolved_config, resolved_path)
    dump_json({
        "path": str(trace_dir),
        "event_trace_hash": identity["trace_hash"],
    }, run_dir / "event_trace_ref.json")
    dump_json({
        "runtime_seconds": runtime,
        "communication_updates": metrics_run["total_communication"],
        "device": device,
    }, run_dir / "system_metrics.json")
    (run_dir / "stdout.log").write_text(
        f"official E1 run completed: {run_id}\n", encoding="utf-8",
    )
    (run_dir / "stderr.log").write_text("", encoding="utf-8")
    data_hash = sha256_path_tree(root / "data/processed/sensorscope")
    protocol_path = root / "configs/frozen/e1_sensorscope_balanced.yaml"
    client_mapping_path = root / "configs/frozen/e1_sensorscope_clients.yaml"
    protocol_config_hash = sha256_file(protocol_path)
    resolved_run_config_hash = sha256_file(resolved_path)
    client_mapping_hash = sha256_file(client_mapping_path)
    env_hash = environment_hash()
    manifest = {
        "run_id": run_id,
        "experiment": "E1_balanced",
        "dataset": "sensorscope",
        "scenario": "balanced",
        "method": method,
        "seed": int(seed),
        "git_commit": git_commit(root),
        "protocol_config_hash": protocol_config_hash,
        "resolved_run_config_hash": resolved_run_config_hash,
        "data_hash": data_hash,
        "event_trace_hash": identity["trace_hash"],
        "target_group_hash": group_hash,
        "client_mapping_hash": client_mapping_hash,
        "pi_target_hash": pi_target_hash,
        "initial_model_hash": initial_model_hash,
        "environment_hash": env_hash,
        "model_hash": final_model_hash,
        "initial_model_seed": int(seed),
        "start_time": started.isoformat(),
        "end_time": datetime.now(timezone.utc).isoformat(),
        "hard_gate_status": {
            "entry_smoke": "PASS",
            "metric_gate": "PASS",
            "solver_gate": "PASS" if solver_failures == 0 else "FAIL",
            "eventtrace_gate": "PASS",
            "artifact_gate": "PASS",
        },
        "status": "completed",
    }
    dump_json(manifest, run_dir / "manifest.json")
    required = {
        "manifest.json", "resolved_config.yaml", "event_trace_ref.json",
        "metrics_window.parquet", "metrics_run.json",
        "predictions_test.parquet", "arrival_weights_test.parquet",
        "propensity_diagnostics.parquet", "solver_diagnostics.parquet",
        "system_metrics.json", "method_diagnostics.parquet",
        "stdout.log", "stderr.log", "checkpoints",
    }
    if not all((run_dir / name).exists() for name in required):
        raise RuntimeError("official E1 artifact completeness gate failed")
    return run_dir

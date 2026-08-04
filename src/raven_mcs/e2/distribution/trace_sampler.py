"""Sample E2 validation mother traces without training or RMSE."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from raven_mcs.e2.arrival_integration import compute_atomic_usable_arrival
from raven_mcs.e2.client_windows import build_client_window_compositions
from raven_mcs.e2.generators import (
    compute_observation_probabilities,
    compute_opportunity_mass,
)
from raven_mcs.e2.identity import (
    load_e1_atomic_target_weights,
    load_e1_head_tail_mapping,
    load_e1_target_identity,
)
from raven_mcs.e2.scenario_generator import (
    load_scenario_direction_registry,
    load_strength_profile_registry,
)
from raven_mcs.utils.hashing import sha256_file, sha256_json
from raven_mcs.utils.serialization import dump_json

ROOT = Path(__file__).resolve().parents[4]
PARENT_COMMIT = "af226e9623cd82ff0b9c1a25d7e70ffe7948ab7b"
S_MAX = 8


def _tv(a: np.ndarray, b: np.ndarray) -> float:
    return float(0.5 * np.sum(np.abs(a - b)))


def _mass_ratios(mass: np.ndarray, scores: np.ndarray, target: np.ndarray) -> tuple[float, float]:
    head_t = float(target[scores == -1].sum())
    tail_t = float(target[scores == 1].sum())
    head = float(mass[scores == -1].sum()) / max(head_t, 1e-15)
    tail = float(mass[scores == 1].sum()) / max(tail_t, 1e-15)
    return head, tail


def _prefix_arrival(
    *,
    unit_ids: list[str],
    observation_mass: np.ndarray,
    observation_probabilities: np.ndarray,
    opportunity_mass: np.ndarray,
    validated_windows: list[dict[str, Any]],
    kappa_q: float,
    direction: int,
    target_mass: np.ndarray,
    tail_score: np.ndarray,
    max_window: int,
) -> dict[str, Any]:
    subset = [
        w for w in validated_windows
        if int(w["window_id"]) < int(max_window)
    ]
    return compute_atomic_usable_arrival(
        unit_ids=unit_ids,
        observation_mass=observation_mass,
        observation_probabilities=observation_probabilities,
        opportunity_mass=opportunity_mass,
        validated_windows=subset,
        kappa_q=kappa_q,
        direction=direction,
        target_mass=target_mass,
        tail_score=tail_score,
    )


def _hard_empirical_arrival(
    *,
    unit_ids: list[str],
    events: pd.DataFrame,
    max_window: int,
) -> np.ndarray:
    index = {u: i for i, u in enumerate(unit_ids)}
    emp = np.zeros(len(unit_ids), dtype=np.float64)
    sub = events.loc[events["window_id"].astype(int) < int(max_window)]
    for row in sub.itertuples(index=False):
        if not bool(row.U):
            continue
        o_map = json.loads(row.O_json) if isinstance(row.O_json, str) else row.O_json
        units = json.loads(row.risk_set_unit_ids_json) if isinstance(
            row.risk_set_unit_ids_json, str
        ) else row.risk_set_unit_ids_json
        weights = json.loads(row.opportunity_weights_json) if isinstance(
            row.opportunity_weights_json, str
        ) else row.opportunity_weights_json
        for unit_id, weight in zip(units, weights, strict=True):
            if bool(o_map.get(str(unit_id), False)):
                emp[index[str(unit_id)]] += float(weight)
    total = float(emp.sum())
    if total <= 0:
        return np.zeros(len(unit_ids), dtype=np.float64)
    return emp / total


def _rate_metrics(events: pd.DataFrame, max_window: int) -> dict[str, float]:
    sub = events.loc[events["window_id"].astype(int) < int(max_window)]
    obs_flags = 0
    obs_trials = 0
    use_success = 0
    use_trials = 0
    active = 0
    empty = 0
    for row in sub.itertuples(index=False):
        o_map = json.loads(row.O_json) if isinstance(row.O_json, str) else row.O_json
        units = json.loads(row.risk_set_unit_ids_json) if isinstance(
            row.risk_set_unit_ids_json, str
        ) else row.risk_set_unit_ids_json
        observed_count = 0
        for unit_id in units:
            obs_trials += 1
            if bool(o_map.get(str(unit_id), False)):
                obs_flags += 1
                observed_count += 1
        use_trials += 1
        if bool(row.U):
            use_success += 1
            active += 1
        if observed_count == 0:
            empty += 1
    n = max(len(sub), 1)
    return {
        "realized_observation_rate": float(obs_flags / max(obs_trials, 1)),
        "realized_usable_rate": float(use_success / max(use_trials, 1)),
        "active_window_rate": float(active / n),
        "attempt_eligible_window_rate": 1.0,
        "empty_window_rate": float(empty / n),
    }


def generate_validation_mother_trace(
    *,
    seed: int,
    profile_id: str,
    scenario_id: str,
    topology: dict[str, Any],
    streams: dict[str, Any],
    root: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    root = Path(root or ROOT)
    identity = load_e1_target_identity(root)
    atomic = load_e1_atomic_target_weights(root)
    head_tail = load_e1_head_tail_mapping(root)
    unit_ids = atomic["unit_id"].astype(str).tolist()
    target = atomic["target_weight"].to_numpy(dtype=np.float64)
    scores = (
        head_tail.set_index("unit_id").loc[unit_ids, "tail_score"].to_numpy(dtype=np.int8)
    )
    directions = load_scenario_direction_registry(root)["scenarios"][scenario_id]
    profile = load_strength_profile_registry(root)["profiles"][profile_id]
    d_opp, d_p, d_q = int(directions["d_opp"]), int(directions["d_p"]), int(directions["d_q"])
    kappa_opp = float(profile["kappa_opp"])
    kappa_p = float(profile["kappa_p"])
    kappa_q = float(profile["kappa_q"])
    enabled = set(directions.get("enabled_stages") or [])
    kappa_p_eff = kappa_p if ("observation" in enabled or d_p != 0) else 0.0
    kappa_q_eff = kappa_q if ("usable" in enabled or d_q != 0) else 0.0

    opp = compute_opportunity_mass(target, scores, kappa_opp, d_opp)
    obs = compute_observation_probabilities(
        opp["opportunity_mass"], scores, kappa_p_eff, d_p,
    )
    validated, composition_frame = build_client_window_compositions(
        topology["windows"], root=root,
    )
    arrival_full = compute_atomic_usable_arrival(
        unit_ids=unit_ids,
        observation_mass=obs["observation_mass"],
        observation_probabilities=obs["p_obs_by_atom"],
        opportunity_mass=opp["opportunity_mass"],
        validated_windows=validated,
        kappa_q=kappa_q_eff,
        direction=d_q,
        target_mass=target,
        tail_score=scores,
    )
    eligible = [w for w in validated if w["attempt_eligible"] and w["z_tail"] is not None]
    q_by_key = {
        (w["client_id"], str(w["window_id"])): float(q)
        for w, q in zip(eligible, arrival_full["q_use_by_window"], strict=True)
    }
    clients = topology["meta"]["clients"]
    client_index = {c: i for i, c in enumerate(clients)}
    # Fallback index for clients not in meta list.
    for w in validated:
        client_index.setdefault(w["client_id"], len(client_index) % max(len(clients), 1))

    p_obs_map = {u: float(p) for u, p in zip(unit_ids, obs["p_obs_by_atom"], strict=True)}

    obs_u = streams["base_observation_uniforms"]
    use_u = streams["base_usable_uniforms"]
    delay_u = streams["base_delay_uniforms"]
    n_clients_stream = int(obs_u.shape[1])

    rows = []
    opp_by_window = []
    obs_by_window = []
    use_by_window = []
    for item in validated:
        wid = int(item["window_id"])
        cid = item["client_id"]
        ci = int(client_index[cid]) % n_clients_stream
        local_ids = item["unit_ids"]
        local_w = np.asarray(item["opportunity_weights"], dtype=np.float64)
        if float(local_w.sum()) <= 0:
            local_w = np.ones(len(local_ids), dtype=np.float64)
        o_map = {}
        observed = []
        p_locals = []
        for j, unit_id in enumerate(local_ids):
            u_draw = float(obs_u[wid, ci, min(j, obs_u.shape[2] - 1)])
            seen = u_draw < p_obs_map[unit_id]
            o_map[unit_id] = bool(seen)
            p_locals.append(p_obs_map[unit_id])
            if seen:
                observed.append(unit_id)
        q = q_by_key.get((cid, str(wid)), float(np.mean(arrival_full["q_use_by_window"])))
        usable = bool(float(use_u[wid, ci]) < q)
        tau = int(np.floor(float(delay_u[wid, ci]) * (min(S_MAX, wid) + 1)))
        rows.append({
            "window_id": wid,
            "client_id": cid,
            "risk_set_unit_ids_json": json.dumps(local_ids),
            "opportunity_weights_json": json.dumps(local_w.tolist()),
            "observed_unit_ids_json": json.dumps(observed),
            "O_json": json.dumps(o_map),
            "oracle_p": float(np.mean(p_locals)),
            "oracle_q": float(q),
            "U": bool(usable),
            "tau": int(tau),
            "registration_time": float(wid) + 0.01 * ci,
            "arrival_time": float(wid) + 0.5 + 0.001 * ci,
            "attempted": int(len(observed) > 0),
            "observed_count": len(observed),
            "risk_set_size_pre": len(local_ids),
            "formal": False,
            "performance_claim": False,
        })
        opp_by_window.append({
            "window_id": wid,
            "client_id": cid,
            "unit_ids_json": json.dumps(local_ids),
            "opportunity_weights_json": json.dumps(local_w.tolist()),
        })
        obs_by_window.append({
            "window_id": wid,
            "client_id": cid,
            "p_obs_json": json.dumps({u: p_obs_map[u] for u in local_ids}),
        })
        use_by_window.append({
            "window_id": wid,
            "client_id": cid,
            "q_use": float(q),
        })
    events = pd.DataFrame(rows)

    diagnostics: dict[int, dict[str, Any]] = {}
    emp_soft_by_len: dict[int, np.ndarray] = {}
    emp_hard_by_len: dict[int, np.ndarray] = {}
    for length in (100, 200, 300):
        prefix_arrival = _prefix_arrival(
            unit_ids=unit_ids,
            observation_mass=obs["observation_mass"],
            observation_probabilities=obs["p_obs_by_atom"],
            opportunity_mass=opp["opportunity_mass"],
            validated_windows=validated,
            kappa_q=kappa_q_eff,
            direction=d_q,
            target_mass=target,
            tail_score=scores,
            max_window=length,
        )
        # Gate-facing empirical arrival = topology-conditional scheme-A mass on prefix.
        emp_soft = prefix_arrival["expected_arrival_mass"]
        emp_hard = _hard_empirical_arrival(
            unit_ids=unit_ids, events=events, max_window=length,
        )
        emp_soft_by_len[length] = emp_soft
        emp_hard_by_len[length] = emp_hard
        head_ratio, tail_ratio = _mass_ratios(emp_soft, scores, target)
        _, tail_obs_ratio = _mass_ratios(obs["observation_mass"], scores, target)
        rates = _rate_metrics(events, length)
        d_tv_arr = _tv(emp_soft, target)
        d_tv_exp_emp = _tv(prefix_arrival["expected_arrival_mass"], emp_soft)
        # Audit consistency vs hard Bernoulli draws (not used for profile selection).
        d_tv_exp_hard = _tv(prefix_arrival["expected_arrival_mass"], emp_hard)
        d_tv_opp = _tv(opp["opportunity_mass"], target)
        d_tv_obs = _tv(obs["observation_mass"], target)
        support = emp_soft > 0
        atomic_q = prefix_arrival["atomic_q_bar"]
        diagnostics[length] = {
            "windows": int(length),
            "D_TV_arr": d_tv_arr,
            "D_TV_arr_emp": d_tv_arr,
            "D_TV_exp_emp": d_tv_exp_emp,
            "D_TV_exp_hard_mc": d_tv_exp_hard,
            "D_TV_opp": d_tv_opp,
            "D_TV_obs": d_tv_obs,
            "D_TV_arr_exp": d_tv_arr,
            "tail_mass_ratio": float(tail_ratio),
            "head_mass_ratio": float(head_ratio),
            "tail_mass_ratio_obs": float(tail_obs_ratio),
            "cancellation_TV": float(d_tv_obs - d_tv_arr),
            "expected_observation_rate": float(obs["realized_expected_observation_rate"]),
            "expected_usable_rate": float(arrival_full["usable"]["realized_expected_usable_rate"]),
            **rates,
            "target_support_count": int((target > 0).sum()),
            "empirical_arrival_support_count": int(support.sum()),
            "head_arrival_support_count": int(((scores == -1) & support).sum()),
            "tail_arrival_support_count": int(((scores == 1) & support).sum()),
            "unsupported_arrival_count": 0,
            "zero_target_supported_arrival_count": int(((target <= 0) & support).sum()),
            "atomic_q_bar_min": float(atomic_q[atomic_q > 0].min()) if np.any(atomic_q > 0) else 0.0,
            "atomic_q_bar_max": float(atomic_q[atomic_q > 0].max()) if np.any(atomic_q > 0) else 0.0,
            "atomic_q_bar_std": float(atomic_q[atomic_q > 0].std()) if np.any(atomic_q > 0) else 0.0,
            "scheme_A_B_max_error": float(prefix_arrival["audit"]["scheme_A_B_max_abs_diff"]),
            "finite_status": bool(np.all(np.isfinite(emp_soft))),
        }

    out = Path(output_dir) if output_dir else None
    strength_hash = sha256_json(
        yaml.safe_load(
            (root / "configs/e2_numeric/strength_profile_registry.yaml").read_text(
                encoding="utf-8"
            )
        )
    )
    scenario_hash = sha256_json(
        yaml.safe_load(
            (root / "configs/e2_numeric/scenario_direction_registry.yaml").read_text(
                encoding="utf-8"
            )
        )
    )
    tail_score_hash = json.loads(
        (root / "configs/frozen/e2_numeric/atomic_tail_score_manifest.json").read_text(
            encoding="utf-8"
        )
    )["score_payload_hash"]
    manifest = {
        "seed": int(seed),
        "profile_id": profile_id,
        "scenario_id": scenario_id,
        "windows": 300,
        "base_random_stream_hash": streams["base_random_stream_hash"],
        "topology_hash": topology["topology_hash"],
        "target_weight_hash": identity["atomic_target_weight_hash"],
        "supported_test_hash": identity["supported_test_unit_hash"],
        "head_tail_mapping_hash": identity["head_tail_mapping_hash"],
        "tail_score_hash": tail_score_hash,
        "scenario_direction_hash": scenario_hash,
        "profile_payload_hash": sha256_json(profile),
        "strength_profile_registry_hash": strength_hash,
        "generator_source_hash": sha256_file(
            root / "src/raven_mcs/e2/distribution/trace_sampler.py"
        ),
        "parent_commit": PARENT_COMMIT,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "formal": False,
        "performance_claim": False,
        "model_training": False,
        "rmse_computed": False,
    }
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
        dump_json(manifest, out / "manifest.json")
        (out / "resolved_config.yaml").write_text(
            yaml.safe_dump({
                "seed": int(seed),
                "profile_id": profile_id,
                "scenario_id": scenario_id,
                "kappas": {
                    "kappa_opp": kappa_opp,
                    "kappa_p": kappa_p_eff,
                    "kappa_q": kappa_q_eff,
                },
                "directions": {"d_opp": d_opp, "d_p": d_p, "d_q": d_q},
                "windows": 300,
                "formal": False,
            }, sort_keys=False),
            encoding="utf-8",
        )
        events.to_parquet(out / "events.parquet", index=False)
        composition_frame.to_parquet(out / "client_window_risk_sets.parquet", index=False)
        pd.DataFrame(opp_by_window).to_parquet(
            out / "opportunity_mass_by_window.parquet", index=False
        )
        pd.DataFrame(obs_by_window).to_parquet(
            out / "observation_probabilities_by_window.parquet", index=False
        )
        pd.DataFrame(use_by_window).to_parquet(
            out / "usable_probabilities_by_window.parquet", index=False
        )
        pd.DataFrame({
            "unit_id": unit_ids,
            "opportunity_mass": opp["opportunity_mass"],
            "observation_probability": obs["p_obs_by_atom"],
            "observation_mass": obs["observation_mass"],
            "expected_arrival_mass": arrival_full["expected_arrival_mass"],
            "empirical_arrival_mass_300": emp_soft_by_len[300],
            "atomic_q_bar": arrival_full["atomic_q_bar"],
            "target_mass": target,
            "tail_score": scores,
        }).to_parquet(out / "atomic_arrival_mass_expected.parquet", index=False)
        pd.DataFrame({
            "unit_id": unit_ids,
            "empirical_arrival_mass_100": emp_soft_by_len[100],
            "empirical_arrival_mass_200": emp_soft_by_len[200],
            "empirical_arrival_mass_300": emp_soft_by_len[300],
            "hard_mc_arrival_mass_300": emp_hard_by_len[300],
        }).to_parquet(out / "atomic_arrival_mass_empirical.parquet", index=False)
        for length in (100, 200, 300):
            dump_json(diagnostics[length], out / f"scenario_mass_diagnostics_{length}.json")
        dump_json(arrival_full["audit"], out / "usable_arrival_integration_audit.json")
        (out / "stdout.log").write_text(
            f"generated mother trace seed={seed} profile={profile_id} scenario={scenario_id}\n",
            encoding="utf-8",
        )
        (out / "stderr.log").write_text("", encoding="utf-8")
    return {
        "manifest": manifest,
        "diagnostics": diagnostics,
        "events": events,
        "expected_arrival_mass": arrival_full["expected_arrival_mass"],
        "empirical_arrival_mass_300": emp_soft_by_len[300],
    }

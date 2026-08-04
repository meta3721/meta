"""Profile validity gates G1–G6 and deterministic selection."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np

VALIDATION_SEEDS = (29101, 29102, 29103, 29104, 29105)
SCENARIOS = (
    "balanced",
    "opportunity_only",
    "observation_only",
    "usable_only",
    "complete_aligned",
    "complete_counteracting",
)
PROFILES = tuple(f"PROFILE-S{i}" for i in range(1, 7))
SINGLE_STAGE = ("opportunity_only", "observation_only", "usable_only")


def evaluate_seed_profile_gates(
    diagnostics_by_scenario: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Evaluate G1–G6 for one seed using 300-window diagnostics."""
    rows = {k: dict(v) for k, v in diagnostics_by_scenario.items()}
    gate_status: dict[str, str] = {}
    failures: list[str] = []

    b = rows["balanced"]
    g1 = (
        float(b["D_TV_arr_emp"]) <= 0.02
        and 0.95 <= float(b["tail_mass_ratio"]) <= 1.05
        and 0.95 <= float(b["head_mass_ratio"]) <= 1.05
        and int(b["unsupported_arrival_count"]) == 0
    )
    gate_status["G1"] = "PASS" if g1 else "FAIL"
    if not g1:
        failures.append("G1")

    g2_ok = True
    for scen in SINGLE_STAGE:
        r = rows[scen]
        ok = (
            float(r["D_TV_arr_emp"]) >= 0.05
            and float(r["tail_mass_ratio"]) <= 0.90
            and float(r["head_mass_ratio"]) >= 1.05
            and 0.18 <= float(r["realized_observation_rate"]) <= 0.22
            and 0.57 <= float(r["realized_usable_rate"]) <= 0.63
        )
        gate_status[f"G2_{scen}"] = "PASS" if ok else "FAIL"
        if not ok:
            g2_ok = False
            failures.append(f"G2_{scen}")
    gate_status["G2"] = "PASS" if g2_ok else "FAIL"

    al = rows["complete_aligned"]
    max_single = max(float(rows[s]["D_TV_arr_emp"]) for s in SINGLE_STAGE)
    min_single_tail = min(float(rows[s]["tail_mass_ratio"]) for s in SINGLE_STAGE)
    g3 = (
        float(al["D_TV_arr_emp"]) >= max_single + 0.02
        and float(al["tail_mass_ratio"]) < min_single_tail
        and float(al["tail_mass_ratio"]) < float(al["tail_mass_ratio_obs"])
    )
    gate_status["G3"] = "PASS" if g3 else "FAIL"
    if not g3:
        failures.append("G3")

    ca = rows["complete_counteracting"]
    g4 = (
        float(ca["D_TV_arr_emp"]) < float(al["D_TV_arr_emp"])
        and float(ca["D_TV_arr_emp"]) > float(b["D_TV_arr_emp"]) + 0.01
        and float(ca["tail_mass_ratio"]) > float(al["tail_mass_ratio"])
        and float(ca["tail_mass_ratio"]) > float(ca["tail_mass_ratio_obs"])
        and float(ca["cancellation_TV"]) > 0.0
    )
    gate_status["G4"] = "PASS" if g4 else "FAIL"
    if not g4:
        failures.append("G4")

    g5_ok = True
    for scen, r in rows.items():
        limit = 0.02 if scen == "balanced" else 0.03
        ok = float(r["D_TV_exp_emp"]) <= limit
        gate_status[f"G5_{scen}"] = "PASS" if ok else "FAIL"
        if not ok:
            g5_ok = False
            failures.append(f"G5_{scen}")
    gate_status["G5"] = "PASS" if g5_ok else "FAIL"

    g6_ok = True
    for scen, r in rows.items():
        ok = (
            int(r["unsupported_arrival_count"]) == 0
            and int(r["head_arrival_support_count"]) > 0
            and int(r["tail_arrival_support_count"]) > 0
            and int(r["empirical_arrival_support_count"]) > 0
            and bool(r["finite_status"])
        )
        gate_status[f"G6_{scen}"] = "PASS" if ok else "FAIL"
        if not ok:
            g6_ok = False
            failures.append(f"G6_{scen}")
    gate_status["G6"] = "PASS" if g6_ok else "FAIL"

    return {
        "gate_status": gate_status,
        "failures": failures,
        "profile_valid_seed": not failures,
        "aligned_dtv": float(al["D_TV_arr_emp"]),
        "counteracting_cancellation": float(ca["cancellation_TV"]),
    }


def select_strength_profile(
    profile_seed_results: Mapping[str, Mapping[int, Mapping[str, Any]]],
    profiles_payload: Mapping[str, Mapping[str, float]],
) -> dict[str, Any]:
    """Deterministic selection among profiles that pass G1–G6 on all seeds."""
    valid = []
    for profile_id, by_seed in profile_seed_results.items():
        if all(bool(by_seed[s]["profile_valid_seed"]) for s in VALIDATION_SEEDS):
            max_aligned = max(float(by_seed[s]["aligned_dtv"]) for s in VALIDATION_SEEDS)
            cancel = [
                float(by_seed[s]["counteracting_cancellation"]) for s in VALIDATION_SEEDS
            ]
            kappa_sum = (
                float(profiles_payload[profile_id]["kappa_opp"])
                + float(profiles_payload[profile_id]["kappa_p"])
                + float(profiles_payload[profile_id]["kappa_q"])
            )
            valid.append({
                "profile_id": profile_id,
                "max_seed_aligned_dtv": max_aligned,
                "kappa_sum": kappa_sum,
                "std_seed_cancellation_tv": float(np.std(cancel)),
            })
    if not valid:
        return {
            "status": "NO_VALID_DISTRIBUTION_PROFILE",
            "selected_profile_id": None,
            "candidates": [],
        }
    valid.sort(
        key=lambda r: (
            r["max_seed_aligned_dtv"],
            r["kappa_sum"],
            r["std_seed_cancellation_tv"],
            r["profile_id"],
        )
    )
    selected = valid[0]
    return {
        "status": "SELECTED",
        "selected_profile_id": selected["profile_id"],
        "selection_rule": [
            "min max_seed D_TV_arr_emp(complete_aligned)",
            "min kappa_opp+kappa_p+kappa_q",
            "min std_seed cancellation_TV(complete_counteracting)",
            "profile_id lexicographic",
        ],
        "selected_metrics": selected,
        "candidates": valid,
    }


def window_prefix_stable(
    metrics_by_length: Mapping[int, Mapping[str, Mapping[str, float]]],
    *,
    length: int,
    reference: int = 300,
) -> tuple[bool, dict[str, float]]:
    """Check stability deltas of length L vs 300 across all scenarios for one seed."""
    thresholds = {
        "delta_TV": 0.01,
        "delta_tail_ratio": 0.05,
        "delta_head_ratio": 0.05,
        "delta_observation_rate": 0.02,
        "delta_usable_rate": 0.03,
        "delta_active_window_rate": 0.02,
        "delta_exp_emp": 0.01,
    }
    key_map = {
        "delta_TV": "D_TV_arr_emp",
        "delta_tail_ratio": "tail_mass_ratio",
        "delta_head_ratio": "head_mass_ratio",
        "delta_observation_rate": "realized_observation_rate",
        "delta_usable_rate": "realized_usable_rate",
        "delta_active_window_rate": "active_window_rate",
        "delta_exp_emp": "D_TV_exp_emp",
    }
    worst = {k: 0.0 for k in thresholds}
    ok = True
    for scen in SCENARIOS:
        a = metrics_by_length[length][scen]
        b = metrics_by_length[reference][scen]
        for delta_name, field in key_map.items():
            delta = abs(float(a[field]) - float(b[field]))
            worst[delta_name] = max(worst[delta_name], delta)
            if delta > thresholds[delta_name]:
                ok = False
    return ok, worst


def select_window_length(
    seed_stability: Mapping[int, Mapping[int, bool]],
) -> dict[str, Any]:
    """Pick shortest length that passes on all seeds; 300 is always fallback."""
    status = {}
    for length in (100, 200, 300):
        status[length] = all(
            bool(seed_stability[seed][length]) for seed in VALIDATION_SEEDS
        )
    # 300 is valid fallback whenever profile gates passed.
    status[300] = True
    selected = 100 if status[100] else 200 if status[200] else 300
    return {
        "selected_windows": selected,
        "candidate_status_100": "PASS" if status[100] else "FAIL",
        "candidate_status_200": "PASS" if status[200] else "FAIL",
        "candidate_status_300": "PASS",
        "selection_rule": "shortest stable among {100,200,300}; 300 fallback",
    }

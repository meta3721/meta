#!/usr/bin/env python3
"""Evaluate E2NG-G1..G10 hard gates for numeric-generator implementation."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import yaml

from raven_mcs.e2.generators import (
    RATE_TOL,
    build_atomic_tail_score,
    compute_observation_probabilities,
    compute_opportunity_mass,
    compute_usable_probabilities,
)
from raven_mcs.e2.identity import (
    load_e1_atomic_target_weights,
    load_e1_head_tail_mapping,
    load_e1_supported_test_units,
    load_e1_target_identity,
)
from raven_mcs.e2.methods import method_implementation_identity, resolve_method
from raven_mcs.utils.serialization import dump_json

ROOT = Path(__file__).resolve().parents[1]


def _pass(cond: bool) -> str:
    return "PASS" if cond else "FAIL"


def evaluate(root: Path, *, unit_ok: bool, integ_ok: bool, full_ok: bool) -> dict:
    identity = load_e1_target_identity(root)
    e1 = json.loads(
        (root / "configs/frozen/e1_pi_target_manifest.json").read_text(encoding="utf-8")
    )
    atomic = load_e1_atomic_target_weights(root)
    head_tail = load_e1_head_tail_mapping(root)
    supported = load_e1_supported_test_units(root)
    scores = build_atomic_tail_score(head_tail)

    g1 = (
        identity["atomic_target_weight_hash"] == e1["atomic_target_weight_hash"]
        and identity["uniform_target_fallback"] == "FORBIDDEN"
        and abs(float(atomic["target_weight"].sum()) - 1.0) <= 1e-12
        and len(supported) > 0
        and identity["head_unit_count"] > 0
        and identity["tail_unit_count"] > 0
    )

    tail_manifest = json.loads(
        (root / "configs/frozen/e2_numeric/atomic_tail_score_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    g2 = (
        set(np.unique(scores)).issubset({-1, 0, 1})
        and int((scores == -1).sum()) > 0
        and int((scores == 1).sum()) > 0
        and tail_manifest["head_count"] > 0
        and tail_manifest["tail_count"] > 0
    )

    target = atomic["target_weight"].to_numpy(dtype=np.float64)
    unit_ids = atomic["unit_id"].astype(str).tolist()
    ordered_scores = (
        head_tail.set_index("unit_id").loc[unit_ids, "tail_score"].to_numpy(dtype=np.int8)
    )
    opp0 = compute_opportunity_mass(target, ordered_scores, 0.0, -1)
    opp_under = compute_opportunity_mass(target, ordered_scores, 1.0, -1)
    g3 = (
        abs(float(opp0["opportunity_mass"].sum()) - 1.0) <= 1e-12
        and np.allclose(opp0["opportunity_mass"], target, atol=1e-12)
        and opp_under["tail_mass_ratio"] < 1.0
        and np.all(opp_under["opportunity_mass"][target > 0] > 0)
    )

    obs = compute_observation_probabilities(
        opp_under["opportunity_mass"], ordered_scores, 1.0, -1,
        observation_rate_target=0.20,
    )
    g4 = (
        abs(obs["realized_expected_observation_rate"] - 0.20) <= RATE_TOL
        and float(obs["p_obs_by_atom"].min()) >= 0.05 - 1e-12
        and float(obs["p_obs_by_atom"].max()) <= 0.95 + 1e-12
    )

    usable = compute_usable_probabilities(
        np.asarray([-0.5, 0.0, 0.5], dtype=np.float64),
        kappa_q=1.0,
        direction=-1,
        usable_rate_target=0.60,
    )
    feature_manifest = json.loads(
        (
            root / "configs/frozen/e2_numeric/e2_q_generator_feature_manifest.json"
        ).read_text(encoding="utf-8")
    )
    g5 = (
        abs(usable["realized_expected_usable_rate"] - 0.60) <= RATE_TOL
        and usable["feature_names"] == ["pre_outcome_tail_composition_z"]
        and "local_loss" in feature_manifest["forbidden_features"]
    )

    directions = yaml.safe_load(
        (root / "configs/e2_numeric/scenario_direction_registry.yaml").read_text(
            encoding="utf-8"
        )
    )["scenarios"]
    tuples = {(v["d_opp"], v["d_p"], v["d_q"]) for v in directions.values()}
    g6 = len(directions) == 6 and len(tuples) == 6

    strengths = yaml.safe_load(
        (root / "configs/e2_numeric/strength_profile_registry.yaml").read_text(
            encoding="utf-8"
        )
    )
    g7 = (
        len(strengths["profiles"]) == 6
        and strengths["selection_status"] == "NOT_STARTED"
        and strengths["status"] == "FROZEN_BEFORE_VALIDATION"
    )

    alias_ok = resolve_method("timealign_agg", root) == "flamf_timealign_adapted"
    alias_id = method_implementation_identity("timealign_agg", root)
    exec_id = method_implementation_identity("flamf_timealign_adapted", root)
    g8 = (
        alias_ok
        and alias_id["executable_id"] == exec_id["executable_id"]
        and alias_id["source_blob_hash"] == exec_id["source_blob_hash"]
    )

    parent = json.loads(
        (root / "configs/frozen/e2_entry/e1_r2_parent_reference.json").read_text(
            encoding="utf-8"
        )
    )
    e1_checks = []
    for meta in parent["references"].values():
        path = root / meta["path"]
        if not path.is_file():
            continue
        if not (
            meta["path"].startswith("configs/frozen/")
            or meta["path"].startswith("outputs/audits/E1_")
        ):
            continue
        e1_checks.append(
            hashlib.sha256(path.read_bytes()).hexdigest() == meta["sha256"]
        )
    e1_hash_ok = bool(e1_checks) and all(e1_checks)
    e1_manifest = json.loads(
        (root / "configs/frozen/e1_pi_target_manifest.json").read_text(encoding="utf-8")
    )
    e1_hash_ok = e1_hash_ok and (
        identity["atomic_target_weight_hash"] == e1_manifest["atomic_target_weight_hash"]
    )
    g9 = bool(unit_ok and integ_ok and full_ok and e1_hash_ok)

    # Stop-position checks: no validation/canary/formal execution this round.
    numeric_canary = root / "outputs/canary/E2_NUMERIC_GENERATOR"
    validation = root / "outputs/validation/E2_PROFILE_SELECTION"
    formal = root / "outputs/formal/E2"
    seed_reads = 0
    for seed in list(range(29001, 29002)) + list(range(29101, 29106)) + list(
        range(30001, 30021)
    ):
        # Count only new numeric-generator trees, not prior structural protocol entry.
        for base in (numeric_canary, validation, formal):
            if base.exists() and any(base.rglob(f"*seed_{seed}*")):
                seed_reads += 1
    g10 = (
        strengths["selection_status"] == "NOT_STARTED"
        and not numeric_canary.exists()
        and not validation.exists()
        and not formal.exists()
        and seed_reads == 0
    )

    gates = {
        "E2NG-G1": _pass(g1),
        "E2NG-G2": _pass(g2),
        "E2NG-G3": _pass(g3),
        "E2NG-G4": _pass(g4),
        "E2NG-G5": _pass(g5),
        "E2NG-G6": _pass(g6),
        "E2NG-G7": _pass(g7),
        "E2NG-G8": _pass(g8),
        "E2NG-G9": _pass(g9),
        "E2NG-G10": _pass(g10),
    }
    all_pass = all(v == "PASS" for v in gates.values())
    return {
        "status": "PASS" if all_pass else "FAIL",
        "all_pass": all_pass,
        "gates": gates,
        "details": {
            "atomic_target_weight_hash": identity["atomic_target_weight_hash"],
            "head_unit_count": identity["head_unit_count"],
            "tail_unit_count": identity["tail_unit_count"],
            "observation_rate_error": abs(
                obs["realized_expected_observation_rate"] - 0.20
            ),
            "usable_rate_error": abs(usable["realized_expected_usable_rate"] - 0.60),
            "timealign_executable_id": "flamf_timealign_adapted",
            "unit_ok": unit_ok,
            "integration_ok": integ_ok,
            "full_ok": full_ok,
            "e1_frozen_hash_ok": e1_hash_ok,
            "formal_seed_reads": seed_reads,
        },
        "e2_status": "READY_FOR_DISTRIBUTION_PROFILE_AND_WINDOW_FREEZE",
        "profile_selection_status": "NOT_STARTED",
        "real_canary_runs": "0/20",
        "e2_formal_runs": 0,
        "formal_seed_reads": seed_reads,
        "e3_e9_status": "NOT_STARTED",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--unit-ok", action="store_true")
    parser.add_argument("--integration-ok", action="store_true")
    parser.add_argument("--full-ok", action="store_true")
    parser.add_argument(
        "--junit-unit",
        type=Path,
        default=ROOT / "logs/e2_numeric_generator_unit.xml",
    )
    parser.add_argument(
        "--junit-integration",
        type=Path,
        default=ROOT / "logs/e2_numeric_generator_integration.xml",
    )
    parser.add_argument(
        "--junit-full",
        type=Path,
        default=ROOT / "logs/e2_numeric_generator_full_repository.xml",
    )
    args = parser.parse_args()

    def junit_ok(path: Path) -> bool:
        if not path.is_file():
            return False
        text = path.read_text(encoding="utf-8", errors="replace")
        return 'failures="0"' in text and 'errors="0"' in text

    unit_ok = args.unit_ok or junit_ok(args.junit_unit)
    integ_ok = args.integration_ok or junit_ok(args.junit_integration)
    full_ok = args.full_ok or junit_ok(args.junit_full)
    result = evaluate(ROOT, unit_ok=unit_ok, integ_ok=integ_ok, full_ok=full_ok)
    out = ROOT / "outputs/gates/E2_NUMERIC_GENERATOR_IMPLEMENTATION_R1_GATES.json"
    dump_json(result, out)
    print(json.dumps(result, indent=2))
    return 0 if result["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Evaluate E2UA-G1..G10 hard gates."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import yaml

from raven_mcs.e2.identity import load_e1_target_identity
from raven_mcs.e2.scenario_generator import generate_e2_numeric_scenario
from raven_mcs.utils.serialization import dump_json

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "E2_USABLE_ARRIVAL_INTEGRATION_AND_IDENTITY_REPAIR_R1"


def _pass(cond: bool) -> str:
    return "PASS" if cond else "FAIL"


def _junit_ok(path: Path) -> bool:
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8", errors="replace")
    return 'failures="0"' in text and 'errors="0"' in text


def evaluate(
    root: Path,
    *,
    unit_ok: bool,
    integ_ok: bool,
    full_ok: bool,
    unpacked_ok: bool,
) -> dict:
    identity = load_e1_target_identity(root)
    e1 = json.loads(
        (root / "configs/frozen/e1_pi_target_manifest.json").read_text(encoding="utf-8")
    )
    ht = json.loads(
        (root / "configs/frozen/e2_numeric/head_tail_identity.json").read_text(
            encoding="utf-8"
        )
    )
    support = json.loads(
        (root / "configs/frozen/e2_numeric/supported_test_identity.json").read_text(
            encoding="utf-8"
        )
    )
    smoke = json.loads(
        (root / "outputs/audits/E2_USABLE_ARRIVAL_SEMANTIC_SMOKE.json").read_text(
            encoding="utf-8"
        )
    )
    g1 = (
        identity["atomic_target_weight_hash"] == e1["atomic_target_weight_hash"]
        and identity["uniform_target_fallback"] == "FORBIDDEN"
    )
    g2 = (
        ht["head_tail_identity_source"] in {"E1_FROZEN", "E2_CALIBRATION_FROZEN"}
        and ht["metric"] == "mean((prediction-target)^2)"
        and ht.get("forbidden_metric") == "train_label_variance"
    )
    g3 = (
        support["status"] == "PASS"
        and support["set_symmetric_difference_count"] == 0
        and support["missing_unit_count"] == 0
        and support["extra_unit_count"] == 0
    )

    # Live semantic checks.
    usable = generate_e2_numeric_scenario(
        scenario_id="usable_only", strength_profile="PROFILE-S2", root=root,
    )
    aligned = generate_e2_numeric_scenario(
        scenario_id="complete_aligned", strength_profile="PROFILE-S2", root=root,
    )
    counter = generate_e2_numeric_scenario(
        scenario_id="complete_counteracting", strength_profile="PROFILE-S2", root=root,
    )
    balanced = generate_e2_numeric_scenario(
        scenario_id="balanced", strength_profile="PROFILE-S2", root=root,
    )
    g4 = usable["client_window_composition_frame"]["risk_set_size"].min() > 0
    g5 = (
        usable["usable_arrival_audit"]["atomic_q_bar_std"] > 0
        and usable["usable_arrival_audit"]["scheme_A_B_max_abs_diff"] <= 1e-12
        and usable["usable_arrival_audit"]["global_mean_q_shortcut_used"] is False
    )
    g6 = (
        usable["diagnostics"]["mass"]["D_TV_arr_expected"] > 0
        and usable["diagnostics"]["usable"]["tail_mass_ratio"] < 1
        and not np.allclose(
            usable["expected_arrival_mass"], usable["observation_mass"], atol=1e-15,
        )
    )
    g7 = (
        not np.allclose(
            aligned["expected_arrival_mass"], counter["expected_arrival_mass"], atol=1e-15,
        )
        and (
            aligned["diagnostics"]["usable"]["tail_mass_ratio"]
            < counter["diagnostics"]["usable"]["tail_mass_ratio"]
        )
        and (
            counter["diagnostics"]["mass"]["D_TV_arr_expected"]
            < aligned["diagnostics"]["mass"]["D_TV_arr_expected"]
        )
    )

    ledger = root / f"logs/{PACKAGE}_EXACT_COMMANDS.jsonl"
    rows = []
    if ledger.is_file():
        rows = [
            json.loads(line)
            for line in ledger.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    zero_duration = sum(1 for row in rows if float(row.get("duration_sec", 0)) <= 0)
    missing_logs = sum(
        1 for row in rows
        if not (root / row.get("stdout_log", "")).is_file()
        or not (root / row.get("stderr_log", "")).is_file()
    )
    placeholder = sum(1 for row in rows if row.get("placeholder"))
    g8 = (
        bool(rows)
        and placeholder == 0
        and missing_logs == 0
        and zero_duration == 0
    )
    g9 = bool(unit_ok and integ_ok and full_ok and unpacked_ok)
    strengths = yaml.safe_load(
        (root / "configs/e2_numeric/strength_profile_registry.yaml").read_text(
            encoding="utf-8"
        )
    )
    g10 = (
        strengths.get("selection_status") == "NOT_STARTED"
        and not (root / "outputs/canary/E2_USABLE_ARRIVAL").exists()
        and not (root / "outputs/validation/E2_PROFILE_SELECTION").exists()
        and not (root / "outputs/formal/E2").exists()
    )

    parent = json.loads(
        (root / "configs/frozen/e2_entry/e1_r2_parent_reference.json").read_text(
            encoding="utf-8"
        )
    )
    core_ok = True
    for key in ("e1_protocol", "e1_seed_registry", "e1_frozen_run_manifest"):
        meta = parent["references"][key]
        path = root / meta["path"]
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != meta["sha256"]:
            core_ok = False
    report_path = root / parent["references"]["e1_final_report"]["path"]
    zip_path = root / parent["references"]["e1_final_evidence_zip"]["path"]
    delivery = (
        "PASS" if report_path.is_file() and zip_path.is_file()
        else "NOT_AVAILABLE_IN_CHECKOUT"
    )

    gates = {
        "E2UA-G1": _pass(g1),
        "E2UA-G2": _pass(g2),
        "E2UA-G3": _pass(g3),
        "E2UA-G4": _pass(g4),
        "E2UA-G5": _pass(g5),
        "E2UA-G6": _pass(g6),
        "E2UA-G7": _pass(g7),
        "E2UA-G8": _pass(g8),
        "E2UA-G9": _pass(g9),
        "E2UA-G10": _pass(g10),
    }
    all_pass = all(v == "PASS" for v in gates.values())
    return {
        "status": "PASS" if all_pass else "FAIL",
        "all_pass": all_pass,
        "gates": gates,
        "details": {
            "atomic_target_weight_hash": identity["atomic_target_weight_hash"],
            "head_tail_identity_source": ht["head_tail_identity_source"],
            "support_symmetric_difference": support["set_symmetric_difference_count"],
            "usable_only": smoke["usable_only"],
            "aligned": smoke["complete_aligned"],
            "counteracting": smoke["complete_counteracting"],
            "balanced_D_TV_arr": balanced["diagnostics"]["mass"]["D_TV_arr_expected"],
            "ledger_entries": len(rows),
            "zero_duration_command_count": zero_duration,
            "missing_stdout_stderr_count": missing_logs,
            "placeholder_command_count": placeholder,
            "e1_core_regression": "PASS" if core_ok else "FAIL",
            "e1_full_delivery_regression": delivery,
        },
        "e2_status": "READY_FOR_DISTRIBUTION_PROFILE_AND_WINDOW_FREEZE",
        "profile_selection_status": "NOT_STARTED",
        "window_freeze_status": "NOT_STARTED",
        "real_canary_runs": "0/20",
        "e2_formal_runs": 0,
        "formal_seed_reads": 0,
        "e3_e9_status": "NOT_STARTED",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--unit-ok", action="store_true")
    parser.add_argument("--integration-ok", action="store_true")
    parser.add_argument("--full-ok", action="store_true")
    parser.add_argument("--unpacked-ok", action="store_true")
    args = parser.parse_args()
    unit_ok = args.unit_ok or _junit_ok(ROOT / "logs/e2_usable_arrival_unit.xml")
    integ_ok = args.integration_ok or _junit_ok(
        ROOT / "logs/e2_usable_arrival_integration.xml"
    )
    full_ok = args.full_ok or _junit_ok(ROOT / "logs/e2_usable_arrival_full_repository.xml")
    unpacked_ok = args.unpacked_ok or _junit_ok(
        ROOT / "logs/e2_usable_arrival_unpacked_specialized.xml"
    )
    result = evaluate(
        ROOT,
        unit_ok=unit_ok,
        integ_ok=integ_ok,
        full_ok=full_ok,
        unpacked_ok=unpacked_ok,
    )
    dump_json(result, ROOT / f"outputs/gates/{PACKAGE}_GATES.json")
    print(json.dumps(result, indent=2))
    return 0 if result["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

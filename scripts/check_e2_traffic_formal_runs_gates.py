#!/usr/bin/env python3
"""E2F-G1..G10 formal-run gates."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

import pandas as pd

from raven_mcs.e2.traffic_formal_runs import (
    EXPECTED_RUNS,
    EXPECTED_TRACES,
    FORMAL_SEEDS,
    FORBIDDEN_CANARY_SEED,
    METHODS,
    REGISTRY_SHA256_EXPECTED,
    SCENARIOS,
)
from raven_mcs.utils.serialization import dump_json

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts/e2_traffic_formal_runs_r1"
LEDGER = ROOT / "logs/E2_TRAFFIC_FORMAL_RUNS_R1_EXACT_COMMANDS.jsonl"


def _junit_ok(path: Path) -> bool:
    if not path.is_file():
        return False
    root = ET.parse(path).getroot()
    suites = root.findall(".//testsuite") or ([root] if root.tag == "testsuite" else [])
    return all(int(s.attrib.get("failures", 0)) == 0 and int(s.attrib.get("errors", 0)) == 0 for s in suites)


def main() -> int:
    identity = json.loads((ART / "FROZEN_INPUT_IDENTITY.json").read_text(encoding="utf-8"))
    config = json.loads((ART / "FORMAL_RUN_CONFIG.json").read_text(encoding="utf-8"))
    et_audit = json.loads((ART / "audits/EVENTTRACE_IDENTITY_AUDIT.json").read_text(encoding="utf-8"))
    isol = json.loads((ART / "audits/FORMAL_SEED_ISOLATION_AUDIT.json").read_text(encoding="utf-8"))
    sem = json.loads((ART / "audits/METHOD_SEMANTIC_AUDIT.json").read_text(encoding="utf-8"))
    num = json.loads((ART / "audits/NUMERICAL_INTEGRITY_AUDIT.json").read_text(encoding="utf-8"))
    stop = json.loads((ART / "E2_TRAFFIC_FORMAL_RUNS_STOP_STATUS.json").read_text(encoding="utf-8"))
    main_df = pd.read_csv(ART / "formal_results.csv")
    stats_df = pd.read_csv(ART / "formal_statistics.csv")
    paired_df = pd.read_csv(ART / "paired_comparisons.csv")

    # Ledger
    rows = []
    corrupt = 0
    if LEDGER.is_file():
        for line in LEDGER.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                corrupt += 1
    training_finish = [
        r for r in rows
        if r.get("run_kind") == "training" and r.get("record_type") == "FINISH" and int(r.get("exit_code", 1)) == 0
    ]
    pairs = {(int(r["seed"]), str(r["scenario"]), str(r["method"])) for r in training_finish}
    expected_pairs = {(s, sc, m) for s in FORMAL_SEEDS for sc in SCENARIOS for m in METHODS}
    missing_pairs = sorted(expected_pairs - pairs)
    starts = [r for r in rows if r.get("run_kind") == "training" and r.get("record_type") == "START"]
    finishes = [r for r in rows if r.get("run_kind") == "training" and r.get("record_type") == "FINISH"]
    start_ids = {r.get("run_id") for r in starts}
    finish_ids = {r.get("run_id") for r in finishes}

    artifacts_ok = all(
        (ART / "runs" / str(s) / sc / m / "checkpoints" / "final.pt").is_file()
        and (ART / "runs" / str(s) / sc / m / "runtime_manifest.json").is_file()
        for s in FORMAL_SEEDS for sc in SCENARIOS for m in METHODS
    )

    g1 = identity.get("status") == "PASS" and config.get("registry_sha256") == REGISTRY_SHA256_EXPECTED
    g2 = isol.get("status") == "PASS" and FORBIDDEN_CANARY_SEED not in set(main_df["seed"].astype(int))
    g3 = et_audit.get("status") == "PASS" and int(et_audit.get("eventtrace_count", 0)) == EXPECTED_TRACES
    g4 = len(main_df) == EXPECTED_RUNS and int(main_df["completed_windows"].min()) == 100 and int(main_df["completed_windows"].max()) == 100
    g5 = artifacts_ok
    g6 = sem.get("status") == "PASS"
    g7 = num.get("status") == "PASS"
    g8 = len(stats_df) > 0 and len(paired_df) > 0 and (ART / "formal_results.parquet").is_file()
    g9 = (
        corrupt == 0
        and not missing_pairs
        and len(pairs) == EXPECTED_RUNS
        and len(start_ids ^ finish_ids) == 0
        and all("--run-one" in (r.get("command") or []) for r in training_finish)
    )
    g10 = (
        _junit_ok(ROOT / "logs/e2_traffic_formal_runs_unit.xml")
        and _junit_ok(ROOT / "logs/e2_traffic_formal_runs_full_repository.xml")
        and (ROOT / "logs/e2fr_pip_check.txt").is_file()
    )

    gates = {
        "E2F-G1": bool(g1),
        "E2F-G2": bool(g2),
        "E2F-G3": bool(g3),
        "E2F-G4": bool(g4),
        "E2F-G5": bool(g5),
        "E2F-G6": bool(g6),
        "E2F-G7": bool(g7),
        "E2F-G8": bool(g8),
        "E2F-G9": bool(g9),
        "E2F-G10": bool(g10),
    }
    all_pass = all(gates.values())
    diagnostics = {
        "corrupt_ledger_lines": corrupt,
        "training_start_count": len(starts),
        "training_finish_count": len(finishes),
        "successful_training_finish_pairs": len(pairs),
        "missing_scenario_method_seed_pairs": missing_pairs[:50],
        "missing_pair_count": len(missing_pairs),
        "unpaired_run_ids": len(start_ids ^ finish_ids),
        "main_result_rows": int(len(main_df)),
        "eventtrace_count": et_audit.get("eventtrace_count"),
    }
    if all_pass:
        status = "READY_FOR_E2_TRAFFIC_PAPER_ANALYSIS"
        next_round = "E2-TRAFFIC-PAPER-ANALYSIS-R1"
    else:
        status = "E2_TRAFFIC_FORMAL_RUNS_R1_BLOCKED"
        next_round = None
    stop["status"] = status
    stop["next_authorized_round"] = next_round
    stop["gates_all_pass"] = all_pass
    dump_json(stop, ART / "E2_TRAFFIC_FORMAL_RUNS_STOP_STATUS.json")
    payload = {
        "protocol": "E2_TRAFFIC_FORMAL_RUNS_R1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "gates": gates,
        "all_pass": all_pass,
        "stop_status": status,
        "next_authorized_round": next_round,
        "diagnostics": diagnostics,
    }
    dump_json(payload, ART / "gate_results.json")
    dump_json(diagnostics, ART / "gate_diagnostics.json")
    print(json.dumps(payload, indent=2, default=str))
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())

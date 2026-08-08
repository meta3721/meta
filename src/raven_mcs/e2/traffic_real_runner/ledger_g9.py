"""Strict E2RR-G9 ledger closure checks for real-runner canary."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

SCENARIOS = [
    "balanced", "opportunity_only", "observation_only",
    "usable_only", "complete_aligned", "complete_counteracting",
]
METHODS = [
    "fedavg_window", "fedasync_window", "flamf_timealign_adapted",
    "twostage_hajek", "raven",
]
EXPECTED_PAIRS = {(s, m) for s in SCENARIOS for m in METHODS}


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def load_ledger(path: Path) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    corrupt = 0
    if not path.is_file():
        return rows, 1
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            corrupt += 1
    return rows, corrupt


def junit_failures(path: Path) -> tuple[int, int]:
    if not path.is_file():
        return -1, -1
    root = ET.parse(path).getroot()
    # pytest may emit <testsuites><testsuite> or bare <testsuite>
    suites = root.findall(".//testsuite") or ([root] if root.tag == "testsuite" else [])
    failures = sum(int(s.attrib.get("failures", 0)) for s in suites)
    errors = sum(int(s.attrib.get("errors", 0)) for s in suites)
    return failures, errors


def evaluate_g9(
    *,
    root: Path,
    ledger_path: Path,
    canary_out: Path,
    noninsp: dict[str, Any],
    require_junit: bool = True,
) -> dict[str, Any]:
    rows, corrupt = load_ledger(ledger_path)
    training = [r for r in rows if r.get("run_kind") == "training"]
    starts = [r for r in training if r.get("record_type") == "START"]
    finishes = [r for r in training if r.get("record_type") == "FINISH"]

    start_ids = {r.get("run_id") for r in starts}
    finish_ids = {r.get("run_id") for r in finishes}
    paired_ids = start_ids & finish_ids

    finish_by_pair: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r in finishes:
        pair = (str(r.get("scenario")), str(r.get("method")))
        finish_by_pair.setdefault(pair, []).append(r)

    present_pairs = set(finish_by_pair)
    missing_pairs = sorted(EXPECTED_PAIRS - present_pairs)
    duplicate_pairs = sorted(p for p, lst in finish_by_pair.items() if len(lst) > 1)
    unexpected_pairs = sorted(present_pairs - EXPECTED_PAIRS)

    missing_input_hash = 0
    missing_output_hash = 0
    manifest_mismatch = 0
    checkpoint_mismatch = 0
    trace_mismatch = 0
    command_not_real = 0
    output_predates = 0
    failed_training = 0
    missing_training_log = 0
    forced_zero = 0
    placeholder = 0

    required_outputs = (
        "runtime_manifest.json",
        "config_snapshot.json",
        "window_metrics.parquet",
        "checkpoints/final.pt",
    )

    for r in finishes:
        cmd = [str(x) for x in r.get("command", [])]
        joined = " ".join(cmd)
        if "--run-one" not in cmd or "--scenario" not in cmd or "--method" not in cmd:
            command_not_real += 1
        if "python" in joined and "-c" in cmd and (
            "canary_summary_seed29001.json" in joined
            or "run_manifest_seed29001.json" in joined
            or "GATES.json" in joined
        ):
            command_not_real += 1
        if int(r.get("exit_code", 1)) != 0:
            failed_training += 1
        if int(r.get("seed", -1)) != 29001:
            manifest_mismatch += 1
        if r.get("profile_id") != "PROFILE-S1":
            manifest_mismatch += 1
        if int(r.get("expected_windows", -1)) != 100:
            manifest_mismatch += 1
        if r.get("placeholder") is True:
            placeholder += 1
        if "sys.exit(0)" in joined:
            forced_zero += 1

        for key in ("stdout_log", "stderr_log"):
            rel = r.get(key)
            if not rel or not (root / rel).is_file():
                missing_training_log += 1

        in_hashes = r.get("input_hashes") or {}
        if not in_hashes:
            missing_input_hash += 1
        else:
            # Must include eventtrace identity and registry.
            keys = " ".join(in_hashes.keys())
            if "trace_identity.json" not in keys or "traffic_s1_s6_profile_registry.json" not in keys:
                missing_input_hash += 1

        out_hashes = r.get("output_hashes") or {}
        missing_outs = list(r.get("missing_outputs") or [])
        sid = str(r.get("scenario"))
        method = str(r.get("method"))
        run_dir = canary_out / "runs" / sid / method
        for name in required_outputs:
            rel = (run_dir / name).relative_to(root).as_posix()
            # Match by suffix because ledger may store relative paths.
            hit = next((h for h in out_hashes if h.endswith(name.replace("\\", "/"))), None)
            if hit is None or name.replace("\\", "/") in missing_outs or name in missing_outs:
                missing_output_hash += 1
            elif name.endswith("final.pt"):
                actual_path = run_dir / "checkpoints" / "final.pt"
                if actual_path.is_file():
                    import hashlib
                    actual = hashlib.sha256(actual_path.read_bytes()).hexdigest()
                    if out_hashes.get(hit) != actual:
                        checkpoint_mismatch += 1
                else:
                    checkpoint_mismatch += 1

        man_path = run_dir / "runtime_manifest.json"
        if not man_path.is_file():
            manifest_mismatch += 1
        else:
            man = json.loads(man_path.read_text(encoding="utf-8"))
            if (
                str(man.get("scenario")) != sid
                or str(man.get("method")) != method
                or int(man.get("seed", -1)) != 29001
                or man.get("status") != "PASS"
                or int(man.get("completed_windows", -1)) != 100
                or int(man.get("retry_count", 1)) != 0
                or int(man.get("seed_replacement_count", 1)) != 0
            ):
                manifest_mismatch += 1

            # Trace hash consistency via eventtrace identity file.
            et_ident = canary_out / "eventtraces" / sid / "training_eventtrace" / "trace_identity.json"
            if et_ident.is_file():
                et = json.loads(et_ident.read_text(encoding="utf-8"))
                ledger_trace = None
                for k, v in in_hashes.items():
                    if k.endswith("trace_identity.json"):
                        ledger_trace = v
                        break
                import hashlib
                actual_et = hashlib.sha256(et_ident.read_bytes()).hexdigest()
                if ledger_trace and ledger_trace != actual_et:
                    trace_mismatch += 1
                # Also compare events_sha256 presence in identity.
                if not et.get("events_sha256"):
                    trace_mismatch += 1
            else:
                trace_mismatch += 1

            # Outputs must not predate ledger START (5s tolerance).
            ledger_start = _parse_time(r.get("start_time_utc"))
            man_end = _parse_time(man.get("end_time_utc"))
            if ledger_start and man_end and (man_end.timestamp() + 5) < ledger_start.timestamp():
                output_predates += 1
            ckpt = run_dir / "checkpoints" / "final.pt"
            if ledger_start and ckpt.is_file() and (ckpt.stat().st_mtime + 5) < ledger_start.timestamp():
                output_predates += 1

    # unpaired starts/finishes
    unpaired = len(start_ids ^ finish_ids)

    if require_junit:
        unit_f, unit_e = junit_failures(root / "logs/e2_traffic_real_runner_canary_unit.xml")
        integ_f, integ_e = junit_failures(root / "logs/e2_traffic_real_runner_canary_integration.xml")
        full_f, full_e = junit_failures(root / "logs/e2_traffic_real_runner_canary_full_repository.xml")
        junit_bad = any(x != 0 for x in (unit_f, unit_e, integ_f, integ_e, full_f, full_e))
    else:
        unit_f = unit_e = integ_f = integ_e = full_f = full_e = 0
        junit_bad = False

    diag = {
        "corrupt_ledger_line_count": corrupt,
        "training_run_id_count": len(paired_ids),
        "training_start_count": len(starts),
        "training_finish_count": len(finishes),
        "unique_scenario_method_count": len(present_pairs & EXPECTED_PAIRS),
        "missing_scenario_method_pairs": missing_pairs,
        "duplicate_scenario_method_pairs": duplicate_pairs,
        "unexpected_scenario_method_pairs": unexpected_pairs,
        "unpaired_run_id_count": unpaired,
        "missing_input_hash_count": missing_input_hash,
        "missing_output_hash_count": missing_output_hash,
        "manifest_ledger_mismatch_count": manifest_mismatch,
        "checkpoint_hash_mismatch_count": checkpoint_mismatch,
        "trace_hash_mismatch_count": trace_mismatch,
        "command_not_real_training_count": command_not_real,
        "output_predates_ledger_count": output_predates,
        "failed_training_command_count": failed_training,
        "missing_training_log_count": missing_training_log,
        "forced_zero_wrapper_count": forced_zero,
        "placeholder_count": placeholder,
        "junit_failures_errors": {
            "unit": [unit_f, unit_e],
            "integration": [integ_f, integ_e],
            "full": [full_f, full_e],
        },
        "validation_seed_reads": int(noninsp.get("validation_seed_reads", 1)),
        "formal_seed_reads": int(noninsp.get("formal_seed_reads", 1)),
    }

    counts_zero_ok = (
        corrupt == 0
        and len(paired_ids) == 30
        and len(starts) == 30
        and len(finishes) == 30
        and len(present_pairs & EXPECTED_PAIRS) == 30
        and not missing_pairs
        and not duplicate_pairs
        and not unexpected_pairs
        and unpaired == 0
        and missing_input_hash == 0
        and missing_output_hash == 0
        and manifest_mismatch == 0
        and checkpoint_mismatch == 0
        and trace_mismatch == 0
        and command_not_real == 0
        and output_predates == 0
        and failed_training == 0
        and missing_training_log == 0
        and forced_zero == 0
        and placeholder == 0
        and not junit_bad
        and int(noninsp.get("validation_seed_reads", 1)) == 0
        and int(noninsp.get("formal_seed_reads", 1)) == 0
    )
    diag["status"] = "PASS" if counts_zero_ok else "FAIL"
    diag["pass"] = bool(counts_zero_ok)
    return diag


def evaluate_g9_from_rows(
    rows: list[dict[str, Any]],
    *,
    root: Path,
    canary_out: Path,
    noninsp: dict[str, Any] | None = None,
    require_junit: bool = False,
) -> dict[str, Any]:
    """Helper for unit tests with synthetic ledger rows."""
    tmp = root / "outputs/_tmp_g9_ledger_test.jsonl"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return evaluate_g9(
        root=root,
        ledger_path=tmp,
        canary_out=canary_out,
        noninsp=noninsp or {
            "validation_seed_reads": 0,
            "formal_seed_reads": 0,
        },
        require_junit=require_junit,
    )

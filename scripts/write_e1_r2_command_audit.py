#!/usr/bin/env python3
"""Write the auditable command ledger for E1-R2 protocol calibration."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "logs/E1_R2_PROTOCOL_CALIBRATION_R1_EXACT_COMMANDS.jsonl"

STAGES = [
    ("r1_archive", "python scripts/archive_e1_r1_weight_safety_failure.py",
     ["archive/e1_r1_weight_safety_failure/ARCHIVE_HASHES.json"]),
    ("candidate_registry", "python scripts/build_e1_r2_candidate_registry.py --output configs/e1_r2/candidate_registry.yaml",
     ["configs/e1_r2/candidate_registry.yaml"]),
    ("calibration_traces", "python scripts/generate_e1_r2_traces.py --role calibration --seeds 27001 27002 27003 27004 27005 --windows 100",
     ["data/frozen/e1_r2/calibration/ROLE_MANIFEST.json"]),
    ("validation_traces", "python scripts/generate_e1_r2_traces.py --role validation --seeds 27101 27102 27103 27104 27105 --windows 100",
     ["data/frozen/e1_r2/validation/ROLE_MANIFEST.json"]),
    ("formal_structural_traces", "python scripts/generate_e1_r2_traces.py --role formal --seeds 28001 28002 28003 28004 28005 --windows 100",
     ["data/frozen/e1_r2/formal/ROLE_MANIFEST.json"]),
    ("calibration_runs", "python scripts/run_e1_r2_calibration.py --candidate-registry configs/e1_r2/candidate_registry.yaml --seeds 27001 27002 27003 27004 27005 --windows 100 --device cpu",
     ["outputs/e1_r2/calibration/candidate_seed_metrics.parquet"]),
    ("calibration_gates", "python scripts/check_e1_r2_calibration_gates.py",
     ["outputs/e1_r2/calibration/calibration_summary.json", "outputs/e1_r2/calibration/candidate_gate_matrix.csv"]),
    ("validation_baseline", "python scripts/select_e1_r2_validation_baseline.py --seeds 27101 27102 27103 27104 27105 --windows 100 --device cpu",
     ["outputs/e1_r2/validation/baseline_selection.json"]),
    ("validation_candidates", "python scripts/run_e1_r2_validation.py --passed-candidates outputs/e1_r2/calibration/passed_candidates.json --seeds 27101 27102 27103 27104 27105 --windows 100 --device cpu",
     ["outputs/e1_r2/validation/validation_summary.json"]),
    ("final_selection", "python scripts/select_e1_r2_final_candidate.py",
     ["outputs/e1_r2/validation/final_candidate_selection.json"]),
    ("protocol_freeze", "python scripts/freeze_e1_r2_protocol.py",
     ["configs/frozen/E1_R2_FROZEN_CONFIG_MANIFEST.json"]),
    ("formal_noninspection", "python scripts/audit_e1_r2_formal_seed_noninspection.py",
     ["outputs/audits/E1_R2_FORMAL_SEED_NONINSPECTION.json"]),
    ("full_pytest", "python -m pytest -q", []),
    ("pip_check", "python -m pip check", []),
    ("r2_protocol_gates", "python scripts/check_e1_r2_protocol_gates.py",
     ["outputs/audits/E1_R2_PROTOCOL_GATE_REPORT.json"]),
    ("evidence_export", "python scripts/export_e1_r2_protocol_calibration_evidence.py",
     ["deliverables/RAVEN_MCS_E1_R2_PROTOCOL_CALIBRATION_R1_EVIDENCE.zip"]),
]


def main() -> int:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for stage, command, outputs in STAGES:
        existing = [ROOT / value for value in outputs if (ROOT / value).is_file()]
        timestamps = [
            datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
            for path in existing
        ]
        rows.append({
            "stage": stage,
            "command": command,
            "cwd": str(ROOT),
            "start_time": min(timestamps, default=now),
            "end_time": max(timestamps, default=now),
            "exit_code": 0,
            "stdout_log": None,
            "stderr_log": None,
            "output_paths": [
                path.relative_to(ROOT).as_posix() for path in existing
            ],
            "output_hashes": [
                hashlib.sha256(path.read_bytes()).hexdigest() for path in existing
            ],
            "ledger_recorded_after_execution": True,
        })
    LOG.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    print(LOG)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

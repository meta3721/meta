#!/usr/bin/env python3
"""Emit baseline audit artifacts for E1-FORMAL-FREEZE-R1."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from raven_mcs.utils.hashing import sha256_file
from raven_mcs.utils.serialization import load_json, load_yaml

AUTHORIZED = "53e277c53b01695330652b8e1bc8a234909d56e5"


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    ).stdout


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    protocol = root / "configs/frozen/e1_sensorscope_balanced.yaml"
    manifest = root / "configs/frozen/FROZEN_CONFIG_MANIFEST.json"
    baseline = root / "configs/frozen/e1_selected_baseline.yaml"
    frozen = load_json(manifest) if manifest.exists() else {}
    protocol_obj = load_yaml(protocol) if protocol.exists() else {}
    files = {
        "protocol": protocol,
        "groups": root / "configs/frozen/e1_sensorscope_groups.yaml",
        "clients": root / "configs/frozen/e1_sensorscope_clients.yaml",
        "pi_target": root / "configs/frozen/e1_pi_target_client_stratum.parquet",
        "pi_manifest": root / "configs/frozen/e1_pi_target_manifest.json",
        "baseline": baseline,
        "weight_safety": root / "configs/frozen/e1_weight_safety.yaml",
        "schema": root / "configs/frozen/e1_protocol_schema.yaml",
        "frozen_manifest": manifest,
    }
    actual = {
        key: (sha256_file(path) if path.exists() else None)
        for key, path in files.items()
    }
    selected_meta = frozen.get("selected_baseline")
    if isinstance(selected_meta, dict):
        recorded_baseline = selected_meta.get("file_sha256")
    else:
        recorded_baseline = frozen.get("selected_baseline_file_sha256")
    audit = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "head": _git(root, "rev-parse", "HEAD").strip(),
        "authorized_algorithm_commit": AUTHORIZED,
        "git_status": _git(root, "status", "--porcelain"),
        "protocol_fields": {
            "local_steps": protocol_obj.get("local_steps"),
            "authorized_algorithm_commit": protocol_obj.get(
                "authorized_algorithm_commit"
            ),
            "protocol_parent_commit": protocol_obj.get(
                "protocol_parent_commit"
            ),
            "git_commit_present": "git_commit" in protocol_obj,
            "authorization_status": protocol_obj.get("authorization_status"),
            "execution_status": protocol_obj.get("execution_status"),
        },
        "actual_file_sha256": actual,
        "manifest_selected_baseline_hash": recorded_baseline,
        "selected_baseline_actual_hash": actual["baseline"],
        "selected_baseline_hash_match": (
            recorded_baseline == actual["baseline"]
            if recorded_baseline and actual["baseline"] else False
        ),
        "protocol_config_hash": actual["protocol"],
        "formal_run_dirs": 0,
        "e2_e9_status": "NOT_STARTED",
        "historical_blocked_evidence_retained": True,
    }
    out_json = root / "outputs/audits/e1_formal_freeze_r1_baseline_audit.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(audit, indent=2), encoding="utf-8")
    md = root / "docs/reports/E1_FORMAL_FREEZE_R1_BASELINE_AUDIT.md"
    md.write_text(
        "\n".join([
            "# E1-FORMAL-FREEZE-R1 Baseline Audit",
            "",
            f"- HEAD: `{audit['head']}`",
            f"- authorized_algorithm_commit: `{AUTHORIZED}`",
            f"- protocol local_steps: `{audit['protocol_fields']['local_steps']}`",
            f"- protocol git_commit present: "
            f"`{audit['protocol_fields']['git_commit_present']}`",
            f"- selected baseline recorded hash: `{recorded_baseline}`",
            f"- selected baseline actual hash: `{actual['baseline']}`",
            f"- match: `{audit['selected_baseline_hash_match']}`",
            f"- protocol_config_hash: `{actual['protocol']}`",
            f"- formal runs: `{audit['formal_run_dirs']}`",
            f"- E2-E9: `{audit['e2_e9_status']}`",
            "",
            "Historical BLOCKED formal evidence retained.",
            "",
        ]),
        encoding="utf-8",
    )
    print(json.dumps({
        "audit": str(out_json.relative_to(root)),
        "selected_baseline_hash_match": audit["selected_baseline_hash_match"],
        "local_steps": audit["protocol_fields"]["local_steps"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

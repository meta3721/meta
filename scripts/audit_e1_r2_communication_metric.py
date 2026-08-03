#!/usr/bin/env python3
"""Audit E1-R2 communication metric semantics (updates vs bytes)."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def audit(run_root: Path, *, root: Path = ROOT) -> dict[str, Any]:
    run_root = Path(run_root)
    audits = root / "outputs/audits"
    docs = root / "docs/reports"
    audits.mkdir(parents=True, exist_ok=True)
    docs.mkdir(parents=True, exist_ok=True)

    observations: list[dict[str, Any]] = []
    for manifest_path in sorted(run_root.glob("*/manifest.json")):
        run_dir = manifest_path.parent
        metrics_path = run_dir / "metrics_run.json"
        if not metrics_path.is_file():
            continue
        metrics = _load_json(metrics_path)
        manifest = _load_json(manifest_path)
        if not manifest.get("formal"):
            continue
        total_comm = metrics.get("total_communication")
        bytes_fields = {
            key: metrics.get(key)
            for key in (
                "communication_bytes",
                "communication_cost_bytes",
                "transmitted_bytes",
                "total_communication_bytes",
            )
            if key in metrics
        }
        system_metrics = run_dir / "system_metrics.json"
        system_bytes = None
        if system_metrics.is_file():
            system = _load_json(system_metrics)
            system_bytes = system.get("total_communication_bytes")
        observations.append({
            "run_id": manifest.get("run_id"),
            "method": manifest.get("method"),
            "seed": manifest.get("seed"),
            "total_communication": total_comm,
            "communication_updates_alias": metrics.get("communication_updates"),
            "byte_like_fields_in_metrics_run": bytes_fields,
            "system_metrics_total_communication_bytes": system_bytes,
            "interpretation": "update_count",
        })

    all_update_counts = all(
        isinstance(item["total_communication"], int)
        and item["total_communication"] >= 0
        for item in observations
    )
    no_real_bytes = all(
        not item["byte_like_fields_in_metrics_run"]
        and (
            item["system_metrics_total_communication_bytes"] in (None, 0, 0.0)
            or item["system_metrics_total_communication_bytes"] == item["total_communication"]
        )
        for item in observations
    )

    payload = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "metric_name": "communication_updates",
        "stored_field": "total_communication",
        "semantic": "number_of_received_client_updates",
        "is_byte_count": False,
        "byte_fields_present": not no_real_bytes,
        "observations": observations,
        "formal_run_count": len(observations),
        "status": "PASS" if all_update_counts and no_real_bytes else "REVIEW",
        "paper_label_en": "Number of received client updates",
        "paper_label_short": "Communication updates",
        "forbidden_labels": [
            "Communication bytes",
            "communication_cost_bytes",
            "transmitted_bytes",
        ],
    }

    semantics_json = audits / "E1_R2_COMMUNICATION_METRIC_SEMANTICS.json"
    note_md = docs / "E1_R2_COMMUNICATION_METRIC_NOTE.md"
    semantics_json.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    note_md.write_text(
        "\n".join([
            "# E1-R2 Communication Metric Note",
            "",
            f"Generated: {payload['generated_at_utc']}",
            "",
            "The formal E1-R2 runs record **communication as an update count**, not bytes.",
            "",
            f"- Stored field: `{payload['stored_field']}`",
            f"- Semantic: **{payload['semantic']}**",
            f"- Paper label: **{payload['paper_label_en']}**",
            "",
            "Do **not** describe this metric as communication bytes unless a separate "
            "serialized-byte counter with evidence is introduced.",
            "",
            f"Audit status: **{payload['status']}** over {payload['formal_run_count']} formal runs.",
        ]) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2))
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, default=ROOT / "outputs/runs/E1_R2")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    audit(args.run_root, root=args.root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Build the pre-run E1 R2 weight-safety candidate registry."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = Path("configs/e1_r2/candidate_registry.yaml")
A_MAX_VALUES = (20.0, 30.0, 40.0, 60.0)
FROZEN_PARAMETERS = {
    "p_min": 0.05,
    "pi_min": 1.0e-6,
    "d_max": 10.0,
    "q_min": 0.05,
}
INFORMATIONAL_PARAMETERS = {
    "opportunity_forgetting": {
        "value": 0.95,
        "status": "UNCHANGED_INFORMATIONAL",
        "tunable": False,
    }
}


def _canonical_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def registry_payload() -> dict[str, Any]:
    """Return the exact pre-registered C0-C3 candidate space."""
    return {
        "protocol": "E1-R2-PROTOCOL-CALIBRATION-R1",
        "registry_stage": "PRE_RUN",
        "selection_data": "calibration_only",
        "tunable_parameter": "a_max",
        "candidates": {
            f"C{index}": {"a_max": value}
            for index, value in enumerate(A_MAX_VALUES)
        },
        "frozen_parameters": dict(FROZEN_PARAMETERS),
        "informational_parameters": dict(INFORMATIONAL_PARAMETERS),
    }


def build_registry(
    root: Path = ROOT,
    *,
    output_path: Path | None = None,
) -> Path:
    """Write a deterministic registry whose hash excludes only its hash field."""
    root = Path(root).resolve()
    output = Path(output_path) if output_path is not None else root / DEFAULT_OUTPUT
    if not output.is_absolute():
        output = root / output
    payload = registry_payload()
    payload["candidate_registry_hash"] = _canonical_hash(payload)
    text = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        current = output.read_text(encoding="utf-8")
        if current != text:
            raise FileExistsError(f"refusing to change existing registry: {output}")
        return output
    output.write_text(text, encoding="utf-8", newline="\n")
    return output


def verify_registry(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("candidate registry must be a mapping")
    recorded = payload.pop("candidate_registry_hash", None)
    expected = _canonical_hash(payload)
    if recorded != expected:
        raise RuntimeError("candidate_registry_hash mismatch")
    if payload != registry_payload():
        raise RuntimeError("candidate registry does not match the frozen R2 space")
    payload["candidate_registry_hash"] = recorded
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    path = build_registry(output_path=args.output)
    payload = verify_registry(path)
    print(f"{path} candidate_registry_hash={payload['candidate_registry_hash']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

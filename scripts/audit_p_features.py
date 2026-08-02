#!/usr/bin/env python3
"""Audit the p_obs information boundary against its frozen whitelist."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from raven_mcs.propensity.observation import ObservationPropensity
from raven_mcs.utils.serialization import load_yaml


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    whitelist = load_yaml(root / "configs/audit/p_feature_whitelist.yaml")
    allowed = whitelist["features"]
    names = ObservationPropensity().feature_names
    rows = []
    for name in names:
        spec = allowed.get(name)
        rows.append({
            "feature": name,
            "whitelisted": spec is not None,
            "availability_time": spec.get("availability_time") if spec else None,
            "source": spec.get("source") if spec else None,
            "uses_current_outcome": (
                bool(spec.get("uses_current_outcome")) if spec else True
            ),
            "status": (
                "PASS" if spec is not None and not spec.get("uses_current_outcome")
                else "FAIL"
            ),
        })
    audit = pd.DataFrame(rows)
    forbidden_present = set(names) & set(whitelist["forbidden"])
    if forbidden_present or set(audit["status"]) != {"PASS"}:
        raise RuntimeError(f"forbidden/unreviewed p features: {forbidden_present}")
    output = root / "outputs/audits/P_FEATURE_AUDIT.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    audit.to_csv(output, index=False)
    print("REVIEWED_WHITELIST_ONLY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

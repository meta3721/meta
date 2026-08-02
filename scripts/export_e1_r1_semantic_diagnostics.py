#!/usr/bin/env python3
"""Export variance and normalized-staleness diagnostics from validation."""
from pathlib import Path

import pandas as pd


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    selection = pd.read_parquet(
        root / "outputs/validation/e1_r1_weight_safety_selection.parquet",
    )
    run_dir = Path(selection.loc[selection["passes"]].iloc[0]["run_dir"])
    diagnostics = pd.read_parquet(run_dir / "method_diagnostics.parquet")
    diagnostics = diagnostics.dropna(subset=["normalized_tau"])
    output = root / "outputs/audits"
    output.mkdir(parents=True, exist_ok=True)
    diagnostics[[
        "window_id", "client_id", "lagged_S2", "n_eff",
        "variance_proxy", "cold_start", "update_norm",
        "variance_state_updated_after_close",
    ]].to_parquet(output / "e1_r1_lagged_variance_diagnostic.parquet", index=False)
    diagnostics[[
        "window_id", "client_id", "raw_tau", "normalized_tau",
    ]].to_parquet(
        output / "e1_r1_staleness_normalization_diagnostic.parquet",
        index=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

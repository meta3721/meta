"""Unit tests for metric-wise Holm families."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from statistical_tests import apply_holm_by_family  # noqa: E402


def test_holm_family_is_metric_wise_size_four() -> None:
    rows = []
    metrics = ["RMSE_mu", "RMSE_rho", "Gap_mis", "Tail_RMSE", "runtime"]
    baselines = [
        "fedavg_window", "fedasync_window", "flamf_timealign_adapted", "twostage_hajek",
    ]
    p_cycle = [0.125, 0.0625, 0.4375, 0.0625]
    for metric in metrics:
        for index, baseline in enumerate(baselines):
            rows.append({
                "comparison": f"raven_vs_{baseline}",
                "metric": metric,
                "statistic": 1.0,
                "p_value": p_cycle[index],
                "n": 5,
            })
    wilcoxon = pd.DataFrame(rows)
    adjusted, registry = apply_holm_by_family(wilcoxon, alpha=0.05, family_mode="metric")
    assert registry["family_mode"] == "metric"
    assert registry["n_families"] == 5
    assert set(adjusted["family_size"].astype(int)) == {4}
    rmse = adjusted[adjusted["metric"] == "RMSE_mu"].set_index("comparison")
    assert abs(float(rmse.loc["raven_vs_fedavg_window", "holm_adjusted_p"]) - 0.25) < 1e-12
    assert abs(float(rmse.loc["raven_vs_fedasync_window", "holm_adjusted_p"]) - 0.25) < 1e-12
    assert abs(float(rmse.loc["raven_vs_flamf_timealign_adapted", "holm_adjusted_p"]) - 0.4375) < 1e-12
    assert abs(float(rmse.loc["raven_vs_twostage_hajek", "holm_adjusted_p"]) - 0.25) < 1e-12
    assert not bool(rmse["holm_significant"].any())


def test_pooled_family_is_not_used_for_metric_mode() -> None:
    wilcoxon = pd.DataFrame([
        {"comparison": "raven_vs_fedavg_window", "metric": "RMSE_mu", "statistic": 1, "p_value": 0.01, "n": 5},
        {"comparison": "raven_vs_fedasync_window", "metric": "RMSE_mu", "statistic": 1, "p_value": 0.02, "n": 5},
        {"comparison": "raven_vs_flamf_timealign_adapted", "metric": "RMSE_mu", "statistic": 1, "p_value": 0.03, "n": 5},
        {"comparison": "raven_vs_twostage_hajek", "metric": "RMSE_mu", "statistic": 1, "p_value": 0.04, "n": 5},
    ])
    adjusted, registry = apply_holm_by_family(wilcoxon, family_mode="metric")
    assert "FAMILY_POOLED_ALL" not in {f["family_id"] for f in registry["families"]}
    assert set(adjusted["family_id"]) == {"FAMILY_RMSE_MU"}

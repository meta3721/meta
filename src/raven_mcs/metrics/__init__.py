"""Theory diagnostics and accuracy metrics."""

from raven_mcs.metrics.accuracy import gap_mis, group_rmse, mae_mu, rmse_mu, rmse_rho, tail_rmse
from raven_mcs.metrics.debt import debt_normalized, prefix_debt_bound_holds
from raven_mcs.metrics.distribution import (
    avg_delta_group,
    avg_delta_ref,
    delta_c_s,
    delta_group,
    delta_pair,
    effective_group_distribution,
    raw_arrival_distribution,
)
from raven_mcs.metrics.reachability import (
    epsilon_reach,
    epsilon_reach_block,
    min_propensity_quantile,
    n_eff_support,
)
from raven_mcs.metrics.system import SystemMetrics, SystemTimer
from raven_mcs.metrics.variance import (
    empirical_update_variance,
    local_n_eff,
    max_local_weight,
    proxy_rank_correlation,
    variance_proxy,
    weight_clip_rate,
)

__all__ = [
    # accuracy
    "rmse_mu",
    "mae_mu",
    "rmse_rho",
    "gap_mis",
    "tail_rmse",
    "group_rmse",
    # debt
    "debt_normalized",
    "prefix_debt_bound_holds",
    # distribution
    "delta_group",
    "delta_pair",
    "delta_c_s",
    "avg_delta_group",
    "avg_delta_ref",
    "effective_group_distribution",
    "raw_arrival_distribution",
    # reachability
    "epsilon_reach",
    "epsilon_reach_block",
    "n_eff_support",
    "min_propensity_quantile",
    # system
    "SystemMetrics",
    "SystemTimer",
    # variance
    "local_n_eff",
    "max_local_weight",
    "variance_proxy",
    "empirical_update_variance",
    "proxy_rank_correlation",
    "weight_clip_rate",
]

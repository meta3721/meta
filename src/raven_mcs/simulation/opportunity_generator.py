"""Controlled opportunity-flow generator (Phase 4 / design §8.2).

Generates per-client, per-window risk sets with opportunity features,
following a controlled opportunity distribution with configurable skew.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class OpportunityConfig:
    """Controlled opportunity generation parameters."""

    num_clients: int = 50
    num_windows: int = 300
    risk_set_mean: float = 7.0
    opportunity_skew: float = 1.0
    drift_period: int | None = None
    drift_magnitude: float = 0.0
    seed: int = 26001


def generate_client_preferences(
    num_clients: int,
    n_strata: int,
    opportunity_skew: float,
    rng: np.random.Generator,
) -> np.ndarray:
    """Generate per-client log-preference vectors for opportunity strata.

    Returns (num_clients, n_strata) array of log-preferences.
    opportunity_skew=0 → uniform preferences (balanced).
    """
    # Base spatial preferences (Dirichlet-like)
    base = rng.dirichlet(np.ones(n_strata), size=num_clients)  # type: ignore[arg-type]
    if opportunity_skew <= 0:
        return np.log(base + 1e-12)
    # Skewed: amplify variation
    skewed = base ** (1.0 / (opportunity_skew + 1e-8))
    skewed = skewed / skewed.sum(axis=1, keepdims=True)
    return np.log(skewed + 1e-12)


def generate_opportunity_stream(
    atomic_units: pd.DataFrame,
    config: OpportunityConfig,
) -> pd.DataFrame:
    """Generate per-window, per-client risk sets from atomic_units.

    Returns a DataFrame with columns: window_id, client_id, risk_set_unit_ids,
    opportunity_stratum, opportunity_features.
    """
    rng = np.random.default_rng(config.seed)

    # Determine strata from atomic_units
    if "opportunity_stratum" in atomic_units.columns:
        strata = sorted(atomic_units["opportunity_stratum"].unique())
    else:
        strata = [0]
    n_strata = len(strata)

    # Generate client preferences
    log_prefs = generate_client_preferences(
        config.num_clients, n_strata, config.opportunity_skew, rng
    )

    rows: list[dict[str, Any]] = []
    drift_shift = np.zeros(n_strata)

    for window_id in range(config.num_windows):
        # Apply drift if configured
        if config.drift_period and config.drift_period > 0:
            if window_id > 0 and window_id % config.drift_period == 0:
                drift_shift = rng.normal(0, config.drift_magnitude, n_strata)

        for client_index in range(config.num_clients):
            client_id = f"c{client_index:04d}"
            # Sample risk set size
            risk_size = max(1, int(rng.poisson(config.risk_set_mean)))

            # Sample units from atomic_units (balanced across strata when skew=0)
            probs = np.exp(log_prefs[client_index] + drift_shift)
            probs = probs / probs.sum()

            sampled_strata = rng.choice(n_strata, size=min(risk_size, n_strata), p=probs, replace=False)

            risk_units: list[str] = []
            for s in sampled_strata:
                stratum_units = atomic_units[
                    atomic_units.get("opportunity_stratum", 0) == s
                ]
                if len(stratum_units) > 0:
                    chosen = rng.choice(stratum_units.index, size=1)[0]
                    risk_units.append(str(chosen))

            rows.append(
                {
                    "window_id": int(window_id),
                    "client_id": client_id,
                    "risk_set_unit_ids": risk_units,
                    "opportunity_stratum": int(sampled_strata[0]) if len(sampled_strata) > 0 else 0,
                    "opportunity_features": {
                        "stratum_id": int(sampled_strata[0]) if len(sampled_strata) > 0 else 0,
                        "risk_size": risk_size,
                        "client_bias": float(client_index % 10) / 10.0,
                        "log_preference": float(log_prefs[client_index, 0]),
                    },
                }
            )

    return pd.DataFrame(rows)

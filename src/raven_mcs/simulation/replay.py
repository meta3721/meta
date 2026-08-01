"""RAVEN-SimOracle Monte Carlo replay (Phase 4 / design §8.4).

Replays the same pre-outcome state M_MC times to estimate
oracle q values with controlled Monte Carlo error.
"""

from __future__ import annotations

import numpy as np

from raven_mcs.simulation.usable_generator import UsableConfig, generate_usable_events


def mc_replay_q(
    num_clients: int,
    num_windows: int,
    config: UsableConfig,
    m_mc: int = 2000,
    base_seed: int = 26001,
) -> tuple[np.ndarray, np.ndarray]:
    """Monte Carlo replay to estimate oracle q with standard errors.

    Runs m_mc independent replays of the usable-event generation
    with the same pre-outcome state (same config, different MC seeds).

    Args:
        num_clients: number of clients
        num_windows: number of windows
        config: usable generation configuration
        m_mc: number of Monte Carlo replays (default 2000)
        base_seed: base seed for MC stream

    Returns:
        q_mc_mean: (windows, clients) mean estimated q
        q_mc_se: (windows, clients) standard error of q estimate
    """
    rng = np.random.default_rng(base_seed)
    mc_seeds = rng.integers(0, 2**31 - 1, size=m_mc)

    # Accumulate q estimates across MC replays
    q_sum = np.zeros((num_windows, num_clients))
    q_sq_sum = np.zeros((num_windows, num_clients))

    for mc_idx in range(m_mc):
        mc_cfg = UsableConfig(
            mean_usable_rate=config.mean_usable_rate,
            mean_compute_duration=config.mean_compute_duration,
            mean_network_duration=config.mean_network_duration,
            window_duration=config.window_duration,
            max_staleness=config.max_staleness,
            seed=int(mc_seeds[mc_idx]),
        )
        _, _, _, _, _, U_mc = generate_usable_events(
            num_clients, num_windows, mc_cfg
        )
        q_sum += U_mc.astype(np.float64)
        q_sq_sum += (U_mc.astype(np.float64)) ** 2

    q_mean = q_sum / m_mc
    # Standard error = sqrt(variance / M_MC)
    variance = (q_sq_sum / m_mc) - q_mean**2
    variance = np.maximum(variance, 0.0)  # numerical safety
    q_se = np.sqrt(variance / m_mc)

    return q_mean, q_se


def check_mc_accuracy(
    q_mc_mean: np.ndarray,
    q_oracle: np.ndarray,
    tolerance: float = 0.01,
) -> dict[str, float]:
    """Verify MC accuracy against oracle q values.

    Returns dict with max_abs_error and rmse.
    """
    diff = q_mc_mean - q_oracle
    return {
        "max_abs_error": float(np.max(np.abs(diff))),
        "rmse": float(np.sqrt(np.mean(diff**2))),
        "within_tolerance": bool(np.max(np.abs(diff)) < tolerance),
    }

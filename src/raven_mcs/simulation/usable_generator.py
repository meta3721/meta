"""Second-stage usable-update generator (Phase 4 / design §8.4).

Models compute success, network success, delays, and deadlines
to produce the final usable indicator U_{k,r}.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class UsableConfig:
    """Usable-update generation parameters."""

    mean_usable_rate: float = 0.60
    mean_compute_duration: float = 0.5
    mean_network_duration: float = 0.3
    window_duration: float = 1.0
    max_staleness: int = 5
    seed: int = 26001


def generate_device_profiles(
    num_clients: int,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Generate device capability profiles.

    Returns:
        compute_success_rate: (K,) per-client P(compute_success)
        compute_duration_mean: (K,) per-client mean LogNormal compute time
        network_success_rate: (K,) per-client P(network_success)
    """
    # Three device tiers: low (30%), medium (50%), high (20%)
    tiers = rng.choice([0, 1, 2], size=num_clients, p=[0.3, 0.5, 0.2])
    compute_success_rate = np.where(tiers == 0, 0.7, np.where(tiers == 1, 0.9, 0.98))
    compute_duration_mean = np.where(tiers == 0, 0.8, np.where(tiers == 1, 0.5, 0.2))
    network_success_rate = np.where(tiers == 0, 0.8, np.where(tiers == 1, 0.95, 0.99))
    return compute_success_rate, compute_duration_mean, network_success_rate


def generate_usable_events(
    num_clients: int,
    num_windows: int,
    config: UsableConfig,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Generate compute/network/arrival outcomes for the full trace.

    Returns:
        compute_success: (windows, clients) bool
        compute_duration: (windows, clients) float
        network_success: (windows, clients) bool
        network_duration: (windows, clients) float
        arrival_time: (windows, clients) float
        U: (windows, clients) bool — final usable indicator
    """
    rng = np.random.default_rng(config.seed)

    csr, cmd, nsr = generate_device_profiles(num_clients, rng)

    compute_success = np.zeros((num_windows, num_clients), dtype=bool)
    compute_duration = np.zeros((num_windows, num_clients))
    network_success = np.zeros((num_windows, num_clients), dtype=bool)
    network_duration = np.zeros((num_windows, num_clients))
    U = np.zeros((num_windows, num_clients), dtype=bool)

    for w in range(num_windows):
        for k in range(num_clients):
            # Registration time (uniform in first 30% of window)
            reg_time = float(w) + rng.uniform(0, 0.3 * config.window_duration)

            # Compute
            cs = rng.random() < csr[k]
            cd = rng.lognormal(np.log(cmd[k]), 0.3) if cs else 0.0
            compute_success[w, k] = cs

            # Network
            ns = rng.random() < nsr[k] if cs else False
            nd = rng.lognormal(np.log(config.mean_network_duration), 0.2) if ns else 0.0
            network_success[w, k] = ns

            # Arrival
            arrival = reg_time + cd + nd
            compute_duration[w, k] = cd
            network_duration[w, k] = nd

            # Staleness (downloaded version)
            downloaded_version = max(0, w - rng.integers(0, config.max_staleness + 1))
            staleness = w - downloaded_version

            # U = compute AND network AND on-time AND not-too-stale
            on_time = arrival < (w + config.window_duration)
            not_too_stale = staleness <= config.max_staleness
            U[w, k] = bool(cs and ns and on_time and not_too_stale)

    return compute_success, compute_duration, network_success, network_duration, np.zeros((num_windows, num_clients)), U


def generate_q_oracle(
    num_clients: int,
    num_windows: int,
    config: UsableConfig,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Generate oracle q values (true usable probabilities) for each (window, client).

    These are the generating probabilities for SimOracle.
    """
    if rng is None:
        rng = np.random.default_rng(config.seed)
    csr, _, nsr = generate_device_profiles(num_clients, rng)
    q_oracle = np.zeros((num_windows, num_clients))
    for w in range(num_windows):
        for k in range(num_clients):
            # True q = P(compute_success) * P(network_success) * P(on_time) * P(not_too_stale)
            p_cs = csr[k]
            p_ns = nsr[k]
            p_ontime = 0.85  # approximate
            p_not_stale = min(1.0, (config.max_staleness + 1) / (config.max_staleness + 2))
            q_oracle[w, k] = float(p_cs * p_ns * p_ontime * p_not_stale)
    return q_oracle

"""Shared per-seed base random streams for E2 distribution validation."""
from __future__ import annotations

import hashlib
from typing import Any

import numpy as np

from raven_mcs.utils.hashing import sha256_json
from raven_mcs.utils.seed import SeedBundle


def _array_digest(name: str, arr: np.ndarray) -> str:
    digest = hashlib.sha256()
    digest.update(name.encode("utf-8"))
    digest.update(np.ascontiguousarray(arr).tobytes())
    return digest.hexdigest()


def build_base_random_streams(
    seed: int,
    *,
    n_windows: int,
    n_clients: int,
    max_risk_set: int,
) -> dict[str, Any]:
    """Pre-draw uniforms reused by all profiles/scenarios for one seed."""
    bundle = SeedBundle.from_master(int(seed))
    opp_rng = np.random.default_rng(bundle.opportunity)
    obs_rng = np.random.default_rng(bundle.observation)
    event_rng = np.random.default_rng(bundle.event)
    # Usable/delay use event and mc_oracle streams (no model/solver streams consumed).
    use_rng = np.random.default_rng(bundle.mc_oracle)
    delay_rng = np.random.default_rng(int(bundle.event) ^ 0x44454C41)

    shape_wu = (int(n_windows), int(n_clients), int(max_risk_set))
    streams = {
        "seed": int(seed),
        "seed_bundle": bundle.as_dict(),
        "base_opportunity_uniforms": opp_rng.random(shape_wu),
        "base_observation_uniforms": obs_rng.random(shape_wu),
        "base_usable_uniforms": use_rng.random((int(n_windows), int(n_clients))),
        "base_delay_uniforms": delay_rng.random((int(n_windows), int(n_clients))),
        "base_client_window_schedule": event_rng.random((int(n_windows), int(n_clients))),
    }
    streams["base_random_stream_hash"] = sha256_json({
        "seed": int(seed),
        "seed_bundle": bundle.as_dict(),
        "opp": _array_digest("opp", streams["base_opportunity_uniforms"]),
        "obs": _array_digest("obs", streams["base_observation_uniforms"]),
        "use": _array_digest("use", streams["base_usable_uniforms"]),
        "delay": _array_digest("delay", streams["base_delay_uniforms"]),
        "sched": _array_digest("sched", streams["base_client_window_schedule"]),
    })
    return streams

"""Deterministic seeding for RAVEN-MCS runs."""

from __future__ import annotations

import os
import random
from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np

SEED_STREAMS = (
    "master",
    "data",
    "opportunity",
    "observation",
    "event",
    "model",
    "solver",
    "bootstrap",
    "mc_oracle",
)


def assert_preconfigured_python_hash_seed(seed: int) -> None:
    """Require the interpreter to have started with the run's hash seed."""
    expected = str(seed)
    if os.environ.get("PYTHONHASHSEED") != expected:
        raise RuntimeError(
            "PYTHONHASHSEED must be set before Python starts; launch this run with "
            f"PYTHONHASHSEED={expected}"
        )


@dataclass(frozen=True)
class SeedBundle:
    """All RNG streams that may affect a run (must enter the manifest)."""

    master: int
    data: int
    opportunity: int
    observation: int
    event: int
    model: int
    solver: int
    bootstrap: int
    mc_oracle: int

    @classmethod
    def from_master(cls, master: int) -> SeedBundle:
        """Derive component seeds from a master seed (stable, documented)."""
        if isinstance(master, bool) or not isinstance(master, int) or master < 0:
            raise ValueError("master seed must be a non-negative integer")
        rng = np.random.default_rng(int(master))
        draws = rng.integers(0, 2**31 - 1, size=8, dtype=np.int64)
        return cls(
            master=int(master),
            data=int(draws[0]),
            opportunity=int(draws[1]),
            observation=int(draws[2]),
            event=int(draws[3]),
            model=int(draws[4]),
            solver=int(draws[5]),
            bootstrap=int(draws[6]),
            mc_oracle=int(draws[7]),
        )

    @classmethod
    def from_config(
        cls,
        master: int,
        configured: Mapping[str, Any] | None,
    ) -> SeedBundle:
        """Resolve explicit overrides against stable master-derived streams."""
        if isinstance(master, bool) or not isinstance(master, int) or master < 0:
            raise ValueError("master seed must be a non-negative integer")
        values = dict(configured or {})
        unknown = sorted(set(values) - set(SEED_STREAMS))
        if unknown:
            raise ValueError(f"Unknown seed streams: {unknown}")
        configured_master = values.get("master")
        if configured_master is not None and configured_master != master:
            raise ValueError(
                f"seeds.master ({configured_master}) must equal seed ({master})"
            )
        derived = cls.from_master(master).as_dict()
        resolved: dict[str, int] = {"master": master}
        for name in SEED_STREAMS[1:]:
            value = values.get(name)
            if value is None:
                resolved[name] = derived[name]
            elif isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"seeds.{name} must be a non-negative integer")
            else:
                resolved[name] = value
        return cls(**resolved)

    def as_dict(self) -> dict[str, int]:
        return {
            "master": self.master,
            "data": self.data,
            "opportunity": self.opportunity,
            "observation": self.observation,
            "event": self.event,
            "model": self.model,
            "solver": self.solver,
            "bootstrap": self.bootstrap,
            "mc_oracle": self.mc_oracle,
        }


def seed_everything(
    seed: int | SeedBundle,
    *,
    require_preconfigured_hash_seed: bool = True,
) -> SeedBundle:
    """
    Seed Python, NumPy, and Torch (if installed) for reproducibility.

    Sets at least: random, numpy, torch CPU/CUDA, deterministic algorithms,
    cuDNN deterministic, PYTHONHASHSEED.
    """
    bundle = seed if isinstance(seed, SeedBundle) else SeedBundle.from_master(seed)
    if require_preconfigured_hash_seed:
        assert_preconfigured_python_hash_seed(bundle.master)
    random.seed(bundle.master)
    np.random.seed(bundle.data % (2**32 - 1))

    try:
        import torch

        torch.manual_seed(bundle.model)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(bundle.model)
        torch.use_deterministic_algorithms(True)
        if hasattr(torch.backends, "cudnn"):
            torch.backends.cudnn.deterministic = True
            torch.backends.cudnn.benchmark = False
    except ImportError:
        pass

    return bundle


def numpy_generator(seed: int) -> np.random.Generator:
    return np.random.default_rng(int(seed))


def capture_rng_state() -> dict[str, Any]:
    """Capture Python/NumPy/Torch RNG states for exact checkpoint resume."""
    state: dict[str, Any] = {
        "python": random.getstate(),
        "numpy": np.random.get_state(),
    }
    try:
        import torch

        state["torch_cpu"] = torch.get_rng_state()
        if torch.cuda.is_available():
            state["torch_cuda"] = torch.cuda.get_rng_state_all()
    except ImportError:
        pass
    return state


def restore_rng_state(state: dict[str, Any]) -> None:
    """Restore states produced by :func:`capture_rng_state`."""
    random.setstate(state["python"])
    np.random.set_state(state["numpy"])
    try:
        import torch

        if "torch_cpu" in state:
            torch.set_rng_state(state["torch_cpu"])
        if "torch_cuda" in state and torch.cuda.is_available():
            torch.cuda.set_rng_state_all(state["torch_cuda"])
    except ImportError:
        if "torch_cpu" in state or "torch_cuda" in state:
            raise RuntimeError("Checkpoint contains Torch RNG state but Torch is unavailable")


def assert_explicit_rng(obj: Any) -> None:
    """Call sites should pass explicit RNG/seed objects."""
    if obj is None:
        raise ValueError("RNG/seed object must be explicit; got None")

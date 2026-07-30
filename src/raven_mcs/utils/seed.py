"""Deterministic seeding for RAVEN-MCS runs."""

from __future__ import annotations

import os
import random
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class SeedBundle:
    """All RNG streams that may affect a run (must enter the manifest)."""

    master: int
    data: int
    event: int
    model: int
    solver: int
    bootstrap: int

    @classmethod
    def from_master(cls, master: int) -> SeedBundle:
        """Derive component seeds from a master seed (stable, documented)."""
        rng = np.random.default_rng(int(master))
        draws = rng.integers(0, 2**31 - 1, size=5, dtype=np.int64)
        return cls(
            master=int(master),
            data=int(draws[0]),
            event=int(draws[1]),
            model=int(draws[2]),
            solver=int(draws[3]),
            bootstrap=int(draws[4]),
        )

    def as_dict(self) -> dict[str, int]:
        return {
            "master": self.master,
            "data": self.data,
            "event": self.event,
            "model": self.model,
            "solver": self.solver,
            "bootstrap": self.bootstrap,
        }


def seed_everything(seed: int) -> SeedBundle:
    """
    Seed Python, NumPy, and Torch (if installed) for reproducibility.

    Sets at least: random, numpy, torch CPU/CUDA, deterministic algorithms,
    cuDNN deterministic, PYTHONHASHSEED.
    """
    bundle = SeedBundle.from_master(int(seed))
    os.environ["PYTHONHASHSEED"] = str(bundle.master)
    random.seed(bundle.master)
    np.random.seed(bundle.master % (2**32 - 1))

    try:
        import torch

        torch.manual_seed(bundle.model)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(bundle.model)
        torch.use_deterministic_algorithms(True, warn_only=True)
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

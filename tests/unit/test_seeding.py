"""Phase-1 tests: seeding."""

from __future__ import annotations

import os
import random
import subprocess
import sys

import numpy as np
import pytest

from raven_mcs.utils.seed import (
    SeedBundle,
    capture_rng_state,
    restore_rng_state,
    seed_everything,
)


def test_seed_bundle_stable_from_master() -> None:
    a = SeedBundle.from_master(26001)
    b = SeedBundle.from_master(26001)
    assert a == b
    assert a.master == 26001


def test_seed_everything_numpy_reproducible() -> None:
    seed_everything(26001, require_preconfigured_hash_seed=False)
    x = np.random.rand(5)
    seed_everything(26001, require_preconfigured_hash_seed=False)
    y = np.random.rand(5)
    assert np.allclose(x, y)


def test_seed_everything_python_random_reproducible() -> None:
    seed_everything(7, require_preconfigured_hash_seed=False)
    a = [random.random() for _ in range(5)]
    seed_everything(7, require_preconfigured_hash_seed=False)
    b = [random.random() for _ in range(5)]
    assert a == b


def test_component_seeds_are_distinct() -> None:
    bundle = SeedBundle.from_master(26001)
    component_seeds = {
        bundle.data,
        bundle.opportunity,
        bundle.observation,
        bundle.event,
        bundle.model,
        bundle.solver,
        bundle.bootstrap,
        bundle.mc_oracle,
    }
    assert len(component_seeds) == 8


def test_capture_restore_rng_state() -> None:
    seed_everything(26001, require_preconfigured_hash_seed=False)
    state = capture_rng_state()
    expected_python = random.random()
    expected_numpy = float(np.random.rand())
    restore_rng_state(state)
    assert random.random() == expected_python
    assert float(np.random.rand()) == expected_numpy


def test_torch_seed_reproducible_when_installed() -> None:
    torch = pytest.importorskip("torch")
    seed_everything(26001, require_preconfigured_hash_seed=False)
    first = torch.rand(4)
    seed_everything(26001, require_preconfigured_hash_seed=False)
    second = torch.rand(4)
    assert torch.equal(first, second)
    assert torch.are_deterministic_algorithms_enabled()


def test_seed_everything_requires_process_hash_seed(monkeypatch) -> None:
    monkeypatch.delenv("PYTHONHASHSEED", raising=False)
    with pytest.raises(RuntimeError, match="before Python starts"):
        seed_everything(26001)


def test_python_hash_is_stable_when_set_before_process_start() -> None:
    env = os.environ.copy()
    env["PYTHONHASHSEED"] = "26001"
    command = [sys.executable, "-c", "print(hash('raven-mcs'))"]
    first = subprocess.check_output(command, env=env, text=True).strip()
    second = subprocess.check_output(command, env=env, text=True).strip()
    assert first == second


def test_seed_bundle_config_coherence() -> None:
    explicit = SeedBundle.from_config(
        26001, {"master": 26001, "data": 123, "event": 456}
    )
    assert explicit.master == 26001
    assert explicit.data == 123
    assert explicit.event == 456
    with pytest.raises(ValueError, match="must equal"):
        SeedBundle.from_config(26001, {"master": 999})

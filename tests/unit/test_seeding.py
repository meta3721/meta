"""Phase-1 tests: seeding."""

from __future__ import annotations

import random

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
    seed_everything(26001)
    x = np.random.rand(5)
    seed_everything(26001)
    y = np.random.rand(5)
    assert np.allclose(x, y)


def test_seed_everything_python_random_reproducible() -> None:
    seed_everything(7)
    a = [random.random() for _ in range(5)]
    seed_everything(7)
    b = [random.random() for _ in range(5)]
    assert a == b


def test_component_seeds_are_distinct() -> None:
    bundle = SeedBundle.from_master(26001)
    component_seeds = {
        bundle.data,
        bundle.event,
        bundle.model,
        bundle.solver,
        bundle.bootstrap,
    }
    assert len(component_seeds) == 5


def test_capture_restore_rng_state() -> None:
    seed_everything(26001)
    state = capture_rng_state()
    expected_python = random.random()
    expected_numpy = float(np.random.rand())
    restore_rng_state(state)
    assert random.random() == expected_python
    assert float(np.random.rand()) == expected_numpy


def test_torch_seed_reproducible_when_installed() -> None:
    torch = pytest.importorskip("torch")
    seed_everything(26001)
    first = torch.rand(4)
    seed_everything(26001)
    second = torch.rand(4)
    assert torch.equal(first, second)

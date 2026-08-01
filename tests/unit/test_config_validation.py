"""Phase-1 tests: config validation."""

from __future__ import annotations

import pytest

from raven_mcs.utils.config import load_base_config, resolve_run_config
from raven_mcs.utils.validation import (
    ConfigValidationError,
    assert_valid_config,
    validate_config,
)


def test_base_config_validates() -> None:
    cfg = load_base_config()
    result = validate_config(cfg)
    assert result.ok, result.errors


def test_lambda_reference_must_be_positive() -> None:
    cfg = load_base_config()
    cfg["aggregation"]["lambda_reference"] = 0.0
    result = validate_config(cfg)
    assert not result.ok
    with pytest.raises(ConfigValidationError):
        assert_valid_config(cfg)


def test_lambda_group_vs_max_lr() -> None:
    cfg = load_base_config()
    cfg["aggregation"]["lambda_group"] = 0.1
    cfg["aggregation"]["max_server_learning_rate"] = 1.0
    result = validate_config(cfg)
    assert any("lambda_group" in e for e in result.errors)


def test_resolve_run_config_default() -> None:
    cfg = resolve_run_config(seed=26001)
    assert cfg["seed"] == 26001
    assert cfg["experiment"] == "E0_unit"


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("max_workers",), 0, "max_workers"),
        (("device",), "gpu", "device"),
        (("solver", "tolerance"), 0.0, "solver.tolerance"),
        (("solver", "tolerance"), "invalid", "solver.tolerance"),
        (("solver", "tolerance"), "1e-6", "solver.tolerance"),
        (("solver", "tolerance"), float("nan"), "must be finite"),
        (("solver", "tolerance"), float("inf"), "must be finite"),
        (("correction", "p_min"), 1.1, "correction.p_min"),
        (
            ("correction", "opportunity_forgetting"),
            0.0,
            "opportunity_forgetting",
        ),
        (("aggregation", "alpha_max"), 1.1, "alpha_max"),
        (("window", "num_windows"), 0, "window.num_windows"),
    ],
)
def test_extended_config_validation(
    path: tuple[str, ...], value: object, message: str
) -> None:
    cfg = load_base_config()
    target = cfg
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    result = validate_config(cfg)
    assert any(message in error for error in result.errors)


def test_unknown_config_keys_are_rejected() -> None:
    cfg = load_base_config()
    cfg["typo_parameter"] = 1
    cfg["solver"]["tolernace"] = 1e-6
    result = validate_config(cfg)
    assert "unknown key: typo_parameter" in result.errors
    assert "unknown key: solver.tolernace" in result.errors


def test_resolved_config_contains_all_concrete_seed_streams() -> None:
    cfg = resolve_run_config(seed=26001)
    assert cfg["seeds"]["master"] == cfg["seed"]
    assert all(isinstance(value, int) for value in cfg["seeds"].values())
    assert len(set(cfg["seeds"].values())) == len(cfg["seeds"])


def test_named_config_slice_rejects_unknown_keys() -> None:
    with pytest.raises(ConfigValidationError, match="unknown key"):
        resolve_run_config(overrides={"_dataset_cfg": {"typo": 1}})

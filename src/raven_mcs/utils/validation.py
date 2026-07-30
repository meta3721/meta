"""Config validation for RAVEN-MCS (Phase 1 skeleton)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


class ConfigValidationError(ValueError):
    """Raised when a config violates the experiment constitution."""


REQUIRED_TOP_LEVEL = (
    "experiment",
    "dataset",
    "method",
    "scenario",
    "seed",
    "device",
    "output_dir",
    "resume",
    "dry_run",
    "max_workers",
    "fail_fast",
    "clients",
    "window",
    "correction",
    "aggregation",
    "solver",
    "seeds",
)


@dataclass
class ValidatedConfig:
    raw: dict[str, Any]
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _require_keys(
    d: Mapping[str, Any], keys: tuple[str, ...], prefix: str, errors: list[str]
) -> None:
    for key in keys:
        if key not in d:
            errors.append(f"missing key: {prefix}{key}")


def _as_float(value: Any, label: str, errors: list[str]) -> float | None:
    if isinstance(value, bool):
        errors.append(f"{label} must be numeric")
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        errors.append(f"{label} must be numeric")
        return None


def _as_int(value: Any, label: str, errors: list[str]) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        errors.append(f"{label} must be an integer")
        return None
    return value


def validate_config(config: Mapping[str, Any]) -> ValidatedConfig:
    """
    Validate constitution-critical config constraints.

    Phase 1 checks structure + P2 lambda rules; later phases extend.
    """
    raw = dict(config)
    errors: list[str] = []
    _require_keys(raw, REQUIRED_TOP_LEVEL, "", errors)

    for key in ("experiment", "dataset", "method", "scenario", "device", "output_dir"):
        value = raw.get(key)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            errors.append(f"{key} must be a non-empty string")

    device = raw.get("device")
    if isinstance(device, str):
        valid_device = device == "cpu" or device == "cuda" or (
            device.startswith("cuda:") and device[5:].isdigit()
        )
        if not valid_device:
            errors.append("device must be cpu, cuda, or cuda:N")

    for key in ("resume", "dry_run", "fail_fast"):
        if key in raw and not isinstance(raw[key], bool):
            errors.append(f"{key} must be boolean")
    if "max_workers" in raw:
        if not isinstance(raw["max_workers"], int) or isinstance(raw["max_workers"], bool):
            errors.append("max_workers must be an integer")
        elif raw["max_workers"] < 1:
            errors.append("max_workers must be >= 1")

    agg = raw.get("aggregation")
    if isinstance(agg, Mapping):
        _require_keys(
            agg,
            (
                "lambda_group",
                "lambda_reference",
                "lambda_variance",
                "lambda_staleness",
                "min_effective_clients",
                "alpha_max",
                "max_server_learning_rate",
            ),
            "aggregation.",
            errors,
        )
        lam_beta = agg.get("lambda_reference")
        lam_g = agg.get("lambda_group")
        max_lr = agg.get("max_server_learning_rate", 1.0)
        lam_beta_num = (
            _as_float(lam_beta, "aggregation.lambda_reference", errors)
            if lam_beta is not None
            else None
        )
        lam_g_num = (
            _as_float(lam_g, "aggregation.lambda_group", errors)
            if lam_g is not None
            else None
        )
        max_lr_num = _as_float(
            max_lr, "aggregation.max_server_learning_rate", errors
        )
        if lam_beta_num is not None and lam_beta_num <= 0:
            errors.append("aggregation.lambda_reference must be > 0 (P2 uniqueness)")
        if (
            lam_g_num is not None
            and max_lr_num is not None
            and lam_g_num < max_lr_num
        ):
            errors.append(
                "aggregation.lambda_group must be >= aggregation.max_server_learning_rate"
            )
        for key in ("lambda_group", "lambda_variance", "lambda_staleness"):
            number = (
                _as_float(agg[key], f"aggregation.{key}", errors)
                if key in agg
                else None
            )
            if number is not None and number < 0:
                errors.append(f"aggregation.{key} must be >= 0")
        alpha_max = (
            _as_float(agg["alpha_max"], "aggregation.alpha_max", errors)
            if "alpha_max" in agg
            else None
        )
        if alpha_max is not None and not 0 < alpha_max <= 1:
            errors.append("aggregation.alpha_max must be in (0, 1]")
        min_clients = (
            _as_int(
                agg["min_effective_clients"],
                "aggregation.min_effective_clients",
                errors,
            )
            if "min_effective_clients" in agg
            else None
        )
        if min_clients is not None and min_clients < 1:
            errors.append("aggregation.min_effective_clients must be >= 1")
    else:
        errors.append("aggregation must be a mapping")

    corr = raw.get("correction")
    if isinstance(corr, Mapping):
        for key in (
            "p_min",
            "q_min",
            "a_max",
            "d_max",
            "opportunity_forgetting",
            "pi_min",
        ):
            if key not in corr:
                errors.append(f"missing key: correction.{key}")
            else:
                number = _as_float(corr[key], f"correction.{key}", errors)
                if number is not None and number <= 0:
                    errors.append(f"correction.{key} must be > 0")
        for key in ("p_min", "q_min"):
            number = (
                _as_float(corr[key], f"correction.{key}", [])
                if key in corr
                else None
            )
            if number is not None and number > 1:
                errors.append(f"correction.{key} must be <= 1")
        forgetting = (
            _as_float(
                corr["opportunity_forgetting"],
                "correction.opportunity_forgetting",
                [],
            )
            if "opportunity_forgetting" in corr
            else None
        )
        if forgetting is not None and not 0 < forgetting <= 1:
            errors.append("correction.opportunity_forgetting must be in (0, 1]")
        pi_min = (
            _as_float(corr["pi_min"], "correction.pi_min", [])
            if "pi_min" in corr
            else None
        )
        if pi_min is not None and pi_min <= 0:
            errors.append("correction.pi_min must be > 0")
    else:
        errors.append("correction must be a mapping")

    solver = raw.get("solver")
    if isinstance(solver, Mapping):
        if "backend" not in solver:
            errors.append("missing key: solver.backend")
        elif not isinstance(solver["backend"], str) or not solver["backend"].strip():
            errors.append("solver.backend must be a non-empty string")
        if "tolerance" not in solver:
            errors.append("missing key: solver.tolerance")
        else:
            tolerance = _as_float(solver["tolerance"], "solver.tolerance", errors)
            if tolerance is not None and tolerance <= 0:
                errors.append("solver.tolerance must be > 0")
    else:
        errors.append("solver must be a mapping")

    seed = raw.get("seed")
    if seed is not None:
        if not isinstance(seed, int) or isinstance(seed, bool):
            errors.append("seed must be an integer")
        elif seed < 0:
            errors.append("seed must be non-negative")

    clients = raw.get("clients")
    if isinstance(clients, Mapping):
        for key in ("K", "local_steps", "risk_set_mean"):
            if key not in clients:
                errors.append(f"missing key: clients.{key}")
            else:
                number = _as_int(clients[key], f"clients.{key}", errors)
                if number is not None and number < 1:
                    errors.append(f"clients.{key} must be >= 1")
    else:
        errors.append("clients must be a mapping")

    window = raw.get("window")
    if isinstance(window, Mapping):
        for key in ("num_windows", "duration", "max_staleness"):
            if key not in window:
                errors.append(f"missing key: window.{key}")
        num_windows = (
            _as_int(window["num_windows"], "window.num_windows", errors)
            if "num_windows" in window
            else None
        )
        if num_windows is not None and num_windows < 1:
            errors.append("window.num_windows must be >= 1")
        duration = (
            _as_float(window["duration"], "window.duration", errors)
            if "duration" in window
            else None
        )
        if duration is not None and duration <= 0:
            errors.append("window.duration must be > 0")
        max_staleness = (
            _as_int(window["max_staleness"], "window.max_staleness", errors)
            if "max_staleness" in window
            else None
        )
        if max_staleness is not None and max_staleness < 0:
            errors.append("window.max_staleness must be >= 0")
    else:
        errors.append("window must be a mapping")

    seeds = raw.get("seeds")
    required_seeds = ("master", "data", "event", "model", "solver", "bootstrap")
    if isinstance(seeds, Mapping):
        _require_keys(seeds, required_seeds, "seeds.", errors)
        for key in required_seeds:
            value = seeds.get(key)
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value < 0
            ):
                errors.append(f"seeds.{key} must be null or a non-negative integer")
    else:
        errors.append("seeds must be a mapping")

    return ValidatedConfig(raw=raw, errors=errors)


def assert_valid_config(config: Mapping[str, Any]) -> dict[str, Any]:
    result = validate_config(config)
    if not result.ok:
        raise ConfigValidationError("; ".join(result.errors))
    return result.raw

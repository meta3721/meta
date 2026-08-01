"""Config loading and merging for RAVEN-MCS."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from raven_mcs.utils.seed import SeedBundle
from raven_mcs.utils.serialization import load_yaml
from raven_mcs.utils.validation import assert_valid_config


def repo_root_from_here() -> Path:
    """src/raven_mcs/utils/config.py -> repo root."""
    return Path(__file__).resolve().parents[3]


def load_base_config(path: Path | None = None) -> dict[str, Any]:
    root = repo_root_from_here()
    cfg_path = Path(path) if path is not None else root / "configs" / "config.yaml"
    return load_yaml(cfg_path)


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        if key in out and isinstance(out[key], dict) and isinstance(value, dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_named_yaml(kind: str, name: str, *, root: Path | None = None) -> dict[str, Any]:
    root = root or repo_root_from_here()
    path = root / "configs" / kind / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Missing config: {path}")
    return load_yaml(path)


def resolve_run_config(
    *,
    experiment: str | None = None,
    dataset: str | None = None,
    method: str | None = None,
    scenario: str | None = None,
    seed: int | None = None,
    device: str | None = None,
    overrides: dict[str, Any] | None = None,
    base_path: Path | None = None,
    validate: bool = True,
) -> dict[str, Any]:
    """Merge root config with named YAML slices and CLI overrides."""
    root = repo_root_from_here()
    cfg = load_base_config(base_path)

    exp_name = experiment or str(cfg.get("experiment"))
    ds_name = dataset or str(cfg.get("dataset"))
    method_name = method or str(cfg.get("method"))
    scenario_name = scenario or str(cfg.get("scenario"))

    for kind, name in (
        ("experiment", exp_name),
        ("dataset", ds_name),
        ("method", method_name),
        ("scenario", scenario_name),
    ):
        slice_path = root / "configs" / kind / f"{name}.yaml"
        if slice_path.exists():
            cfg = deep_merge(cfg, {kind: name, f"_{kind}_cfg": load_yaml(slice_path)})

    cfg["experiment"] = exp_name
    cfg["dataset"] = ds_name
    cfg["method"] = method_name
    cfg["scenario"] = scenario_name
    if seed is not None:
        cfg["seed"] = int(seed)
    if device is not None:
        cfg["device"] = device
    if overrides:
        cfg = deep_merge(cfg, overrides)

    seed_bundle = SeedBundle.from_config(cfg["seed"], cfg.get("seeds"))
    cfg["seeds"] = seed_bundle.as_dict()
    if validate:
        assert_valid_config(cfg)
    return cfg

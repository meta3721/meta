"""E2 method identity resolution."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from raven_mcs.experiments.e1_entry import E1_METHODS
from raven_mcs.utils.hashing import sha256_file

ROOT = Path(__file__).resolve().parents[3]

EXECUTABLE_METHODS = {
    "fedavg_window",
    "fedasync_window",
    "flamf_timealign_adapted",
    "local_hajek",
    "twostage_hajek",
}


def load_method_alias_registry(root: Path | None = None) -> dict[str, Any]:
    root = Path(root or ROOT)
    path = root / "configs/e2_numeric/method_alias_registry.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def resolve_method(name: str, root: Path | None = None) -> str:
    root = Path(root or ROOT)
    registry = load_method_alias_registry(root)
    aliases = registry.get("aliases", {})
    if name in aliases:
        executable = str(aliases[name]["executable_id"])
    else:
        executable = str(name)
    if executable not in EXECUTABLE_METHODS:
        raise KeyError(f"unknown executable method: {executable}")
    if executable in {"fedavg_window", "fedasync_window", "flamf_timealign_adapted"}:
        if executable not in E1_METHODS:
            raise RuntimeError(f"strict method missing from E1_METHODS: {executable}")
    return executable


def method_implementation_identity(
    name: str, root: Path | None = None,
) -> dict[str, Any]:
    root = Path(root or ROOT)
    executable = resolve_method(name, root)
    module_path = root / "src/raven_mcs/aggregation/methods.py"
    config_path = root / f"configs/method/{executable}.yaml"
    if not config_path.is_file() and executable == "flamf_timealign_adapted":
        # Fall back to timealign config if present under either name.
        alt = root / "configs/method/timealign_agg.yaml"
        config_path = alt if alt.is_file() else config_path
    return {
        "requested": name,
        "executable_id": executable,
        "implementation_module": "raven_mcs.aggregation.methods",
        "source_blob_hash": sha256_file(module_path) if module_path.is_file() else None,
        "config_path": config_path.relative_to(root).as_posix() if config_path.is_file() else None,
        "config_hash": sha256_file(config_path) if config_path.is_file() else None,
        "in_e1_methods": executable in E1_METHODS,
    }

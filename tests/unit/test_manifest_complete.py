"""Phase-1 tests: manifest completeness and resume hash guard."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from raven_mcs.training.checkpoints import (
    load_checkpoint_for_resume,
    save_window_checkpoint,
)
from raven_mcs.utils.config import resolve_run_config
from raven_mcs.utils.hashing import config_hash
from raven_mcs.utils.manifest import (
    REQUIRED_MANIFEST_FIELDS,
    assert_resume_config_hash,
    build_manifest,
    finalize_manifest,
    write_manifest,
    write_resolved_config,
)
from raven_mcs.utils.paths import ensure_run_layout, make_run_id
from raven_mcs.utils.seed import SeedBundle, seed_everything

DATA_HASH = "a" * 64
TRACE_HASH = "b" * 64


def test_manifest_required_fields_present(tmp_path: Path) -> None:
    cfg = resolve_run_config(seed=26001)
    bundle = seed_everything(26001)
    run_id = make_run_id(
        experiment=str(cfg["experiment"]),
        dataset=str(cfg["dataset"]),
        method=str(cfg["method"]),
        scenario=str(cfg["scenario"]),
        seed=int(cfg["seed"]),
    )
    run_dir = ensure_run_layout(tmp_path / run_id)
    man = build_manifest(
        run_id=run_id,
        config=cfg,
        seed_bundle=bundle,
        data_hash=DATA_HASH,
        event_trace_hash=TRACE_HASH,
    )
    write_manifest(man, run_dir)
    write_resolved_config(cfg, run_dir)
    data = man.to_dict()
    for key in REQUIRED_MANIFEST_FIELDS:
        assert key in data
    assert man.validate_complete() == []
    assert len(man.run_hash) == 64
    assert (run_dir / "manifest.json").exists()
    assert (run_dir / "resolved_config.yaml").exists()


def test_resume_config_hash(tmp_path: Path) -> None:
    cfg = resolve_run_config(seed=26001)
    bundle = seed_everything(26001)
    run_id = "test_run"
    run_dir = ensure_run_layout(tmp_path / run_id)
    man = build_manifest(
        run_id=run_id,
        config=cfg,
        seed_bundle=bundle,
        data_hash=DATA_HASH,
        event_trace_hash=TRACE_HASH,
    )
    write_manifest(man, run_dir)
    save_window_checkpoint(
        run_dir,
        window_r=0,
        state={"theta": np.asarray([0.0, 1.0]), "nested": {"step": 4}},
        config=cfg,
    )

    payload = load_checkpoint_for_resume(run_dir, cfg)
    assert payload is not None
    assert payload["window_r"] == 0
    assert np.array_equal(payload["state"]["theta"], np.asarray([0.0, 1.0]))
    assert payload["state"]["nested"]["step"] == 4

    bad = dict(cfg)
    bad["seed"] = 99999
    assert config_hash(bad) != config_hash(cfg)
    with pytest.raises(RuntimeError, match="config hash mismatch"):
        assert_resume_config_hash(run_dir, bad)
    with pytest.raises(RuntimeError, match="config hash mismatch"):
        load_checkpoint_for_resume(run_dir, bad)


def test_manifest_finalize_requires_failure_reason(tmp_path: Path) -> None:
    cfg = resolve_run_config(seed=26001)
    run_dir = ensure_run_layout(tmp_path / "finalize")
    man = build_manifest(
        run_id="finalize",
        config=cfg,
        seed_bundle=seed_everything(26001),
        data_hash=DATA_HASH,
        event_trace_hash=TRACE_HASH,
    )
    write_manifest(man, run_dir)

    with pytest.raises(ValueError, match="failure_reason"):
        finalize_manifest(run_dir, hard_gate_status="FAIL")
    final = finalize_manifest(
        run_dir,
        hard_gate_status="FAIL",
        failure_reason="synthetic failure",
    )
    assert final.end_time is not None
    assert final.validate(final=True) == []


def test_auditable_manifest_can_require_git(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="Git is required"):
        build_manifest(
            run_id="requires-git",
            config=resolve_run_config(),
            seed_bundle=SeedBundle.from_master(26001),
            data_hash=DATA_HASH,
            event_trace_hash=TRACE_HASH,
            repo_root=tmp_path,
            require_git=True,
        )

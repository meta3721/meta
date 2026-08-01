#!/usr/bin/env python3
"""Exercise the Phase 1 run/manifest/checkpoint lifecycle without training."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from raven_mcs.training.checkpoints import (
    load_checkpoint_for_resume,
    save_window_checkpoint,
)
from raven_mcs.utils.cli import add_common_run_flags
from raven_mcs.utils.config import resolve_run_config
from raven_mcs.utils.hashing import sha256_json
from raven_mcs.utils.run import RunContext, finalize_run, initialize_run
from raven_mcs.utils.seed import SeedBundle, seed_everything
from raven_mcs.utils.serialization import dump_json


def _relaunch_with_hash_seed(seed: int) -> int | None:
    expected = str(seed)
    if os.environ.get("PYTHONHASHSEED") == expected:
        return None
    env = os.environ.copy()
    env["PYTHONHASHSEED"] = expected
    completed = subprocess.run([sys.executable, *sys.argv], env=env, check=False)
    return completed.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--resume-from",
        type=Path,
        default=None,
        help="Explicit existing run directory used with --resume.",
    )
    add_common_run_flags(parser)
    parser.set_defaults(output_dir=Path("outputs/runs"))
    args = parser.parse_args(argv)
    if args.max_workers != 1:
        parser.error("Lifecycle smoke is one run; --max-workers must be 1")
    seed = 26001 if args.seed is None else args.seed
    if not args.dry_run:
        child_code = _relaunch_with_hash_seed(seed)
        if child_code is not None:
            return child_code

    config = resolve_run_config(
        experiment="phase1_lifecycle_smoke",
        dataset="synthetic",
        method="infrastructure_only",
        scenario="none",
        seed=seed,
        device=args.device,
        overrides={
            "output_dir": str(args.output_dir),
            "resume": args.resume,
            "dry_run": args.dry_run,
            "max_workers": args.max_workers,
            "fail_fast": args.fail_fast,
        },
    )
    bundle = SeedBundle.from_config(config["seed"], config["seeds"])
    data_hash = sha256_json({"fixture": "phase1-lifecycle-data-v1"})
    trace_hash = sha256_json({"fixture": "phase1-lifecycle-trace-v1"})
    context: RunContext | None = None
    try:
        context = initialize_run(
            config=config,
            seed_bundle=bundle,
            data_hash=data_hash,
            event_trace_hash=trace_hash,
            output_root=args.output_dir,
            resume=args.resume,
            resume_from=args.resume_from,
            dry_run=args.dry_run,
            require_git=True,
            repo_root=_ROOT,
        )
        if context.dry_run:
            print(f"dry_run=True run_id={context.run_id}")
            return 0

        seed_everything(bundle)
        if context.resumed:
            checkpoint = load_checkpoint_for_resume(context.path, config)
            if checkpoint is None:
                raise RuntimeError("Resume requested but no checkpoint exists")
        else:
            save_window_checkpoint(
                context.path,
                window_r=0,
                state={"smoke_value": 1, "seed_streams": bundle.as_dict()},
                config=config,
            )
            checkpoint = load_checkpoint_for_resume(context.path, config)
        if checkpoint is None or checkpoint["state"].get("smoke_value") != 1:
            raise RuntimeError("Checkpoint round-trip failed")

        dump_json(
            {
                "run_id": context.run_id,
                "smoke_only": True,
                "checkpoint_round_trip": True,
            },
            context.path / "metrics_run.json",
        )
        finalize_run(context, hard_gate_status="N/A")
        print(f"run_id={context.run_id}")
        print(f"run_dir={context.path}")
        print("lifecycle_smoke=PASS")
        return 0
    except Exception as exc:
        if context is not None and not context.dry_run:
            try:
                finalize_run(
                    context,
                    hard_gate_status="FAIL",
                    failure_reason=f"{type(exc).__name__}: {exc}",
                )
            except Exception:
                pass
        raise


if __name__ == "__main__":
    raise SystemExit(main())

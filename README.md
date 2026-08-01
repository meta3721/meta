# RAVEN-MCS V2.3

Workspace: `D:\Cursor\raven.mcs`

Target-Risk-Calibrated Asynchronous Federated Data Completion under Two-Stage Non-Random Selection.

## Official environment

- **Python 3.11** (constitution). Prefer the project `.venv` (already 3.11.8 on this machine).

```bash
# Activate project venv (Windows)
.\.venv\Scripts\Activate.ps1

# Exact locked environment, then editable package without dependency drift
python -m pip install -r requirements-lock.txt
python -m pip install --no-deps -e .

# Or from conda
conda env create -f environment.yml
conda activate raven-mcs
```

## Verify

```bash
python scripts/verify_run.py --check-environment
python scripts/verify_run.py --check-repository
pytest -q
```

Before any paper-facing run, Git must be installed and the repository must have
a commit:

```bash
python scripts/verify_run.py --check-repository --require-git
```

The run initializer uses strict Git auditing by default, refuses output
overwrites, and requires real 64-character data/EventTrace SHA-256 values.
Scientific runs also require `PYTHONHASHSEED` to be present before Python
starts; the lifecycle smoke automatically relaunches itself with the requested
seed.

```bash
# Reproducible Phase 0 tree/scans (resumes the frozen report if it exists)
python scripts/audit_phase0.py --resume --max-workers 4

# Phase 1 infrastructure only; no model training or main experiment
python scripts/smoke_run_lifecycle.py --dry-run --seed 26001
```

## Phase 2 data framework / G0

```bash
# Official raw download (provenance + checksum)
python scripts/download_data.py --dataset sensorscope

# Prepare / freeze / audit a paper dataset
python scripts/prepare_data.py --dataset sensorscope --freeze --seed 26001
python scripts/audit_data.py --dataset sensorscope
python scripts/check_g0_data.py --data-root data

# Synthetic fixture remains available for infrastructure smoke only
python scripts/prepare_data.py --dataset synthetic --freeze --seed 26001
```

See `docs/DATA_DICTIONARY.md`. Frozen data does not authorize test-set
evaluation; the experiment-config/test-entry gate (ISSUE-010) is still required.

## Hard gates

```bash
python scripts/check_g0_data.py --data-root data
python scripts/check_e0.py
python scripts/check_hard_gates.py   # G1–G5
```

## Status

See `STATUS.md`. Do not run E1 / 20-seed main experiments until G6–G7 pass and ISSUE-012 is resolved.

## Long-task CLI flags

`--dry-run` `--resume` `--max-workers` `--fail-fast` `--device` `--seed` `--output-dir`

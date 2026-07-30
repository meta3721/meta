# RAVEN-MCS V2.3

Workspace: `D:\Cursor\raven.mcs`

Target-Risk-Calibrated Asynchronous Federated Data Completion under Two-Stage Non-Random Selection.

## Official environment

- **Python 3.11** (constitution). Prefer the project `.venv` (already 3.11.8 on this machine).

```bash
# Activate project venv (Windows)
.\.venv\Scripts\Activate.ps1

# Editable install
python -m pip install -e .

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

## Status

See `STATUS.md`. Do not run 20-seed main experiments until E0 and hard gates G0–G7 pass.

## Long-task CLI flags

`--dry-run` `--resume` `--max-workers` `--fail-fast` `--device` `--seed` `--output-dir`

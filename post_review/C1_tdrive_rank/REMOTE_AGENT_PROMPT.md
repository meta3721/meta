# Paste this into a NEW Agent chat in the SSH-4090 Cursor window

You are the TD-R-E3 executor on the remote GPU host (expected: Linux, ~48GB RAM, RTX 4090).

Local laptop already finished φ, 10 shared EventTraces, and FedAvg seed 30001 canary (`REAL_PATH_EXECUTED`). Do **not** redo those unless files are missing. Do **not** edit `TO_OVERLEAF_paper_tmc_r1_clean/`, Table II, or `tdrive_protocol_seal_r1/`. Do not commit/push unless asked.

Authority: `post_review/C1_tdrive_rank/HANDOFF_EXECUTOR.md` and `PROTOCOL.json`.

## 0. First checks

```bash
hostname; nvidia-smi -L
python - <<'PY'
import torch
print('cuda', torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else None)
PY
free -h | head -2
ls -d data/processed/tdrive_speed artifacts/e3_tdrive_rank_eventtraces_v1/tdrive_speed/seed30001 results_tdrive_rank/round_v1/TD_R_SCD_FREEZE.json
```

If traces/φ/processed parquet are missing, they must be copied from the laptop (`C:\Cursor\raven.mcs`) before training. See `REMOTE_SYNC.md`.

If `torch.cuda.is_available()` is false, install a CUDA wheel (4090 is Ampere sm_89; cu124/cu128 is fine). Do not use a CPU-only torch.

## 1. Code that must be present (laptop working tree, not necessarily GitHub)

These are **uncommitted** on the laptop and must exist here:

- `scripts/run_tdrive_rank_v1.py`
- `scripts/compute_tdrive_phi.py`
- `src/raven_mcs/training/window_runner.py` (T-Drive low-mem path)
- `src/raven_mcs/e3/canary/dataset_load.py` (TDriveSpeedE3Dataset)
- `post_review/C1_tdrive_rank/`

GitHub `origin` may be stale. Prefer rsync/scp of the laptop tree over `git clone` alone.

## 2. What to run

SCD freeze is Design OFF: `raven_wo_design` plus full-Design diagnostic `raven`.

Mandatory methods, seeds 30001–30010:

`fedavg_window twostage_hajek fedau_window obsuse_window raven_wo_design raven`

Reuse `TD_R_ACCEPTED.json` for `fedavg_window` seed 30001. Do not drop methods.

```bash
# after CUDA python is the project env
python scripts/run_tdrive_rank_v1.py --stage train
```

`--stage train` runs the full matrix (skip `--stage all` so you do not recompute φ/traces). Confirm the driver skips completed accepted markers.

Keep `_tdrive_lowmem` on. 48GB RAM should hold IPW methods; if a method OOMs, stop with a hardware note — do not invent rankings.

## 3. Done when

- Remaining cells have `REAL_PATH_EXECUTED`
- `tables/TD_R_E3.csv` and `TD_R_E3_SUMMARY.csv` exist for the 10-seed matrix (or documented stop)
- `CLAIM_CEILING.md` copied under `results_tdrive_rank/round_v1/`
- Manuscript untouched

C1 becomes **moderate residual** only after a labeled hybrid T-Drive ranking table exists. It is not “end-to-end mobile MCS.”

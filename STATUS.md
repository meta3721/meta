# STATUS 鈥?RAVEN-MCS V2.3

**Updated:** 2026-08-03
**Workspace root:** `D:\Cursor\raven.mcs`  
**Source docs:** paper PDF + Cursor instruction TXT + design DOCX (`docs/SOURCES.md`)  
**Current phase:** E1-R2-FORMAL-RESULTS-AUDIT-AND-SEAL-R1
**Main experiments:** E1-R2 formal 25/25 complete; results audit/seal in progress

---
## P10 Status (2026-08-01)

| Section | Status | Description |
|---------|--------|-------------|
| P10-A | PASS | Chronological windows, tau invariants, historical checkpoints, and past-only estimator updates verified |
| P10-B | PASS | Estimated zeta/p/q and frozen atomic arrival-risk contributions verified |
| P10-C | PASS | FedAvg/TwoStage local and server paths produce distinct audited updates |
| P10-D | PASS | RMSE_mu/RMSE_rho are recomputed from atomic rows and Gap_mis identity is exact |
| P10-E | PASS | Two same-seed SensorScope runs pass R1-G1 through R1-G8 |
| E1 | NOT EXECUTED | Freeze identity sealed; awaiting teacher final execution authorization |

## Pre-E1 Seal

- `P10-R1 = PASS`
- `PRE-E1-SMOKE = PASS`
- `E1-ENTRY-INFRASTRUCTURE = PASS`
- `E1-ENTRY-SEMANTIC-AUDIT = FAIL`
- `E1-ENTRY-R1 = PARTIAL`
- `E1-ENTRY-R2 = PASS`
- `E1-OPPORTUNITY-SUPPORT-AUDIT = PASS`
- `E1-ENTRY-R3 = PASS`
- `E1-STAGE2-ATTEMPT-SEMANTICS = PASS`
- `E1-ARRIVAL-SUPPORT-METRIC = PASS`
- `E1-ENTRY-R4 = PASS`
- `E1-FORMAL-R1 = BLOCKED_BY_FREEZE_IDENTITY`
- `E1-FORMAL-FREEZE-R1 = PASS`
- `E1-FORMAL-FREEZE-R1-CONFIG = PASS`
- `E1-FORMAL-FREEZE-R1-MANIFEST = PASS`
- `E1-FORMAL-FREEZE-R1-VALIDATION = PASS`
- `E1-FORMAL-FREEZE-R1-PREFLIGHT = CONDITIONAL PASS`
- `EXECUTION-CANDIDATE-CODE-AUDIT = PASS`
- `E1-FORMAL-FREEZE-R1.1 = PASS`
- `E1-FORMAL-FREEZE-R1.1-DIFF-AUDIT = PASS`
- `E1-FORMAL-FREEZE-R1.1-CORE-EQUIVALENCE = PASS`
- `E1-FORMAL-RUNNER = PASS`
- `E1-FORMAL-STATISTICS = READY (not executed; matrix incomplete)`
- `E1-FORMAL-EXECUTION-R1 = PARTIAL`
- `E1-FORMAL-WEIGHT-SAFETY-DIAG-R1 = PARTIAL`
- `E1-R1 = PERMANENTLY_STOPPED / PERFORMANCE NOT EVALUATED`
- `E1-R2-PROTOCOL-CALIBRATION-R1 = PASS`
- `E1-R2-FORMAL-FREEZE-SEAL-R1 = PASS`
- `E1-R2-CANDIDATE-HEAD-CHECK-R1 = PASS`
- `E1-R2-FORMAL-EXECUTION-R1 = PASS (25/25)`
- `E1-R2-FORMAL-RESULTS-AUDIT-AND-SEAL-R1 = PASS`
- `E1-R2 = SEALED / FORMAL 25/25 / STATISTICAL SUPERIORITY NOT ESTABLISHED`
- `E2-E9 = NOT STARTED`

Phase A sealed `formal_execution_commit=c077cfb7...` with HARNESS-G1..G10
PASS. Phase B fail-fast stopped on
`E1_FORMAL_fedavg_window_26001_*` when
`first_stage_clip_rate鈮?.0637 > 0.05` (E1-RUN-G6). Failed run retained;
24 remaining formal runs not started; no retuning. DIAG-R1 reproduced that
macro `>=` rate exactly, found zero exact-boundary hits and risk/observed
true-exceed rates above 5% within persisted attempted-client rows, and
determined the original gate definition is materially incomplete (branch C
protocol clarification). Full all-client micro reconstruction remains pending
because nonattempted p/zeta vectors were not persisted. Evidence under
`deliverables/RAVEN_MCS_E1_WEIGHT_SAFETY_DIAG_R1_EVIDENCE.zip`.

E1-R2 now uses a unique observed-record global-micro true-exceed gate
(`u > a_max + 1e-12`, threshold 5%) with disjoint 100-window calibration,
validation, and formal seed roles. C0 (`a_max=20`) failed calibration; C1鈥揅3
passed. Validation rejected C1 on per-seed safety and selected C2
(`a_max=40`, opportunity forgetting unchanged at 0.95) over C3 by the
pre-registered RMSE rule. The validation baseline is
`flamf_timealign_adapted`; no-harm upper 95% is about 0.00146 < 0.03.
R2P-G1鈥揋10 PASS. Formal seeds 28001鈥?8005 have structural traces only:
zero training, prediction, RMSE, clip, or ESS outputs.

R2 freeze-seal binds the protocol, runner, observed-record global-micro
strict-exceed gate, aggregate rejection rules, and all 15 traces to one clean
execution candidate. The real runner compatibility smoke used calibration
seed 27001 for two non-formal windows only; formal aggregation rejected it.
R2FS-G1鈥揋10 PASS; formal execution remains 0/25.

## P10-E Smoke Results (2026-08-01)

Runs: `outputs/runs/P10_SMOKE_20260801_102055/` and
`outputs/runs/P10_SMOKE_20260801_102515/`

| Method | RMSE_mu | RMSE_rho | Gap_mis | Train Loss | Active Win | Time |
|--------|---------|----------|---------|------------|------------|------|
| FedAvg-Window | 7.1818 | 7.0646 | 0.1172 | 7.8376 | 20/20 | 69.7s |
| TwoStage-Hajek | 7.1572 | 7.0400 | 0.1172 | 7.9108 | 20/20 | 70.6s |
| RAVEN-MCS | 7.1111 | 6.9937 | 0.1174 | 7.9075 | 20/20 | 74.6s |

All P10 smoke checks and R1-G1 through R1-G8: **PASS**.


## P10 Code Status

- **E1 five methods: official entry verified**
- Central-All/Central-Delivered: marked as requiring true centralized training (NotImplementedError in aggregation)
- FLAMF-Original: external baseline not integrated
- Old WindowRunner moved to `synthetic_gate_runner.py` for G2-G5 gates
- New `window_runner.py`: full Common-NDMF training with local SGD, two-stage correction, debt, variance
- `configs/frozen/`: frozen config gate for test-entry (ISSUE-010)
- Statistical tests rewritten to read real results from `per_seed_metrics.parquet`

---

## Phase checklist

| Phase | Status | Notes |
|-------|--------|-------|
| 0 Audit + plans | **DONE / RE-AUDITED** | Reproducible full-scope evidence in `docs/audits/phase0_audit.json` |
| 1 Env / config / manifest | **DONE / REPAIRED** | Strict seed/config/resume/determinism semantics and lifecycle smoke |
| 2A Data framework | **DONE** | Schema/split/scaler/audit/hash/CLI; synthetic smoke only |
| 2B Four real adapters + G0 | **DONE** | Official downloads + adapters frozen; G0 PASS (see below) |
| 3 Target / strata | **DONE** | TargetBuilder / GroupMapper / StrataMapper |
| 4 EventTrace + G1 | **DONE** | Immutable parquet+hash; G1 PASS |
| 5 Common-NDMF | **DONE** | Shared backbone; no client embedding |
| 6 WindowRunner + G2 | **DONE** | Frozen 胃 + one update; G2 PASS |
| 7 Propensity / opportunity | **DONE** | Lagged p/q + EMA opportunity cores |
| 8 Methods | **PARTIAL** | E1 five-method official entry verified; centralized methods remain pending |
| 9 P2 / debt + G3鈥揋5 | **DONE** | G3鈥揋5 PASS via `check_hard_gates.py` |
| 10 Metrics / artifacts | **DONE FOR E1 ENTRY** | Full predictions, risks, RMSE/Gap/ESS/clip/solver artifacts |
| E0 unit suite | **DONE** | E0.1鈥揈0.6 green via `scripts/check_e0.py` |
| E1 Balanced / G6 | READY_FOR_FINAL_EXECUTION_AUTHORIZATION | Freeze-R1 PASS; formal 25-run E1 not started |
| E2鈥揈9 / 20-seed | BLOCKED | |

---

## Phase 0 re-audit (2026-07-31)

- Added `scripts/audit_phase0.py` and a reusable scanner that records a complete
  sorted tree, exact patterns, candidate files, line-level hits, exclusions,
  read failures, test-gate state, and run artifacts.
- Re-ran dataset/model, immediate-async, test-tuning, q post-outcome leakage,
  and P2/current-update scans over `src/`, `scripts/`, `configs/`, `tests/`,
  and `notebooks/`.
- No algorithm implementations exist yet; negative q/P2/async findings are
  explicitly classified as vacuous and do not pass G2/G4.
- Frozen the machine-readable evidence at `docs/audits/phase0_audit.json`.
- Confirmed no main run artifacts exist (`outputs/runs/.gitkeep` only).

---

## Phase 1 strict-audit remediation (2026-07-31)

- Reconciled the instruction/DOCX seed taxonomies into nine deterministic
  streams: master, data, opportunity, observation, event, model, solver,
  bootstrap, and MC oracle.
- Resolved all streams into the config and manifest; the run hash now includes
  every stream and rejects caller/config divergence.
- Config validation now rejects NaN/Inf, numeric strings, unknown keys, invalid
  named config slices, and seed-master mismatches.
- `--resume` never creates a missing run. Changed identity is rejected, and an
  explicit `resume_from` path is required when the derived path is unavailable.
- Checkpoints verify the manifest config before saving and cannot overwrite an
  existing window checkpoint.
- Python is constrained to 3.11.x; Torch deterministic algorithms are strict;
  actual runs require `PYTHONHASHSEED` to have been set before interpreter
  startup.
- `environment.yml` consumes the exact pip lock before editable installation.
- Added `smoke_run_lifecycle.py`, which exercises manifest creation, atomic run
  ownership, checkpoint save/load, metrics output, and finalization without
  training or launching a main experiment.
- Added failure-path tests for seed mismatch, non-finite/unknown config,
  process hash determinism, changed-config resume, and checkpoint overwrite.
- Full current suite: **63 passed**.

---

## Phase 1 report (2026-07-30)

### 1. 鏈樁娈靛畬鎴愬唴瀹?

- Built `src/raven_mcs/` package layout and `configs/` tree.
- Implemented seed manager and RNG capture/restore, package-aware environment hash, stable run hash, YAML config validation, manifest start/finalize lifecycle, atomic run-directory ownership, and binary checkpoint resume.
- Added `scripts/verify_run.py` (`--check-environment`, `--check-repository`).
- Cleaned accidental dirs (`correctionmkdir`, `utilsmkdir`) and misnamed `requirements.txt.txt`.
- Verified on project `.venv` Python **3.11.8**; regenerated `requirements-lock.txt`.

### 2. 鏂板/淇敼鏂囦欢

- `pyproject.toml`, `environment.yml`, `requirements.txt`, `requirements-lock.txt`, `Makefile`, `README.md`, `CHANGELOG.md`, `.gitignore`
- `configs/**`
- `src/raven_mcs/**` (including `utils/run.py`, manifest lifecycle, experiments stubs, binary training checkpoints)
- `scripts/verify_run.py`
- `tests/unit/test_*.py` (including run lifecycle and strict Git behavior)
- Updated `STATUS.md`, `ISSUES.md`

### 3. 鍏抽敭璁捐鍐崇瓥

- Use existing `.venv` (3.11.8) as official engineering interpreter for this machine.
- Seed module path kept as `utils/seed.py` (user-started file), exposing `seed_everything` / `SeedBundle`.
- Config: YAML + deep merge; malformed types/ranges are rejected.
- Run identity hashes config, data, EventTrace, environment/packages, Git commit, and seed.
- Actual runs require real SHA-256 data/EventTrace hashes; no `UNSET`.
- Output directories are atomically claimed, never overwritten, and finalized with end time/status/failure reason.
- Resume verifies config hash + run hash and restores Python/NumPy/Torch RNG state.
- Paper-facing runs require Git by default; Git 2.55 is installed and the repository is initialized.
- Canonical configs live under `configs/`; empty legacy `config/` and `raven/` ignored.

### 4. 瀵瑰簲璁烘枃鍏紡

- None numerically; infrastructure only (F1鈥揊9 still PLANNED).

### 5. 杩愯鐨勫懡浠?

```text
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe scripts\verify_run.py --check-environment
.\.venv\Scripts\python.exe scripts\verify_run.py --check-repository
.\.venv\Scripts\python.exe -m pytest -q
```

### 6. 娴嬭瘯缁撴灉

- ENVIRONMENT CHECK **PASSED** (Python 3.11.8 matches official pin)
- REPOSITORY CHECK **PASSED**
- Manifest schema/value check: **21 required fields** (adds `run_hash` and `git_state_hash`)
- pytest: **33 passed**
- Strict `--require-git`: **required for paper-facing runs**

### 7. 纭棬鐘舵€?

| Gate | Status |
|------|--------|
| G0 | PASS (Phase 2B) |
| G1鈥揋5 | PASS (`scripts/check_hard_gates.py`) |
| G6鈥揋7 | Pending (E1 / oracle ordering) |
| E0 | DONE (formula unit suite) |

### 8. 鍙戠幇鐨勯棶棰?

- ISSUE-001 mitigated via `.venv` 3.11.8.
- ISSUE-002 resolved: Git installed and repository initialized with an auditable initial commit.
- ISSUE-006: no raw datasets yet.
- Empty legacy `config/`, `raven/`, `docs/IMPLEMENTATION_PLAN.md.txt` remain.

### 9. 灏氭湭瀹屾垚浜嬮」锛圥hase 1 handoff锛?

- E0.1鈥揈0.6 synthetic fixtures and formula tests
- Phase 2B real adapters and Phases 3鈥?0
- Real datasets

### 10. 涓嬩竴姝ュ姩浣滐紙updated after Phase 2A锛?

1. Acquire raw data and implement Phase 2B real adapters / G0.
2. Implement **E0** formula, P2, debt, and leakage tests in parallel.

---

## Phase 2A report (2026-07-30)

### Completed

- Added canonical `atomic_units.parquet` and `client_measurements.parquet`
  schemas with strict type/value/reference validation.
- Added unique-time-slot 60/20/20 splitting, first 20% of train as warm-up,
  monotonic time indices, and no time/unit overlap checks.
- Added immutable train-only scaling statistics and source-value hashes.
- Added deterministic identity-level 30/70 fleet splitting for future T-Drive
  use, with reference/client disjointness enforcement.
- Added adapter contract, deterministic synthetic fixture, unit/provenance/
  anomaly audits, raw/interim/processed SHA-256 manifests, freeze/resume
  refusal semantics, and `prepare_data.py` / `audit_data.py`.
- At Phase 2A freeze time, real dataset names failed explicitly; synthetic data
  was never silently substituted. Real adapters landed later in Phase 2B.

### Verification (historical, 2026-07-30)

```text
.\.venv\Scripts\python.exe -m pytest -q
47 passed
```

- CLI prepare+freeze+audit is exercised end-to-end in
  `tests/unit/test_data_cli.py`.
- No paper formula F1鈥揊9 is claimed as numerically implemented.
- **G0 status at Phase 2A close:** not yet passed (real adapters / provenance
  missing). **Superseded by [Phase 2B report](#phase-2b-report-2026-07-31):**
  four official adapters frozen and `g0_overall=PASS`. The separate
  experiment-config/test-entry leakage gate remains ISSUE-010.

### Next (historical; completed in Phase 2B)

1. Acquire/document raw SensorScope, U-Air, Traffic Volume, and T-Drive data.
2. Implement and audit each real adapter; stop on Traffic continuity failure.
3. Run G0 data checks 鈥?see Phase 2B. Test-entry freeze gate remains open.

---

## Phase 2B report (2026-07-31)

### Completed

- Auditable downloader: `scripts/download_data.py` + `src/raven_mcs/data/download.py`
  with provenance JSON and checksum verification.
- Real adapters: `sensorscope`, `uair`, `traffic`, `tdrive_speed` registered and
  frozen under `data/processed/` + `data/manifests/`.
- Traffic quality report written; hard floor 鈮?0脳336 met (selected **43脳720**).
  Preferred 鈮?0 stations **not** met 鈥?recorded, no PEMS substitution.
- G0 checker: `scripts/check_g0_data.py` 鈫?`docs/audits/g0_data_check.json`.
- Dictionary: `docs/DATA_DICTIONARY.md`.

### Per-dataset G0

| Dataset | Download | Freeze audit | G0 | Shape / notes |
|---------|----------|--------------|----|---------------|
| sensorscope | PASS (Zenodo md5 match) | PASS | PASS | 55脳312, coverage 1.0 |
| uair | PASS (`Data-1.zip`) | PASS | PASS | 36脳264, coverage 1.0 |
| traffic | PASS (TfNSW) | PASS | PASS | 43脳720; preferred 60 stations unmet |
| tdrive_speed | PASS (MSR zips 06鈥?14) | PASS | PASS | 500 m / 30 min; fleet 30/70 |

### Verification

```text
.\.venv\Scripts\python.exe scripts\check_g0_data.py --data-root data
g0_overall=PASS
.\.venv\Scripts\python.exe -m pytest
71 passed
```

### Next (historical; E0 completed)

1. Implemented in E0 report below.
2. Keep ISSUE-010 / ISSUE-012 before E1.

---

## E0 report (2026-07-31)

### Completed

- Correction cores: design ratio, H谩jek `a/m/膩/c`, ESS dual identity, stage-2 `d/b/尾`.
- Aggregation cores: debt update, coverage mix, CVXPY+CLARABEL P2, 位 constraints.
- Timing skeleton: `WindowClock` (胃 frozen in-window; one update; empty skip).
- Leakage scan: forbidden q feature tokens (E0.6).
- Tests: `tests/unit/test_e0_*.py`; runner `scripts/check_e0.py`.

### Verification

```text
.\.venv\Scripts\python.exe scripts\check_e0.py
e0_overall=PASS
.\.venv\Scripts\python.exe -m pytest
80 passed
```

### Scope note

E0 validates formula units on synthetic/hand fixtures. EventTrace / Common-NDMF /
WindowRunner / G1鈥揋5 were completed in the following report. E1 remains blocked.

### Next (historical; completed below)

1. Phase 3鈥? cores and G1鈥揋5 鈥?see following report.

---

## Phases 3鈥? + G1鈥揋5 report (2026-07-31)

### Completed

- Phase 3: `data/target.py`, `opportunities/strata.py`, support/mass audits.
- Phase 4: immutable EventTrace freeze/load/hash (`simulation/event_trace.py`).
- Phase 5: `models/common_ndmf.py` (no client embedding).
- Phase 6: `training/window_runner.py` with WindowClock invariants.
- Phase 7: lagged `ObservationPropensity` / `UsablePropensity` + opportunity EMA.
- Phase 8: Aggregator interface + FedAvg / FedAsync / TwoStage-Hajek / RAVEN.
- Phase 9: P2/debt wired through runner; G3鈥揋5 executable checks.

### Verification

```text
.\.venv\Scripts\python.exe scripts\check_hard_gates.py
g1_g5_overall=PASS
.\.venv\Scripts\python.exe -m pytest
89 passed
```

### Still open before E1

1. ISSUE-012 method-set / threshold confirmation.
2. ISSUE-010 test-entry freeze gate.
3. Full method roster / FLAMF / ablations / RMSE artifact pipeline (Phase 10).
4. G6 Balanced no-harm and G7 SimOracle ordering.

---

## Workspace move (2026-07-29)

- Root: `D:\Cursor\raven.mcs`. See ISSUE-008.


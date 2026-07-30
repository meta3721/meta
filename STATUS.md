# STATUS — RAVEN-MCS V2.3

**Updated:** 2026-07-30  
**Workspace root:** `D:\Cursor\raven.mcs`  
**Source docs:** paper PDF + Cursor instruction TXT + design DOCX (`docs/SOURCES.md`)  
**Current phase:** Phase 1 complete  
**Main experiments:** Not started (blocked until E0 + G0–G5; 20-seed main blocked until G6–G7)

---

## Phase checklist

| Phase | Status | Notes |
|-------|--------|-------|
| 0 Audit + plans | **DONE / RE-AUDITED** | Current tree, scan evidence, reusable/missing code and risks refreshed 2026-07-30 |
| 1 Env / config / manifest | **DONE** | Python 3.11.8; 33 tests pass; strict Git audit enabled |
| 2 Data adapters + G0 | NOT STARTED | Blocked on raw data (ISSUE-006) |
| 3 Target / strata | NOT STARTED | |
| 4 EventTrace + G1 | NOT STARTED | |
| 5 Common-NDMF | NOT STARTED | |
| 6 WindowRunner + G2 | NOT STARTED | |
| 7 Propensity / opportunity | NOT STARTED | |
| 8 Methods | NOT STARTED | |
| 9 P2 / debt + G3–G5 | NOT STARTED | |
| 10 Metrics / artifacts | NOT STARTED | |
| E0 unit suite | NOT STARTED | Next coding milestone |
| E1 Balanced / G6 | BLOCKED | |
| E2–E9 / 20-seed | BLOCKED | |

---

## Phase 0 re-audit (2026-07-30)

- Refreshed the repository tree after Phase 1 instead of presenting the original
  greenfield snapshot as the current tree.
- Re-ran dataset/model, immediate-async, test-tuning, q post-outcome leakage,
  P2/current-update, and client-ID model scans on `src/`, `tests/`, and `configs/`.
- No algorithm implementations exist yet; negative q/P2/async findings are
  explicitly classified as vacuous and do not pass G2/G4.
- Updated reusable Phase 1 code, missing algorithm modules, cleanup items, and
  current risks in `docs/IMPLEMENTATION_PLAN.md`.
- Confirmed no main run artifacts exist (`outputs/runs/.gitkeep` only).

---

## Phase 1 report (2026-07-30)

### 1. 本阶段完成内容

- Built `src/raven_mcs/` package layout and `configs/` tree.
- Implemented seed manager and RNG capture/restore, package-aware environment hash, stable run hash, YAML config validation, manifest start/finalize lifecycle, atomic run-directory ownership, and binary checkpoint resume.
- Added `scripts/verify_run.py` (`--check-environment`, `--check-repository`).
- Cleaned accidental dirs (`correctionmkdir`, `utilsmkdir`) and misnamed `requirements.txt.txt`.
- Verified on project `.venv` Python **3.11.8**; regenerated `requirements-lock.txt`.

### 2. 新增/修改文件

- `pyproject.toml`, `environment.yml`, `requirements.txt`, `requirements-lock.txt`, `Makefile`, `README.md`, `CHANGELOG.md`, `.gitignore`
- `configs/**`
- `src/raven_mcs/**` (including `utils/run.py`, manifest lifecycle, experiments stubs, binary training checkpoints)
- `scripts/verify_run.py`
- `tests/unit/test_*.py` (including run lifecycle and strict Git behavior)
- Updated `STATUS.md`, `ISSUES.md`

### 3. 关键设计决策

- Use existing `.venv` (3.11.8) as official engineering interpreter for this machine.
- Seed module path kept as `utils/seed.py` (user-started file), exposing `seed_everything` / `SeedBundle`.
- Config: YAML + deep merge; malformed types/ranges are rejected.
- Run identity hashes config, data, EventTrace, environment/packages, Git commit, and seed.
- Actual runs require real SHA-256 data/EventTrace hashes; no `UNSET`.
- Output directories are atomically claimed, never overwritten, and finalized with end time/status/failure reason.
- Resume verifies config hash + run hash and restores Python/NumPy/Torch RNG state.
- Paper-facing runs require Git by default; Git 2.55 is installed and the repository is initialized.
- Canonical configs live under `configs/`; empty legacy `config/` and `raven/` ignored.

### 4. 对应论文公式

- None numerically; infrastructure only (F1–F9 still PLANNED).

### 5. 运行的命令

```text
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe scripts\verify_run.py --check-environment
.\.venv\Scripts\python.exe scripts\verify_run.py --check-repository
.\.venv\Scripts\python.exe -m pytest -q
```

### 6. 测试结果

- ENVIRONMENT CHECK **PASSED** (Python 3.11.8 matches official pin)
- REPOSITORY CHECK **PASSED**
- Manifest schema/value check: **21 required fields** (adds `run_hash` and `git_state_hash`)
- pytest: **33 passed**
- Strict `--require-git`: **required for paper-facing runs**

### 7. 硬门状态

| Gate | Status |
|------|--------|
| G0–G7 | Still N/A / not executable |
| E0 | Not started |

### 8. 发现的问题

- ISSUE-001 mitigated via `.venv` 3.11.8.
- ISSUE-002 resolved: Git installed and repository initialized with an auditable initial commit.
- ISSUE-006: no raw datasets yet.
- Empty legacy `config/`, `raven/`, `docs/IMPLEMENTATION_PLAN.md.txt` remain.

### 9. 尚未完成事项

- E0.1–E0.6 synthetic fixtures and formula tests
- Phases 2–10
- Real datasets

### 10. 下一步动作

1. Implement **E0** synthetic fixture + weight/P2/debt/leakage unit tests.
2. Acquire raw data for Phase 2 / G0 in parallel.

---

## Workspace move (2026-07-29)

- Root: `D:\Cursor\raven.mcs`. See ISSUE-008.

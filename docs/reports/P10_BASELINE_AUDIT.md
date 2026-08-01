# P10 Baseline Audit — RAVEN-MCS V2.3

**Date:** 2026-08-01
**Branch:** `p10-end-to-end-integration`

---

## 1. Current Git Commit

- **Commit:** `44a70d2` — "fix: locate Git for strict audit checks"
- **Full hash:** `44a70d201b697f136fb4bc300a53b14038deb298`

## 2. Git Status

- Branch `p10-end-to-end-integration` created from `main`
- Modified: `.gitignore`
- Untracked: `.venv/`, `.pytest_cache/`, `__pycache__/`

## 3. Current Pytest Results

```
89 passed, 2 failed
```

**Pre-existing failures (not introduced by P10):**
- `test_corrected_mass_not_ess` — ESS identities disagree (10.67 vs 8.0)
- `test_phase0_audit_covers_full_executable_scope` — expected NOT_STARTED, got ARTIFACTS_FOUND

## 4. G0-G5 Audit Results

| Gate | Status | Checker |
|------|--------|---------|
| G0 | PASS | `scripts/check_g0_data.py` |
| G1 | PASS | `scripts/check_hard_gates.py` |
| G2 | PASS | WindowRunner frozen θ + one update |
| G3 | PASS | Hájek/ESS/β identities |
| G4 | PASS | CVXPY P2 constraints |
| G5 | PASS | debt prefix bound on runner path |

## 5. Current WindowRunner Known Placeholders

1. **Synthetic EventTrace only** — No real dataset integration
2. **Constant NumPy vector updates** — No real model training (lines 128-134)
3. **Synthetic composition via workload softmax** — Not from record groups (lines 95-104)
4. **oracle_q used directly** — No estimated q model (line 107)
5. **downloaded_version equality check** — Forces staleness check that should be relaxed (line 89)
6. **No local SGD** — Fixed synthetic updates
7. **No zeta/p estimation** — Uses oracle values
8. **No n_eff tracking** — Not computed
9. **No variance state** — Uses identity matrix
10. **No test predictions** — Only window metrics returned

**Resolution:** Old runner moved to `synthetic_gate_runner.py`; new full pipeline in `window_runner.py`.

## 6. Current Method Implementation Status

| # | Method | Status |
|---|--------|--------|
| 1 | Central-All | Implemented (uniform weights — NOT true centralized training) |
| 2 | Central-Delivered | Implemented (raw-count proportional — NOT true centralized training) |
| 3 | FedAvg-Window | Implemented |
| 4 | FedAsync-Window | Implemented |
| 5 | TimeAlign-Agg | Implemented |
| 6 | FLAMF-Original | Placeholder (uniform stub only) |
| 7 | Local-Hajek | Implemented (falls back to raw counts) |
| 8 | TwoStage-Hajek | Implemented |
| 9 | Inst-Cal | Implemented (broken: uses `1/raw_counts`) |
| 10 | Debt-Cal | Implemented (broken: uses `exp(-debt_client)`) |
| 11 | RAVEN-MCS | Implemented (full P2, but uses oracle_q) |
| 12 | RAVEN-SimOracle | Implemented |

**P10 target:** 11 deployable + 1 external pending (FLAMF)

## 7. Current Metrics/Statistics Scripts Placeholder Status

- `metrics/accuracy.py` — tail_rmse uses prediction error (wrong definition)
- `metrics/reachability.py` — epsilon_reach computes realized deviation (should be renamed)
- `scripts/statistical_tests.py` — uses random example data, not real results
- `scripts/freeze_config.py` — does not exist
- `configs/frozen/` — does not exist

## 8. Expected Modified Files

**New files:**
- `src/raven_mcs/data/processed_dataset.py`
- `src/raven_mcs/data/window_dataset.py`
- `src/raven_mcs/models/features.py`
- `src/raven_mcs/training/client.py`
- `src/raven_mcs/training/local_objective.py`
- `src/raven_mcs/aggregation/method_policy.py`
- `src/raven_mcs/metrics/reachability_optimization.py`
- `scripts/freeze_config.py`
- `configs/frozen/` directory
- `tests/unit/test_p10_*.py`
- `tests/integration/test_p10_end_to_end.py`

**Modified files:**
- `src/raven_mcs/training/window_runner.py` (rewrite)
- `src/raven_mcs/training/synthetic_gate_runner.py` (moved from old window_runner)
- `src/raven_mcs/aggregation/methods.py` (fix method semantics)
- `src/raven_mcs/correction/design_ratio.py` (update)
- `src/raven_mcs/propensity/observation.py` (update)
- `src/raven_mcs/metrics/accuracy.py` (fix tail definition)
- `src/raven_mcs/metrics/reachability.py` (rename epsilon_reach)
- `scripts/run_experiment.py` (real data fallback prohibition)
- `scripts/statistical_tests.py` (rewrite with real data)
- `ISSUES.md` (close ISSUE-012)
- `STATUS.md` (add P10 status)
- `docs/FORMULA_TO_CODE_MAP.md` (update mappings)

**Import updates:**
- `src/raven_mcs/training/__init__.py`
- `scripts/run_grid.py`
- `scripts/check_hard_gates.py`
- `tests/unit/test_phase4_to_9_gates.py`
- `tests/unit/test_critical_invariants.py`

## 9. Unchanged Paper Definitions

The following paper definitions are NOT modified by P10:

- F1.1–F1.7: Atomic units, strata, targets — definitions unchanged
- F2.1–F2.7: Windows and selection — definitions unchanged
- F3.1–F3.9: Design ratio and stage-1 correction — formulas unchanged, implementation updated
- F4.1–F4.2: Local objective — formulas unchanged
- F5.1–F5.4: Lagged variance and stage-2 — formulas unchanged
- F6.1–F6.8: Target debt and P2 — formulas unchanged
- F7.1–F7.9: Theory diagnostics — formulas unchanged
- F8.1–F8.4: Risks and RMSE — formulas unchanged
- F9.1–F9.2: Client measurement — formulas unchanged

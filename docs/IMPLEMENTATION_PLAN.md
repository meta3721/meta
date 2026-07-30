# RAVEN-MCS V2.3 Implementation Plan

**Role:** Chief Research Engineer + Experiment Auditor  
**Paper:** *RAVEN-MCS: Target-Risk-Calibrated Asynchronous Federated Data Completion under Two-Stage Non-Random Selection*  
**Plan date:** 2026-07-27  
**Workspace root:** `D:\Cursor\raven.mcs` (moved from `D:\Cursor\RAVEN` on 2026-07-29)  
**Source docs:** see `docs/SOURCES.md` (paper PDF + Cursor instruction + design DOCX)  
**Phase status:** Phase 0–1 complete; E0 / Phase 2 not started

---

## 0. Phase 0 Audit Summary

### 0.1 Initial greenfield snapshot (2026-07-27)

At the original Phase 0 audit, the repository contained only empty skeleton
directories plus the paper/instruction artifacts. There was no executable
dataset, model, federated-training, propensity, correction, P2, or metrics code.
That historical conclusion remains valid for the state that was audited then.

### 0.2 Current repository tree (re-audited 2026-07-30)

Generated with recursive PowerShell listing while excluding `.venv/`, `Lib/`,
cache directories, installed package metadata, and searchable reference extracts:

```
D:\Cursor\raven.mcs/
├── configs/
│   ├── config.yaml
│   ├── seeds_20.txt
│   ├── dataset/{synthetic,sensorscope}.yaml
│   ├── scenario/{balanced,complete_aligned}.yaml
│   ├── method/raven.yaml
│   └── experiment/{E0_unit,E1_balanced}.yaml
├── data/{raw,interim,processed,manifests}/   # no raw datasets
├── docs/
│   ├── IMPLEMENTATION_PLAN.md
│   ├── FORMULA_TO_CODE_MAP.md
│   ├── SOURCES.md
│   └── IMPLEMENTATION_PLAN.md.txt           # empty legacy stub
├── outputs/{runs,aggregate,figures,tables,reproducibility}/
├── scripts/verify_run.py
├── src/raven_mcs/
│   ├── data/ models/ opportunities/ propensity/ simulation/
│   │   └── __init__.py only
│   ├── aggregation/ correction/ metrics/
│   │   └── __init__.py only
│   ├── experiments/{hard_gates.py,registry.py}
│   ├── training/checkpoints.py
│   └── utils/{cli,config,hashing,logging,manifest,paths,run,
│              seed,serialization,validation}.py
├── tests/unit/
│   ├── test_cli_flags.py
│   ├── test_config_validation.py
│   ├── test_hashing.py
│   ├── test_manifest_complete.py
│   ├── test_run_lifecycle.py
│   └── test_seeding.py
├── pyproject.toml
├── environment.yml
├── requirements.txt
├── requirements-lock.txt
├── README.md
├── STATUS.md
└── ISSUES.md
```

Non-project/transient items observed and excluded from implementation analysis:
`.venv/`, `Lib/`, `.pytest_cache/`, `src/raven_mcs.egg-info/`, top-level empty
legacy `config/` and `raven/`, `tests/unitecho/`, and the Office lock file
`~$VEN-MCS_V2.3_实验设计方案.docx`.

### 0.3 Mandatory risk scans (current code)

Scope: executable/config code under `src/`, `tests/`, `configs/`; excludes
`.venv`, `Lib`, caches, binary source documents, and `docs/_ref_*`.

| Scan | Current result | Interpretation |
|------|----------------|----------------|
| Dataset adapters (SensorScope / U-Air / Traffic / T-Drive) | **None** | Dataset YAML exists, but no loader/adapter implementation |
| Model code (Common-NDMF / FLAMF / `nn.Module`) | **None** | `models/__init__.py` only |
| Old immediate-async/per-arrival global update | **No matches** | No legacy implementation to quarantine; G2 is not thereby passed |
| Test-set hyperparameter tuning | **No executable matches** | `test` occurs only in split configs/tests; no tuning implementation |
| `q` post-outcome features (`realized`, arrival, future, actual delay, update norm/value) | **No implementation** | Vacuous result until usable-propensity code and E0.6 exist |
| P2 reading current update coordinates/norm/direction | **No implementation** | Only P2 config validation/G4 enum exists; G4 is not passed |
| `client_id` embedding in shared model | **No model implementation** | Must be enforced when Common-NDMF lands |

Search evidence:

```text
data/model search:
  only generic dataset identifiers in config/manifest/path utilities
immediate async search:
  no matches in src/**/*.py
test-tuning search:
  no tuning/Optuna/best-parameter paths in src/**/*.py
q leakage search:
  only q_min/staleness configuration validation; no q feature builder
P2/update search:
  only lambda/alpha config validation and G4 enum; no P2 solver
```

### 0.4 Reusable, missing/rewrite, and risks (current)

| Category | Items | Decision |
|----------|-------|----------|
| **Reusable source documents** | Cursor instruction, paper PDF, design DOCX, `docs/SOURCES.md` | Keep; authority order documented |
| **Reusable Phase 1 code** | seed/RNG state, hashes/run identity, manifest lifecycle, output ownership, checkpoint/resume, config validation, CLI/logging | Retain and extend; 33 unit tests pass |
| **Reusable configs** | root config, seed list, initial synthetic/SensorScope/scenario/method/experiment configs | Extend without hidden hard-coded result parameters |
| **Must implement new** | data adapters, targets/strata, immutable EventTrace, Common-NDMF, p/q, Hájek/ESS, second stage, WindowRunner, P2/debt, methods, metrics, E0–E9 scripts | Not present |
| **Must rewrite** | No legacy algorithm implementation exists | Nothing to rewrite currently |
| **Must clean/ignore** | legacy empty dirs/stub, `tests/unitecho`, Office lock file, local environments/caches | Never include in paper artifacts |
| **Do not silently replace** | Traffic dataset if quality floor fails | Stop, record in `ISSUES.md`, obtain teacher approval |

Current risks:

1. Raw datasets are unavailable; Phase 2/G0 is blocked (ISSUE-006).
2. All algorithmic formula modules F1–F9 remain planned; absence of leakage/P2
   violations is currently a vacuous result, not a hard-gate pass.
3. Static E0.6 leakage enforcement and G0–G5 tests are not implemented.
4. Legacy/transient filesystem items may pollute naive recursive scans unless
   exclusions are preserved.
5. `configs/frozen/` is empty and there is no frozen-config hash or test-entry
   refusal mechanism; current resume config hashing is not a test-leakage gate.
6. Dataset split YAML is not yet validated for ratio sum, temporal order,
   overlap, or train-only scaler fitting.
7. `E1_balanced.yaml` references methods that are not implemented; it is a
   declaration only and cannot be run.
8. `verify_run.py --check-repository` verifies Phase 1 infrastructure only; it
   does not imply that data, models, E0, or G0–G7 are ready.

### 0.5 Acceptance decision

- Phase 0 tasks 1–8: **completed and re-audited**.
- Reusable code, missing/new code, rewrite status, and risks: **explicitly listed**.
- No main experiment was started: `outputs/runs/` contains only `.gitkeep`.
- Phase 0 does **not** claim E0 or G0–G5 correctness.

### 0.6 Constitution reminders (non-negotiable)

- Public city-level `Y_i`; no client-id prediction object.
- Windowed async: one `A_r`, one P2, one `θ_{r+1}` per window.
- Method-independent frozen EventTrace per seed.
- Pre-outcome only for `p`/`q` features.
- P2: solve `α` **before** aggregating `u`; never use current update coords for weights.
- Temporal train/val/test; freeze before test.

---

## 1. Target repository layout

Adopt instruction §四:

```
D:\Cursor\raven.mcs/          # workspace root (package name remains raven-mcs)
├── README.md, STATUS.md, ISSUES.md, CHANGELOG.md
├── pyproject.toml, requirements.txt, requirements-lock.txt, environment.yml, Makefile
├── configs/   # dataset / scenario / method / experiment / seeds / frozen
├── data/{raw,interim,processed,manifests}
├── docs/
├── src/raven_mcs/{data,opportunities,simulation,models,propensity,
│                  correction,aggregation,training,metrics,experiments,utils}
├── scripts/
├── tests/{unit,integration,regression,fixtures}
├── outputs/{runs,aggregate,figures,tables,reproducibility}
└── notebooks/exploratory_only/
```

---

## 2. Phased delivery (gates required)

| Phase | Goal | Hard gate before next |
|-------|------|------------------------|
| **0** | Audit + plan + formula map | Docs accepted; no main experiments | ✅ |
| **1** | Env, configs, seed/manifest/resume | `verify_run.py` env+repo checks |
| **2** | Four dataset adapters + freeze | **G0** |
| **3** | Target groups, strata, masses | Normalization / support tests |
| **4** | Immutable EventTrace + hash | **G1** |
| **5** | Common-NDMF (no client emb.) | Shape / init / public-context tests |
| **6** | WindowRunner | **G2** |
| **7** | Opportunity / p / q (lagged) | Leakage scan + diagnostics |
| **8** | All methods via Aggregator | Shared trace/model/budget |
| **9** | P2 + debt | **G3–G5** |
| **10** | Metrics + paper CLI | E0 green |
| **E0** | Synthetic + E0.1–E0.6 | pytest; G0–G5 → then E1 |
| **E1** | Balanced 5-seed | **G6** → then G7 |
| **E2–E9** | Full matrix | **G7** before 20-seed main |

**Rules:** No large untested dumps. Each phase ends with tests + smoke. Long tasks support `--dry-run --resume --max-workers --fail-fast --device --seed --output-dir`.

---

## 3. Phase work packages (summary)

1. **Env/repro:** Python 3.11 pin, seed_everything, manifest, config hash, checkpoint resume.
2. **Data:** SensorScope, U-Air, Traffic, T-Drive; unified parquet schema; 60/20/20 + warm-up 20% of train; train-only scaling.
3. **Target/opportunity:** `h(i)`, `s(i)`, `ϖ`, `π`; freeze on val.
4. **EventTrace:** Parquet + metadata; R/O/E/U/delays; method-agnostic; SimOracle MC q.
5. **Common-NDMF:** Shared backbone; no client_id.
6. **WindowRunner:** Frozen θ in window; one update; empty-window policy.
7. **Propensity:** Online logistic p/q; EMA opportunity; lagged only.
8. **Methods:** Central-*/Fed*/TimeAlign/Local-Hajek/TwoStage/Inst-Cal/Debt-Cal/RAVEN/SimOracle + ablations.
9. **P2/debt:** CVXPY+CLARABEL primary; prefix debt bound.
10. **Metrics/artifacts:** RMSE_μ/ρ, Δ_*, debt, reachability, system; aggregate + Wilcoxon+Holm + figures.

---

## 4. Default smoke (post-E0; not for Phase 0)

- `E3_main_complete` / `sensorscope` / seed `26001` / `K=50` / `R=300` / `complete_aligned`
- Statistics: 20 paired seeds, Wilcoxon, Holm
- Sensitivity: staged 3→5→20 seeds; **no** full Cartesian product

---

## 5. Next actions after Phase 0

1. Phase 1: package layout, env pin (ISSUE-001), seed/manifest/CLI.
2. Synthetic fixtures + E0.1–E0.6; `pytest -q`.
3. Only after E0 + G0–G5 → Balanced E1; only after G6–G7 → 20-seed main.

---

## 6. Reporting cadence

Each phase reports per instruction §十九: contents, files, decisions, formulas, commands, tests, gates, issues, remaining, next step.

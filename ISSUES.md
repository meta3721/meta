# ISSUES — RAVEN-MCS V2.3

Do **not** change paper datasets, metrics, or test protocols without teacher approval.

---

## Open

### E1-ENTRY-R1 semantic blockers

- **ISSUE-026 — G=4 mapping incompatible with temporal split.** Closed by
  repeatable UTC six-hour blocks and split-support audit.
- **ISSUE-027 — Local training uses target_value instead of
  potential_measurement.** Closed; exact `(client_id, unit_id)` lookup with no
  truth fallback.
- **ISSUE-028 — p_obs feature contains post-outcome observed count.** Closed;
  frozen pre-outcome whitelist.
- **ISSUE-029 — pi^tar_{k,s} is not frozen in zeta.** Closed; frozen parquet
  and identity hash.
- **ISSUE-030 — First-stage clip rate exceeds 5%.** Closed by validation-only
  safety selection without changing `a_max`.
- **ISSUE-031 — TimeAlign duplicates FedAsync.** **Blocked / unresolved.** No
  primary TimeAlign definition was found; teacher must provide it or approve
  method-registry re-freeze.
- **ISSUE-032 — Lagged empirical variance is not implemented.** Closed.
- **ISSUE-033 — P2 staleness is not normalized.** Closed.
- **ISSUE-034 — Config hash is mixed with target-group hash.** Closed in the
  R1 manifest and aggregator schema.
- **ISSUE-035 — EventTrace evidence export omits events.parquet.** Closed in
  the R1 exporter.
- **ISSUE-036 — Empty Tail/Head group returns zero.** Closed; now NaN and a
  run-stopping hard gate.

### ISSUE-020 — Official E1 runner ignores frozen G=4 mapping
- **Severity:** Blocking
- **Status:** Closed 2026-08-01; official runner validates the frozen mapping
  hash and explicitly runs debt/P2 with G=4.

### ISSUE-021 — Official E1 EventTrace generator uses dummy unit IDs
- **Severity:** Blocking
- **Status:** Closed 2026-08-01; five frozen traces use real SensorScope IDs
  and a stable SHA256 station-cluster mapping.

### ISSUE-022 — Official E1 runner does not emit full paper metrics
- **Severity:** Blocking
- **Status:** Closed 2026-08-01; every official run emits predictions,
  target/arrival risk, full run/window metrics and diagnostics.

### ISSUE-023 — aggregate_results does not emit per_seed_metrics.parquet
- **Severity:** Blocking
- **Status:** Closed 2026-08-01; strict aggregation emits parquet/CSV/run index,
  summary and failed-run inventory.

### ISSUE-024 — Validation baseline selection is not frozen
- **Severity:** Blocking
- **Status:** Closed 2026-08-01; selection uses validation only and is frozen
  in `e1_selected_baseline.yaml`.

### ISSUE-025 — FedAsync and TimeAlign lack official-entry smoke evidence
- **Severity:** Blocking
- **Status:** Closed 2026-08-01; both methods completed the official-entry
  single-seed smoke with diagnostics.

### ISSUE-014 — Chronological window/tau audit incomplete
- **Severity:** High
- **Observation:** P10 Smoke did not emit continuous-window, future-leakage, or tau-consistency audit evidence.
- **Status:** Closed 2026-08-01; R1-G1 recomputes chronological/tau evidence.

### ISSUE-015 — RMSE_rho used uniform weights
- **Severity:** High
- **Observation:** P10 Smoke did not compute atomic arrival-risk weights.
- **Status:** Closed 2026-08-01; R1-G2 verifies atomic contributions and normalization.

### ISSUE-016 — Gap_mis was inconsistent with RMSE definitions
- **Severity:** High
- **Observation:** P10 Smoke used group RMSE range rather than RMSE_mu - RMSE_rho.
- **Status:** Closed 2026-08-01; R1-G3 recomputes both RMSE values and the gap.

### ISSUE-017 — q feature scan not closed
- **Severity:** High
- **Observation:** MATCHES_REQUIRE_REVIEW was treated as accepted without an explicit whitelist.
- **Status:** Closed 2026-08-01; runtime q feature schema has no unreviewed matches.

### ISSUE-018 — FedAvg and TwoStage had forced identical behavior
- **Severity:** High
- **Observation:** MethodPolicy was not applied to local loss and q remained constant.
- **Status:** Closed 2026-08-01; weight, update, model, and prediction differences are audited.

### ISSUE-019 — P10 run artifacts incomplete
- **Severity:** High
- **Observation:** The prior Smoke lacked resolved config, trace ref, window, arrival, propensity, solver, system, checkpoint, and log artifacts.
- **Status:** Closed 2026-08-01; artifacts and hashes are checked by R1-G7.

### ISSUE-013 — Traffic preferred station coverage unmet
- **Severity:** Medium (does not fail hard floor)
- **Observation:** After TfNSW quality reporting and continuity repair, the best
  complete window under seed 26001 is 43 stations × 720 hours. Preferred design
  target is ≥60×720.
- **Rule:** Continue with hard-floor-compliant matrix; do not substitute PEMS.
  Teacher may later approve a dataset-description change if 60 stations are
  required as a hard constraint.
- **Status:** Open (informational).

### ISSUE-003 — Legacy empty plan stub
- **Severity:** Low
- **Observation:** `docs/IMPLEMENTATION_PLAN.md.txt` is an empty legacy file.
- **Status:** Cosmetic; canonical file is `docs/IMPLEMENTATION_PLAN.md`.

### ISSUE-004 — Source-document reconciliation
- **Severity:** Low
- **Observation:** Searchable PDF/DOCX extracts exist in `docs/_ref_*.txt`.
- **Rule:** Any PDF ↔ Cursor instruction formula conflict must stop for teacher review.
- **Status:** Monitoring.

### ISSUE-009 — Legacy/transient workspace items
- **Severity:** Low
- **Observation:** Empty legacy `config/`, `raven/`,
  `docs/IMPLEMENTATION_PLAN.md.txt`, `tests/unitecho/`, and an Office `~$*.docx`
  lock file are present. Local `.venv`, `Lib`, caches, and egg metadata must be
  excluded from audits/artifacts.
- **Plan:** Remove only after confirming no user-owned content; keep exclusions
  in all repository scans.
- **Status:** Open (does not block Phase 0/1).

### ISSUE-010 — Frozen experiment-config/test-entry gate incomplete
- **Severity:** High before any test evaluation
- **Resolved in Phase 2A:** Temporal ratio/order/overlap validation,
  `test_split_no_overlap`, train-only scaling with
  `test_train_only_scaling`, and raw/interim/processed data manifests.
- **Resolution:** Frozen config now binds config/data/group/EventTrace hashes,
  validation summary, timestamp, and Git commit. Test prediction refuses
  mismatched identities before model evaluation.
- **Status:** Closed 2026-08-01 by P10-R1 config/test-entry tests and R1-G7.

### ISSUE-011 — Declared E1 methods are not implemented
- **Severity:** Medium
- **Observation:** `configs/experiment/E1_balanced.yaml` names FedAvg,
  TimeAlign, TwoStage-Hajek, and RAVEN, but no corresponding aggregators,
  model, or runner exist.
- **Rule:** Treat E1 YAML as a declaration only; do not launch it before E0 and
  G0–G5.
- **Status:** Closed 2026-08-01; method registry and end-to-end runner are executable.

### ISSUE-012 — E1 gate protocol (CLOSED 2026-08-01, P10)
- **Status:** Closed. See resolution in "Closed / P10" section below.

---

## Mitigated / closed

- **PRE-E1 solver warning — CLOSED:** `optimal_inaccurate` and residual
  violations trigger SCS fallback; accepted solutions must pass explicit
  simplex, nonnegative, upper-bound, and ESS/L2 residual gates.
- **PRE-E1 staleness boundary — CLOSED:** EventTrace freezes `S_max=5`,
  requires usable updates to satisfy `tau <= S_max`, and rejects expired usable
  updates.

- **ISSUE-012 — CLOSED (P10, 2026-08-01):** E1 Balanced method set: FedAvg-Window,
  FedAsync-Window, TimeAlign-Agg, TwoStage-Hajek, RAVEN-MCS. Baseline: best
  validation RMSE_mu among FedAvg/FedAsync/TimeAlign (no test peek). No-harm:
  3% threshold, 95% one-sided CI upper bound < 3%, plus median local n_eff >= 2,
  clip rates <= 5%, no P2 failure, no NaN/Inf. 2% is reference only.

- **ISSUE-006:** Official SensorScope / U-Air / Traffic / T-Drive artifacts
  downloaded with provenance; four real adapters frozen; G0 data checks PASS.
  Traffic preferred ≥60 stations not met (see ISSUE-013); hard floor met.
- **ISSUE-001:** Project `.venv` is Python 3.11.8 and passes environment verification.
- **ISSUE-002:** Git 2.55 installed; repository initialized on `main` with an auditable initial commit. No Git config was modified.
- **ISSUE-005:** Canonical layout is `configs/` + `src/raven_mcs/`.
- **ISSUE-007:** No legacy immediate-async code found; G2 tests remain a future requirement.
- **ISSUE-008:** Root is `D:\Cursor\raven.mcs`; `scripts/` restored and misnamed requirements stub removed.
- **Phase 1 reproducibility audit:** Seed/config coherence, full seed-stream run
  identity, non-finite/unknown config rejection, explicit resume targeting,
  strict deterministic Torch mode, pre-start `PYTHONHASHSEED`, exact lock
  installation, and executable lifecycle smoke were repaired 2026-07-31.

---

## Closed / findings (Phase 0)

| ID | Finding |
|----|---------|
| F-P0-1 | Initial Phase 0 snapshot was greenfield; Phase 1 utilities are now reusable and listed in the refreshed plan. |
| F-P0-2 | No q post-outcome leakage in code (no propensity code). |
| F-P0-3 | No P2→current-update dependency in code (no P2). |
| F-P0-4 | No test-set tuning pathways in code. |

---

## Decision log

| Date | Decision | By |
|------|----------|----|
| 2026-07-27 | Prior Phase 0/1 wiped; restart from clean skeleton | User |
| 2026-07-27 | Phase 0 re-run: audit + plan + formula map only; no main experiments | Cursor / constitution |
| 2026-07-29 | Workspace root moved to `D:\Cursor\raven.mcs`; docs retargeted | User / Cursor |
| 2026-07-29 | Indexed paper PDF + design DOCX; added `docs/SOURCES.md` (authority: Cursor TXT → paper → design) | Cursor |
| 2026-07-30 | Phase 1 complete on `.venv` Python 3.11.8; E0 next | Cursor |
| 2026-07-30 | Phase 0 re-audited against current tree; stale tree/reuse/risk sections refreshed | Cursor |
| 2026-07-30 | Git installed and repository initialized; initial commit authored as `szr <2025198754@qq.com>` without modifying Git config | User / Cursor |
| 2026-07-30 | Phase 2A framework complete; real adapters/G0 remain blocked and synthetic substitution is forbidden | Cursor / constitution |
| 2026-07-31 | Repaired Phase 0 audit evidence and Phase 1 identity/resume/determinism semantics after strict three-document audit | Cursor |
| 2026-07-31 | Phase 2B: official downloads + four adapters frozen; G0 PASS; Traffic preferred 60 stations unmet → ISSUE-013 | Cursor |
| 2026-07-31 | E0.1–E0.6 formula unit suite implemented; E1 still blocked pending G1–G5 + ISSUE-012 | Cursor |
| 2026-07-31 | Phases 3–9 cores landed; G1–G5 PASS; E1 still blocked by ISSUE-012/G6 and incomplete method roster | Cursor |

# ISSUES — RAVEN-MCS V2.3

Do **not** change paper datasets, metrics, or test protocols without teacher approval.

---

## Open

### ISSUE-006 — Dataset availability unknown
- **Severity:** High (blocks Phase 2 / G0)
- **Observation:** No raw SensorScope / U-Air / Traffic / T-Drive data.
- **Plan:** Phase 2 must acquire or document it. Traffic continuity failure must stop the experiment; no silent substitution.
- **Status:** Open.

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

### ISSUE-010 — Test leakage/frozen-config gate not implemented
- **Severity:** High before any test evaluation
- **Observation:** `configs/frozen/` is empty. There is no validation of split
  ratio/time order/overlap, no train-only scaler enforcement, no frozen-config
  hash, and no test-entry refusal mechanism. Resume config hashing does not
  provide these guarantees.
- **Required resolution:** Implement dataset split/freeze logic and
  `test_no_test_leakage`, `test_split_no_overlap`, and
  `test_train_only_scaling` before test-set execution.
- **Status:** Open; planned for data/E0 work.

### ISSUE-011 — Declared E1 methods are not implemented
- **Severity:** Medium
- **Observation:** `configs/experiment/E1_balanced.yaml` names FedAvg,
  TimeAlign, TwoStage-Hajek, and RAVEN, but no corresponding aggregators,
  model, or runner exist.
- **Rule:** Treat E1 YAML as a declaration only; do not launch it before E0 and
  G0–G5.
- **Status:** Open.

---

## Mitigated / closed

- **ISSUE-001:** Project `.venv` is Python 3.11.8 and passes environment verification.
- **ISSUE-002:** Git 2.55 installed; repository initialized on `main` with an auditable initial commit. No Git config was modified.
- **ISSUE-005:** Canonical layout is `configs/` + `src/raven_mcs/`.
- **ISSUE-007:** No legacy immediate-async code found; G2 tests remain a future requirement.
- **ISSUE-008:** Root is `D:\Cursor\raven.mcs`; `scripts/` restored and misnamed requirements stub removed.

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

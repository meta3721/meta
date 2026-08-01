# Changelog

## Pre-E1 Seal

- Added strict P2 residual gates with SCS fallback on inaccurate CLARABEL results.
- Added explicit S_max enforcement and expired-update rejection.
- Renamed and documented `deadline_slack_pre` as registration-time information.
- Added Pre-E1 smoke entry point, solver/time/metric audits, and seal tests.

## 0.4.0 — 2026-07-31 (Phases 3–9 / G1–G5)

- Target/strata builders and opportunity EMA estimator
- Immutable EventTrace freeze/hash (G1)
- Common-NDMF shared backbone without client embedding
- WindowRunner with frozen-θ / one-update semantics (G2)
- Lagged observation/usable propensity cores
- FedAvg / FedAsync / TwoStage-Hajek / RAVEN aggregators
- Executable `scripts/check_hard_gates.py` for G1–G5

## 0.3.1 — 2026-07-31 (E0)

- Hájek / design-ratio / ESS / second-stage correction modules
- Debt dynamics + CVXPY/CLARABEL P2 solver with uniqueness checks
- Window timing skeleton and static q-feature leakage scan
- E0.1–E0.6 unit tests and `scripts/check_e0.py`

## 0.3.0 — 2026-07-31 (Phase 2B)

- Official auditable downloads for SensorScope / U-Air / Traffic / T-Drive
- Real dataset adapters with freeze/audit and `docs/DATA_DICTIONARY.md`
- Traffic station quality report + continuity hard-floor enforcement
- T-Drive 500 m / 30 min grid with stratified reference/client fleets
- G0 checker `scripts/check_g0_data.py` (all four frozen datasets PASS)

## 0.2.1 — 2026-07-31 (Phase 0–1 strict-audit repair)

- Reproducible full-scope Phase 0 tree and leakage/boundary scan evidence
- Nine coherent seed streams captured in config, manifest, and run hash
- Strict finite/type/unknown-key validation for root and named configs
- Explicit resume targeting that cannot create a changed-identity run
- Pre-start Python hash-seed and strict Torch deterministic enforcement
- Immutable checkpoint windows and executable Phase 1 lifecycle smoke
- Exact dependency lock wired into the Conda environment

## 0.2.0 — 2026-07-30 (Phase 2A)

- Canonical atomic-unit and client-measurement Parquet schemas
- Leakage-safe temporal split/warm-up and train-only scaling
- Dataset adapter/audit contracts and deterministic synthetic smoke fixture
- Identity-safe fleet split and target/client source disjointness checks
- Raw/interim/processed SHA-256 manifests with freeze/resume verification
- Data preparation/audit CLIs and 47-test suite
- Real paper adapters and G0 intentionally remain pending

## 0.1.0 — 2026-07-30 (Phase 1)

- Package skeleton `src/raven_mcs/`
- Config tree under `configs/`
- Seed manager, hashing, manifest, validation, checkpoint resume guard
- `scripts/verify_run.py`
- Phase-1 unit tests

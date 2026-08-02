# Changelog

## E1-FORMAL-EXECUTION-R1

- Sealed a single formal execution harness: `run_e1_formal.py`, per-run
  gates, formal aggregate/statistics/export, and HARNESS-G1..G10.
- Formal manifests require `formal=true`, 100 windows, `local_steps=2`,
  and separated protocol file/payload hashes.
- Wilcoxon and Holm outputs are written as nonempty pairwise tables.

## E1-FORMAL-FREEZE-R1.1

- Packaged authorized→candidate binary Git patch, source archive, and
  verifiable Git bundle without changing the execution candidate commit.
- Added hunk-level `e1_entry.py` audit and core-path blob equivalence
  evidence (`CORE_ALGORITHM_CHANGE = 0`).
- Clarified selected-baseline commit semantics and separated protocol file
  vs payload hashes in R1.1 evidence.
- Copied raw EventTrace, five-seed validation, pytest/JUnit, and exact
  command evidence; disclosed unavailable original candidate commit command.

## E1-FORMAL-FREEZE-R1

- Froze `local_steps: 2` in the formal protocol and schema; runner fails on
  missing/overridden values.
- Split identity into `authorized_algorithm_commit`,
  `protocol_parent_commit`, and runtime `execution_commit_policy`.
- Rebuilt `FROZEN_CONFIG_MANIFEST` from actual SHA-256 bytes, with
  selected-baseline hash verification and no self-hash cycle.
- Made outer `config_hash` equal `resolved_run_config_hash` only.
- Reconfirmed validation-only baseline and five-seed validation safety
  under the re-frozen protocol; did not start formal 25 runs.

## E1-ENTRY-R4

- Froze `attempted = 1{observed_count > 0}` before U and restricted q-use
  updates to that attempt set while retaining all failed attempts.
- Added persisted attempt/q diagnostics and exact leakage/omission gates.
- Masked arrival opportunity mass to zero outside frozen client-stratum
  support and regenerated deployment-risk metrics.
- Added final-commit pi-target reconstruction, distinct hash semantics,
  five-seed validation safety, R4 smoke, command evidence and packaging.

## E1-ENTRY-R3 opportunity-support and identity seal

- Changed opportunity estimation to one EMA transition per client-stratum and
  window, including decay for historical zero-count strata.
- Rebuilt pi target from the unique frozen station-client mapping, reducing
  positive support from the measurement Cartesian product to 440 real pairs.
- Added five-trace risk-support crosschecks and recomputed the nonzero
  calibration residual on real target support.
- Corrected Monday-zero UTC weekday encoding with the Unix epoch offset.
- Separated target-group and client-mapping payload/file hashes and made
  summary `config_hash` mean `resolved_run_config_hash`.
- Added machine-readable test, Git and exact-command evidence.

## E1-ENTRY-R2 final entry semantics

- Added the teacher-frozen FLAMF-TimeAlign-Adapted temporal-coverage baseline,
  distinct from FedAsync and transparent about its adaptation boundary.
- Removed post-outcome raw workload from formal arrival-risk reconstruction.
- Changed observation-propensity history to one lagged row per risk record.
- Froze the formal SensorScope E1 client count at eight and added clean-commit
  EventTrace generation gates plus R2 official smoke/aggregation entry points.

## E1-ENTRY-R1 semantic audit

- Replaced global time quartiles with repeatable UTC six-hour groups.
- Routed local labels through exact client potential-measurement lookup.
- Removed post-O workload from p features and froze client-stratum target mass.
- Added validation-only weight safety, lagged empirical variance, normalized
  staleness, separated identities, and recomputed EventTrace audits.
- Marked TimeAlign-Agg `BASELINE_UNRESOLVED`; its missing primary definition
  keeps formal E1 blocked instead of inventing a replacement.

## E1-ENTRY-SEAL

- Added the official SensorScope E1 runner with frozen G=4 main groups and
  separate 220-group diagnostics.
- Replaced the dummy EventTrace generator with five real-ID balanced traces
  and a seed-independent frozen station/client mapping.
- Added complete per-run prediction, risk, metric, ESS, clip, method, system
  and solver artifacts for all five E1 methods.
- Added strict `per_seed_metrics.parquet` aggregation, validation-only baseline
  freeze, selected-baseline no-harm dry-run and E1E-G1–G8 checks.
- Verified the official five-method, one-seed, 20-window entry smoke. Formal E1
  and E2–E9 remain unexecuted.

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

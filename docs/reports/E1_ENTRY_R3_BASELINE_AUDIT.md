# E1-ENTRY-R3 Baseline Audit

Date: 2026-08-02

## Repository and tests

- Baseline commit: `b7118d4abdfe12c7f37111f9c1e7d37106df777a`.
- Baseline worktree: clean.
- Full pytest: 315 passed, 3 skipped.
- R2 five-method, one-seed smoke passed; formal five-seed E1 was not run.
- Validation baseline: `flamf_timealign_adapted`.

## Opportunity estimator

`OpportunityEstimator.observe_lagged` currently applies
`C <- rho*C + count` on every risk record. `FullWindowRunner` invokes it once
per record-stratum occurrence. This is not the frozen once-per-window formula.
Historical strata absent from a window receive no decay. The current
`pi_hat_opp` therefore depends incorrectly on within-window record ordering.

## Target opportunity support

The R2 `pi_target` is built by merging every target atomic unit with
`client_measurements`. Because potential measurements are available across all
clients, it creates 3,520 positive client-stratum rows: 440 strata times eight
clients. The frozen station-client mapping instead assigns each station and
its strata to exactly one client, so the expected positive support count is
440.

The five EventTraces have not yet been cross-checked against positive target
support at the risk-set level. Consequently the old `Delta_cal` is invalid
under the corrected support and must be recomputed.

## Time feature

`models.features.extract_features` currently computes weekday as
`floor(unix_hours/24) % 7`. With Monday=0 this omits the Unix epoch offset
`+3`, shifting weekday by three days.

## Identity and protocol

R2 run manifests contain one ambiguous `client_mapping_hash` and one
`target_group_hash`; payload and file hashes are not separated. The frozen
protocol still says `BLOCKED_TIMEALIGN_BASELINE_UNRESOLVED` even though the R2
adapted TimeAlign path passed. Test evidence is a text log and cannot by itself
prove exit code, parsed counts or hash integrity.

## R3 entry status

R2 infrastructure and TimeAlign are retained as PASS, but the opportunity
support audit is FAIL. E1 is blocked until R3 gates pass.

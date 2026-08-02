# E1-ENTRY-R1 Baseline Audit

Date: 2026-08-02

## Repository identity

- Branch baseline commit:
  `e2b36d51622cd19856ef5a5c4c2fd8bcc468e113`.
- Worktree was clean before creating `e1-entry-r1-semantic-seal`.
- Full-suite baseline: `202 passed, 3 skipped`.
- Infrastructure seal passed, but this audit does not accept the method
  semantics as paper-ready.

## G=4 mapping and split support

The baseline config uses `mapping: time_index_quartile`. The implementation
splits the complete 312-slot axis into four one-off quartiles. Because the
dataset uses a 60/20/20 chronological split, validation and test do not carry
the same repeatable four-group support as train. This is incompatible with the
required repeatable UTC time-of-day blocks.

## Local measurement path

`extract_window_slice` reads `unit.target_value` for every observed client
record. It does not index `client_measurements.parquet` by
`(client_id, unit_id)` and therefore bypasses `potential_measurement`.

## Observation propensity features

The baseline p model declares `("bias", "hour_block", "workload")`.
`workload` is populated from `log1p(rec.raw_workload)`, while the EventTrace
generator defines `raw_workload = len(observed)`. This leaks the current O
outcome into the score used for that window.

## zeta target numerator

`FullWindowRunner._compute_zeta` falls back to a uniform vector over the
current risk-set strata because no frozen `pi^tar_{k,s}` is supplied. No
client-stratum target parquet or identity hash exists.

## Weight safety

The prior official-entry smoke reports:

- first-stage clip rate: `0.079782` for every method;
- second-stage clip rate: `0.025`;
- median n_eff: `2.0`.

The first-stage rate exceeds the frozen 5% gate. This must be repaired through
group/p/pi semantics and validation-only safety selection, not by silently
increasing `a_max`.

## FedAsync and TimeAlign

Both baseline implementations calculate sample-size weight multiplied by
`exp(-0.1*tau)`. Their official-entry predictions and metrics are identical,
so the two method names do not represent different execution semantics.

## Variance and staleness

The variance state stores only `(a_bar_floor + v_floor) / max(n_eff, 1)` and
never uses historical update dispersion. P2 receives raw `tau` rather than
`tau/S_max`.

## Identity fields

The run manifest lacks separately validated protocol, resolved-run,
client-mapping, pi-target and initial-model hashes. Aggregation maps
`config_hash` from `target_group_hash`, which mixes distinct identities.

## EventTrace evidence

The five frozen trace directories contain `events.parquet`, metadata, identity,
generation config, manifest and audit files. However, the baseline audit sets
window-overlap and unassigned-record counts to literal zero rather than
recomputing them, and the exporter initially included manifests without the
five parquet payloads.

## Tail/Head behavior

`tail_head_rmse` returns `0.0` when a selected Tail/Head group has no test
sample. The required behavior is NaN plus a run-stopping hard-gate failure.

## Baseline status

- `E1-ENTRY-INFRASTRUCTURE = PASS`
- `E1-ENTRY-SEMANTIC-AUDIT = FAIL`
- `E1 = BLOCKED`
- Formal five-seed E1 has not been executed.
- E2–E9 have not started.

# E1-ENTRY-SEAL Baseline Audit

Date: 2026-08-01

## Repository identity

- Branch baseline: `e1-entry-seal` created from
  `d273c17039f5e9479449756243f4772059e0296c`.
- Worktree before branch creation: clean.
- Full pytest baseline: `155 passed`.
- Pre-E1 Seal: PASS.
- Formal E1: not executed.

## Frozen protocol at baseline

- `configs/frozen/e1_sensorscope_balanced.yaml` declares SensorScope,
  balanced, five methods, seeds 26001–26005, 100 windows, `S_max=5`,
  G=4 scope and no-harm threshold 3%.
- `configs/frozen/e1_sensorscope_groups.yaml` defines four frozen time
  quartiles and retains 220 fine groups for diagnostics.
- The frozen protocol still points to the prior Pre-E1 commit and therefore
  must be regenerated after E1-ENTRY-SEAL code is committed.

## Official runner baseline

`scripts/run_experiment.py` rejects missing real-data EventTrace rather than
silently creating synthetic data. However, its real-data path passes
`processed.num_groups` into `build_full_runner`, returns only debt/active-window
summary fields, and does not create independent formal run directories with
predictions, paper metrics, solver diagnostics, checkpoints and final gate
statuses.

## EventTrace generator baseline

`scripts/generate_event_trace.py` builds a dummy atomic table containing
`u000000`-style IDs, uses 50 synthetic client identities and does not freeze
the required SensorScope station/client mapping, generation config or complete
E1 audit. This path is not acceptable for formal E1.

## Aggregation baseline

`scripts/aggregate_results.py` scans summary JSON files and emits only a JSON
debt/active-window aggregate. It does not produce
`per_seed_metrics.parquet`, CSV, run index, failed-run inventory or strict
seed/method/hash consistency checks.

## Statistics baseline

`scripts/statistical_tests.py` can read `per_seed_metrics.parquet`, but defaults
to FedAvg, does not read a validation-frozen selected-baseline file, does not
provide the required single-seed dry-run semantics, and does not emit the full
statistics artifact set.

## G=4 and method registry baseline

- G=4 group mapping exists, but the official runner does not consume it.
- The E1 config declares `fedavg_window`, `fedasync_window`,
  `timealign_agg`, `twostage_hajek` and `raven`.
- FedAsync and TimeAlign have not passed an official-entry end-to-end smoke.

## EventTrace identity baseline

The previous Pre-E1 trace uses real SensorScope IDs, but no five-seed,
100-window `e1_balanced_seed<seed>` family with client/group/data hashes exists.

## Open E1 entry gaps

1. Official G=4 integration and main/fine group separation.
2. Real-ID five-seed balanced EventTrace generation and stable client mapping.
3. Complete per-method run artifacts and independent metric recomputation.
4. Strict per-seed aggregation.
5. Validation-only baseline selection and freeze.
6. Selected-baseline statistical dry-run.
7. Five-method single-seed official-entry smoke.
8. E1E-G1 through E1E-G8 checker, exact command log and evidence export.

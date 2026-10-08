# RAVEN-MCS S1′: server optimizer re-screen (execution prompt)

## 0. Why this round exists

Measured on the frozen e3 checkpoints (seeds 30001–30003):

- the server step is `θ ← θ − η·Σ_i α_i·u_i` with `η = 0.01` and
  `u_i = Δ_i/(γ·E_loc)` (`client.py` L104–107, `window_runner.py` L1155–1167),
  so one window moves the global model by one SGD step of size 0.01 whatever
  `local_steps` is;
- the parameters of fedavg_window / raven / local_hajek move 0.26% (SS),
  0.40% (UA), 0.28% (Traffic) of their initial norm over the run, mostly through
  the output bias `head.8.bias`. Spatial embeddings move 0.01%. On SensorScope
  central_all moves `head.0.weight` by 12.2%;
- consequently N3 (federated learner off its floor) fails on every block, and the
  N4 headroom H measured with `raven_simoracle` was measured on an untrained
  model.

S1′ asks whether a standard server optimizer (FedAdam, Reddi et al., ICLR 2021)
applied to the unchanged pseudo-gradient `g_r = Σ_i α_i·u_i` makes the
federated learner learn, and if so re-measures H on all three blocks.

## 1. Hard constraints

- Do not edit `src/`, the paper, `tdrive_protocol_seal_r1/`, or any frozen
  artifact. Do not commit or push.
- All new code lives in `results_server_optimizer/round_v1/driver/`. All
  outputs go under `results_server_optimizer/round_v1/`.
- Do not resume X1. Do not ingest PATH_A NO2. Do not run the full `build()` of
  `build_public_repro_bundle.py`.
- The aggregation weights α, the client trainer, the model, the features, the
  data splits and the scenario are unchanged. No client-id embedding.
- Selection uses the validation split only. The test split is read only after
  the configuration is frozen in `S1P_FROZEN_CONFIG.json`.
- Any condition below that cannot be met without editing `src/` is a STOP: write
  `S1P_BLOCKED.md` and end the round.

## 2. Blocks, seeds, arms

| Block | Scenario | Arms |
|---|---|---|
| SensorScope | as in e3 formal runs | fedavg_window, raven_simoracle, raven |
| U-Air | as in e3 formal runs | fedavg_window, raven_simoracle, raven |
| NSW-Traffic | complete_aligned | fedavg_window, raven_simoracle, raven |

Screen seeds 30001–30005 for every stage. Confirm seeds 30006–30020 are not used
in this round. `raven` is descriptive only.

## 3. Driver

`ServerOptWindowRunner(WindowRunner)` overrides `_process_window`:

1. flatten `self.theta` → `θ_old`;
2. call `super()._process_window(...)`;
3. flatten the result → `θ_sgd`; recover `g_r = (θ_old − θ_sgd)/η`;
4. apply the server optimizer to `g_r` from `θ_old`, giving `θ_new`;
5. set `self.theta`, `self.model.load_state_dict`, and overwrite
   `self.model_versions[latest]` with `θ_new`.

FedAdam with bias correction: `m ← β1·m + (1−β1)·g`, `v ← β2·v + (1−β2)·g²`,
`θ ← θ − η_s·m̂/(√v̂ + τ)`, with β1 = 0.9, β2 = 0.99, τ = 1e-3. The state (m, v, t)
persists across windows and is created at the first window.

### Gates before any grid run

- **G0 identity**: with the optimizer set to plain SGD at `η_s = η` (i.e.
  `θ_new = θ_sgd`), reproduce the frozen `final_metrics.json` of fedavg_window
  and raven seed 30001 on each block bit-exact. Fail → STOP.
- **G1 reads-after-update audit**: list every line of `_process_window` after
  L1169 that reads `self.theta`, `self.model` or `model_versions`, and state
  for each whether the override makes it see `θ_new`. Any logged metric that
  would still see `θ_sgd` must be named in `S1P_GATES.md`. If such a metric
  feeds `final_metrics.json`, STOP.
- **G2 determinism**: the same (block, arm, seed, config) run twice gives
  identical `final_metrics.json`.

## 4. Stage A: optimizer grid (R = 1)

Grid `η_s ∈ {1e-3, 3e-3, 1e-2}`, arm fedavg_window only, 3 blocks × 5 seeds ×
3 = 45 runs.

Per run record: validation and test `RMSE_μ` (test sealed until §4 selection is
written), final training Hájek loss, relative parameter movement per tensor, and
any NaN/Inf (a diverged run counts as failed for that η_s).

**Selection (per block, pre-registered)**: η_s* = argmin of the mean validation
`RMSE_μ` over the 5 seeds among non-diverged levels; ties within 0.1% go to the
smaller η_s. Write `S1P_FROZEN_CONFIG.json` with η_s* per block and its sha256
before opening test.

**N3′ (per block)**, on test `RMSE_μ`, 5-seed means:

- `c` = frozen central_delivered on the same seeds;
- PASS if `RMSE_μ(fedavg, η_s*) ≤ 1.01·c`;
- PARTIAL if not PASS but `RMSE_μ(fedavg, η_s*)` is ≥ 1% below the frozen
  fedavg_window on the same seeds;
- FAIL otherwise.

Diagnostic only, not a gate: `head.0.weight` relative movement ≥ 5%.

## 5. Stage B: rounds per window (only if a block is PARTIAL or FAIL)

Only for blocks not PASS at Stage A. Implement R server rounds per window in a
copied `_process_window` inside the driver: the clients recompute local updates
on the same delivered records from the current θ in each round, α is computed
once per window from the round-1 payload and held fixed, and the staleness
bookkeeping advances once per window. G0 is repeated with R = 1 and must be
bit-exact before any R > 1 run.

Grid `R ∈ {3, 10}` at that block's η_s*, fedavg only, 5 seeds. Select by
validation as in §4 and append to `S1P_FROZEN_CONFIG.json` before opening test.
N3′ is re-evaluated with the same rule. If the copy cannot reproduce G0, write
`S1P_BLOCKED.md` for Stage B and keep the Stage A verdict.

## 6. Stage C: headroom re-measure (blocks that PASS N3′)

With the frozen config, run raven_simoracle and raven on the same 5 seeds.

`H = (RMSE_μ(fedavg) − RMSE_μ(raven_simoracle)) / RMSE_μ(fedavg)`, paired by
seed; percentile bootstrap 10,000, rng 20261007.

GO-H if `H ≥ 1%`, the 95% lower bound > 0.5%, and `MDE80 < 0.5·H` computed from
the paired seed SD at n = 15. Report for SS and UA also the K_r ≤ 3 window share
under the new config (N1 remains structural there), and do not upgrade SS/UA
to GO if more than 25% of active windows have K_r ≤ 3.

`raven` vs fedavg is reported descriptively, with no test and no decision label.

## 7. Outputs (`results_server_optimizer/round_v1/`)

- `S1P_GATES.md` (G0, G1, G2 with hashes)
- `tables/STAGE_A_GRID.csv`, `tables/STAGE_B_GRID.csv` (if run),
  `tables/MOVEMENT.csv`, `tables/STAGE_C_H.csv`
- `S1P_FROZEN_CONFIG.json`
- `S1P_VERDICT.json`: per block N3′ ∈ {PASS, PARTIAL, FAIL}, and H verdict ∈
  {GO-H, NO-GO-H, not_run}
- `S1P_REPORT.md`: the numbers, the verdicts, and the deviations. No proposal for
  the paper.

The round ends at Stage C. The confirmatory run on seeds 30006–30020 and any
change to frozen tables need a separate authorization.

# HANDOFF: Option B — T-Drive hybrid method ranking (real R, controlled O/U)

Paste this to the executor AI:

```text
You are the TD-R-E3 executor for repo C:\Cursor\raven.mcs.
Read this entire file and post_review/C1_tdrive_rank/PROTOCOL.json.
This round AUTHORIZES T-Drive method ranking that older seals marked DO_NOT_RUN.
It does not authorize overlaying T-Drive GPS onto SensorScope/U-Air.
It does not authorize mixing results into Table II.
It does not authorize Design_t := Gate_t.
It does not authorize choosing Design from RMSE / Y / residuals.
Python: C:\Cursor\raven.mcs\.venv_new\Scripts\python.exe
Execute §9 in order. Stop after Phase 1 (φ) and ask the human only if a stop condition in §0 fires. Otherwise freeze SCD from φ and continue.
```

```text
Experiment ID: TD-R-E3
Question answered: Can we rank the Table II methods under real taxi opportunity R?
Question NOT answered: End-to-end mobile MCS; real O/U logs; SensorScope/U-Air have mobile clients.
Round directory: results_tdrive_rank/round_v1/
Trace root: artifacts/e3_tdrive_rank_eventtraces_v1/
Paper method: support-conditional Design (SCD) via φ=0, NOT coverage Gate
```

This experiment exists because review concern **C1** is that E3 ranking is protocol MCS (station arrays, always-on R). Option B adds one **hybrid ranking block** on T-Drive: \(R\) is trajectory-derived; \(O\) and \(U\) stay Complete-aligned controls.

Older files (`TDRIVE_MANUSCRIPT_LEVEL_GO_NO_GO.md`, `formal_tdrive_runs_authorized=false`, canary `NOT_AUTHORIZED_YET`) are **superseded for this round only**. Do not delete or rewrite the seal. Do not treat E9 yaml as this protocol.

---

## 0. Role and stop conditions

Implement φ, freeze SCD, generate shared EventTraces, train the mandatory matrix, write CSVs, and stop. **Do not edit the manuscript in this round.**

Stop and ask the human if any of the following happens:

- You cannot compute φ without labels \(Y\), RMSE, residuals, or E3/T-Drive test error.
- You would need `build_pi_target_support_compatible`.
- You would overlay T-Drive GPS on SensorScope/U-Air stations, or change SS/U-Air SCD.
- You would set Design from T-Drive RMSE after seeing rankings.
- You would write T-Drive numbers into Table~\ref{tab:main_effectiveness}.
- You would overwrite `tdrive_protocol_seal_r1/` or processed `data/processed/tdrive_speed/` hashes.
- Processed T-Drive parquet / client_measurements / H-seal JSON is missing, or frozen hashes in the protocol master do not match.
- EventTrace hashes differ across methods for the same seed.
- GPU/CPU is insufficient after φ + traces + canary. Then stop with what you have; do not invent rankings.

Do not start SAG, certificate ranking, NSW-Traffic E3, or INT-R retraining. Do not `git push`. Do not commit unless asked.

---

## 1. Scientific contract

| Layer | Source | Label |
| --- | --- | --- |
| \(R\) | processed `client_measurements` presence | **REAL_FROM_TDRIVE** |
| \(O\) | Bernoulli \(p_{\mathrm{obs}}=0.35\) on each \(R=1\) unit | controlled experimental |
| \(U\) | `compute_usable_r3`, \(s_{\max}=5\) | controlled experimental |
| Clients | client-fleet taxis `vehicle::{id}` | real vehicles; reference fleet builds \(Y\) only |
| SCD | \(\mathrm{Design}=\mathrm{ON}\iff\phi=0\) | same rule as Algorithm 2; no RMSE |

Allowed later wording (writing pass, not this round): "method ranking under real-mobility opportunity; O/U remain Complete-aligned controls."

Forbidden wording (now and later):

- end-to-end MCS / real federated updates / real sensor failure logs / energy
- SensorScope or U-Air traces contain mobile clients
- T-Drive RMSE dominance
- Gate switches Design
- INT-R occupancy is this experiment

C1 is addressed by **having** this ranking with honest labels. RAVEN does not need to beat FedAU on RMSE for C1 to close. Do not stop training because a number looks bad. Do not retune \(\phi\), \(p_{\mathrm{obs}}\), \(s_{\max}\), or P2 to improve RMSE.

---

## 2. Frozen protocol (do not retune)

Authority: `tdrive_protocol_seal_r1/` and `src/raven_mcs/tdrive_protocol_seal_r1/`. Read-only seal tree.

Ignore `configs/experiment/E9_tdrive.yaml` (wrong seeds 26001–26010, `num_windows=300`, incomplete methods).

```text
Dataset id: tdrive_speed
Protocol: TDRIVE_REAL_MOBILITY_PROTOCOL_R1
Atomic: data/processed/tdrive_speed/atomic_units.parquet
Measurements: data/processed/tdrive_speed/client_measurements.parquet
μ (evaluation): tdrive_protocol_seal_r1/03_target/TDRIVE_TARGET_H_SEAL.json
  H1–H4 Beijing-local TOD from processed wall-clock hour (fallback_h_id; do not apply +8)
h(i): H1–H4, NOT processed target_group (that field couples spatial_id)
s(i): processed opportunity_stratum = spatial_id :: block{0-3} :: weekday|weekend
Fleet split seed: 26001 (already in processed data; do not re-split)
Formal seeds: 30001 .. 30010  (sealed; not 20, not 50)
Canary: seed 30001, one method, before the full matrix
Micro fixture: 31999 (generator hash-independence only)
R independent of formal seed and of method
O/U/init depend on formal seed; shared EventTrace per seed across methods
Windows: one window per unique TRAIN time slot, chronological (n_train_slots=178)
p_obs: 0.35
s_max: 5
window_duration: 1.0
P2: lambda_group=1.0, lambda_beta=1.0, lambda_v=0.1, lambda_s=0.1, alpha_max=0.5, ESS/e_min=3.0
local_steps: 2
M_MC: 2000 if the runner needs q_true MC; do not change the U rule
```

Generator (reuse, do not fork a second R definition):

```text
src/raven_mcs/tdrive_protocol_seal_r1/eventtrace_generator.py
  generate_tdrive_complete_aligned_eventtrace(...)
```

`method` argument must not affect the EventTrace hash (already `del method` in that function). Prove it on the micro fixture or on seed 30001 with two dummy method names.

Do not use `generate_complete_aligned_r3` (that is station always-on / INT-R occupancy). Do not copy INT-R Markov occupancy onto taxis.

n_clients ≈ 5867. Event rows are sparse \(R=1\) occupancies, not a dense 5867×178 table. Still large. Smoke before the matrix.

---

## 3. Phase 1 — compute T-Drive φ (no traces required for the statistic)

Same paper rule as `post_review/C2_scd_phi/` and `eq:scd_phi`:

\[
\phi=\frac{\#\{i\in\mathcal{I}_{\mathrm{risk}}^{\mathrm{train}}:\pi_i^{\mathrm{tar}}=0\}}{\#\mathcal{I}_{\mathrm{risk}}^{\mathrm{train}}},\qquad
\mathrm{Design}=\mathrm{ON}\iff\phi=0.
\]

\(\mathcal{I}_{\mathrm{risk}}^{\mathrm{train}}\) = unique `unit_id` with `split=="train"` on processed atomic units (seal: 285659). Do not restrict to units that appear in EventTraces.

T-Drive units are cell×slot, not one client per station. Do **not** invent a K=8 remap. Freeze this operational lookup:

```text
s(i) = str(opportunity_stratum)
Lambda_s^tar = total TEST-split target mass of units with that s
  (uniform over test units, or TargetBuilder atom mass on test; must sum to 1 over test)
π_i^tar = Lambda_{s(i)}^tar
φ_train_unit = mean over train units of [π_i^tar <= 0]
```

Public evaluation \(\boldsymbol\mu\) is H1–H4. Design support is \(s(i)\). Train-only strata get \(\Lambda_s^{\mathrm{tar}}=0\). That is the intended positivity test. Do not build \(\pi^{\mathrm{tar}}\) from processed `target_group` (spatial-coupled). Do not use `pi_target_mode=support_compatible`.

Also report, as diagnostics only (must not flip Design):

- `phi_train_pair`: unique train \(s\) with \(\Lambda_s=0\)
- `phi_train_R`: among train units that appear in `client_measurements` (G3-style train-\(R\) units)
- G3 quoted 44.3% train-\(R\) on train-only strata. If `phi_train_R` is far from that, check \(s(i)\) wiring; do not "fix" it with RMSE.

Grep gate on the φ script: must not contain `rmse`, `y_i`, `test_error`, `support_compatible`, `Gate_t`, `aggregate_coverage`.

Write `results_tdrive_rank/round_v1/TD_R_PHI.json` and `tables/TD_R_PHI.csv` with exact counts. Then freeze:

```text
if phi_train_unit == 0:
    SCD method key = raven          # Design ON, Gate unused
else:
    SCD method key = raven_wo_design  # Design OFF, Gate unused
full_Design diagnostic key = raven  # always trained, even if SCD == raven (then it is a duplicate; skip the duplicate row)
```

If SCD is already `raven`, do not train `raven` twice. If SCD is `raven_wo_design`, train both `raven_wo_design` (SCD) and `raven` (full Design diagnostic).

Do not pick a \(\tau>0\) after seeing φ. The rule is \(\phi=0\) vs \(\phi>0\).

---

## 4. Phase 2 — EventTraces

For each seed in 30001–30010, write:

```text
artifacts/e3_tdrive_rank_eventtraces_v1/tdrive_speed/seed{seed}/training_eventtrace/
```

Shared across methods. Record `trace_hash` in a manifest. Do not put traces inside `tdrive_protocol_seal_r1/`.

Canary: generate seed 30001 first; confirm R occupancy is independent of method name; confirm windows = train slots.

---

## 5. Phase 3 — training matrix

Mandatory methods (Table II comparators). Same backbone, same traces:

```text
fedavg_window
twostage_hajek
fedau_window
obsuse_window
SCD row: raven or raven_wo_design from Phase 1
full Design diagnostic: raven, only if SCD is raven_wo_design
```

Optional if budget remains after the mandatory matrix (do not start these before mandatory finishes):

```text
fedasync_window
flamf_timealign_adapted
```

The seal canary list omitted FedAU/ObsUse. Adding them is required for C1 vs Table II. They consume the same EventTrace. Do not retune them.

Seeds: 30001–30010. Pairing is by seed. Holm / \(+0.5\%\) worst-group non-inferiority vs FedAU and ObsUse is **pre-registered** on this block, same numerical rule as E3, but this table is **not** Table II.

Gate: unused on every T-Drive run (`always_off` / do not call aggregate_coverage as Design). `method_policy.py` still documents Gate on `raven_mcs`. Do not follow that for this round. Use `raven` / `raven_wo_design` as in INT-R.

Evaluation:

- \(\boldsymbol\mu\) and WorstGroupRMSE: **four H1–H4 groups** via `fallback_h_id` in `eventtrace_generator.py` (same function). Do not max over 46082 strata.
- Also report \(\Delta_{\mathrm{group}}\), \(\Delta_{c\text{-}s}\), \(\mathrm{RMSE}_\mu\).
- Scale: follow existing T-Drive processed scaler (train-only). Do not invent a new z-score after seeing test RMSE.

Entry point: adapt `run_e3_real` / INT-R training loop to `tdrive_speed` traces. If `load_paper_dataset` does not know `tdrive_speed`, add a loader that reads processed parquet + sealed H identity. Do not use E9 yaml seeds.

Smoke: seed 30001 `fedavg_window` must finish `REAL_PATH_EXECUTED` before launching the matrix.

---

## 6. What you must not do

- Overlay taxi GPS on SensorScope/U-Air.
- Change SensorScope/U-Air traces, Table II cells, or SS/UA SCD flags.
- Mix T-Drive rows into `tab:main_effectiveness`.
- Use INT-R occupancy traces.
- Use RMSE / \(Y\) / residuals to choose φ, Design, \(p_{\mathrm{obs}}\), horizon, or client subsample.
- Subsample the 5867 clients to "make it like K=8" unless the human later authorizes a **pre-registered** subsample that does not use RMSE. Default is the sealed fleet.
- Call controlled \(O/U\) real.
- Restore `Design_t := Gate_t`.
- Edit `TO_OVERLEAF_paper_tmc_r1_clean/` in this round.
- Run the 50-run future matrix.

---

## 7. Outputs

All under `results_tdrive_rank/round_v1/`:

| File | Content |
| --- | --- |
| `TD_R_PHI.json` | φ counts, SCD freeze, hashes |
| `tables/TD_R_PHI.csv` | one row |
| `TD_R_SCD_FREEZE.json` | method key for SCD and whether full Design is extra |
| `TD_R_TRACE_MANIFEST.json` | seed → trace path and hash |
| `tables/TD_R_E3.csv` | per dataset=tdrive, method, seed: RMSE_μ, WorstGroupRMSE, Δ_group, Δ_c-s |
| `tables/TD_R_E3_SUMMARY.csv` | mean±std over 10 seeds; paired vs FedAU/ObsUse/FedAvg |
| `EXECUTION_LOG.md` | stages, wall time, stop reasons if any |
| `CLAIM_CEILING.md` | copy §1 allowed/forbidden wording |

Do not write manuscript numbers into `main.tex`.

---

## 8. Claim ceiling for a later writing pass (not now)

When numbers exist, a later writer may add a **separate** T-Drive ranking table (likely supplemental, or a short main-text table that is not Table II).

Allowed: hybrid ranking under real taxi \(R\); SCD applied by φ before RMSE; O/U controlled; protocol-MCS remains the SensorScope/U-Air Table II setting.

Forbidden: "we now have a mobile MCS ranking"; promoting INT-R; unlabeled 25.5%; Gate as method; T-Drive RMSE win as the headline.

C1 closes as **moderate residual** if this table exists and is labeled hybrid. It does not become "resolved" in the sense of jointly measured O/U.

---

## 9. Execution order

1. Confirm Python and that processed T-Drive parquet exists; check hashes against `TDRIVE_REAL_MOBILITY_PROTOCOL_MASTER_R1.json` `source_hashes` / processed sha256 fields.
2. Write `scripts/compute_tdrive_phi.py` and `scripts/run_tdrive_rank_v1.py` (or one driver with `--stage`).
3. Phase 1: compute φ; write `TD_R_PHI.json` and `TD_R_SCD_FREEZE.json`.
4. Phase 2: generate traces 30001–30010 into the new trace root; write manifest.
5. Smoke: seed 30001 FedAvg.
6. Train mandatory matrix. If budget dies, stop after canary + φ; do not drop methods to cherry-pick a winner.
7. Summarize CSVs. Do not edit the paper.
8. Stop.

Grep gate on new scripts: no `rmse`/`y_i`/`test_error` in the φ/SCD-freeze path. Training eval may compute RMSE as an **output**, not as a Design input.

---

## 10. Done when

- `TD_R_PHI.json` exists and SCD is frozen from φ=0.
- 10 shared traces exist with method-independent hashes.
- Mandatory matrix CSVs exist, or a documented stop after canary with a hardware reason.
- `tdrive_protocol_seal_r1/` unmodified.
- `main.tex` unmodified.
- Table II unmodified.

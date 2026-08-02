# Formula → Code Map (RAVEN-MCS V2.3)

**Source of truth for experiments:** `RAVEN-MCS_V2.3_Cursor_实验执行指令.txt`  
**Workspace root:** `D:\Cursor\raven.mcs`  
**Status:** P10 end-to-end training integration; 11 deployable methods + 1 external pending.
**Update rule:** When a symbol lands, replace `PLANNED` with `path::symbol` and keep the formula ID stable.

## Pre-E1 seal additions

| Requirement | Implementation | Evidence |
|---|---|---|
| P2 feasibility residuals and fallback | `aggregation/p2_cvxpy.py::solve_p2` | `PRE_E1_SOLVER_AUDIT.json` |
| `U=1 => tau<=S_max` | `simulation/event_trace.py::EventTrace.validate` | `PRE_E1_TIME_STALENESS_AUDIT.json` |
| Registration-time deadline slack | `propensity/usable.py::deadline_slack_pre` | `DATA_DICTIONARY.md`, q audit |

## E1 official-entry closure

| Requirement | Implementation | Evidence |
|---|---|---|
| Frozen SensorScope G=4 main groups | `experiments/e1_entry.py::add_e1_groups` | run manifests, prediction rows |
| Real-ID balanced EventTrace family | `experiments/e1_entry.py::generate_balanced_trace` | five trace manifests/audits |
| Official atomic target/arrival risk | `experiments/e1_entry.py::_arrival_weights` | `arrival_weights_test.parquet` |
| Per-seed aggregation | `scripts/aggregate_results.py::aggregate` | `per_seed_metrics.parquet` |
| Validation-only baseline | `scripts/select_e1_baseline.py::choose_baseline` | `e1_selected_baseline.yaml` |
| No-harm degradation dry-run | `scripts/statistical_tests.py` | `no_harm_summary.json` |

---

## 1. Atomic units, strata, targets

| ID | Symbol / definition | Planned code | Notes / bans |
|----|---------------------|--------------|--------------|
| F1.1 | Atomic unit `i = (n, t)` | **STRUCTURAL:** `data/schema.py::atomic_units_arrow_schema`, `normalize_atomic_units` | Canonical representation only; target/opportunity formula logic is not implemented |
| F1.2 | Opportunity stratum `s(i)` | **IMPLEMENTED:** `opportunities/strata.py::OpportunityStrataMapper` | Coarse region × ToD × weekday/weekend |
| F1.3 | Target group `h(i)` | **IMPLEMENTED:** `data/target.py::GroupMapper` | Eval spatial × target time block |
| F1.4 | `Ŷ_i = f_θ(i; C_i^dep)` | **IMPLEMENTED:** `models/common_ndmf.py::CommonNDMF` | **Ban:** client_id embedding |
| F1.5 | `ϖ_i^tar = μ_{h(i)} · ν_{i\|h(i)}^tar` | **IMPLEMENTED:** `data/target.py::TargetBuilder` | Nonnegative + normalize |
| F1.6 | `π_{k,s}^tar = Λ_s^tar · λ_{k\|s}^tar` | **IMPLEMENTED:** `data/target.py::client_stratum_mass` | Controlled λ |
| F1.7 | `π_{k,i}^tar = π_{k,s(i)}^tar · ν_{i\|s(i)}^tar` | **IMPLEMENTED:** `data/target.py::client_atom_mass` | |

---

## 2. Windows and selection

| ID | Symbol / definition | Planned code | Notes / bans |
|----|---------------------|--------------|--------------|
| F2.1 | Window `W_r = [T_r, T_{r+1})` | **IMPLEMENTED:** `training/window_timing.py` + `training/window_runner.py` | θ frozen + one update; G2 |
| F2.2 | Risk set `R_{k,r}` before outcomes | `simulation/observation_generator.py` | Pre-outcome |
| F2.3 | `O`, `p_obs = P(O=1 \| X_obs, hist)` | `propensity/observation.py` | **Ban:** Y, current error, future in `X_obs` |
| F2.4 | `E_r = {k : buffer ≠ ∅}` | `simulation/event_trace.py` | Register before usable outcome |
| F2.5 | `U_{k,r}` usable indicator | `simulation/usable_generator.py` | Keep U=0; never drop |
| F2.6 | `q` usable propensity | `propensity/usable.py` + **IMPLEMENTED ban scan:** `propensity/leakage.py` | E0.6 forbids banned feature names; full q model later |
| F2.7 | Usable set `A_r ⊆ E_r` | `training/window_runner.py` | |

---

## 3. Design ratio and stage-1 correction

| ID | Symbol / definition | Planned code | Notes |
|----|---------------------|--------------|-------|
| F3.1 | General `ζ^o_{k,r,i}` | `correction/design_ratio.py` | Full two-factor form |
| F3.2 | Main: `ζ̂_{k,r,s} = π^tar_{k,s} / max(π̂^opp_{k,s,r}, π_min)` | **IMPLEMENTED:** `correction/design_ratio.py::zeta_hat_stratum` | Within-stratum exchangeability default; E0.1 |
| F3.3 | EMA `C^opp`, `π̂^opp` | **IMPLEMENTED:** `opportunities/estimator.py::OpportunityEstimator` | **Lagged** only; forgetting `ρ_opp` |
| F3.4 | `a = min{a_max, ζ̂ / max(p̂_obs, p_min)}` | **IMPLEMENTED:** `correction/hajek.py::raw_weights` | E0.1 |
| F3.5 | `m_{k,r,g} = Σ_i O a 1{h(i)=g}` | **IMPLEMENTED:** `correction/hajek.py::group_mass` | E0.1 |
| F3.6 | `m_{k,r} = Σ_g m_{k,r,g}` | **IMPLEMENTED:** `correction/hajek.py::total_mass` | Target-equivalent mass — **≠** ESS |
| F3.7 | Hájek `ā = O a / m` | **IMPLEMENTED:** `correction/hajek.py::normalized_weights` | E0.1 |
| F3.8 | `c_{k,r,g} = m_{k,r,g} / m_{k,r}` | **IMPLEMENTED:** `correction/hajek.py::composition` | E0.1 |
| F3.9 | `n_eff = m² / Σ(O a)² = 1/Σ ā²` | **IMPLEMENTED:** `correction/effective_sample_size.py::effective_sample_size` | Dual-identity check; E0.1 |

---

## 4. Local objective and normalized update

| ID | Symbol / definition | Planned code |
|----|---------------------|--------------|
| F4.1 | `F̂^H = Σ_i ā · ½ (f_θ − Z)²` | `training/client.py::local_objective` |
| F4.2 | `u = (θ_s − θ^{(E_loc)}) / (γ_r E_loc)` | `training/client.py::normalized_update` |

---

## 5. Lagged variance and stage-2

| ID | Symbol / definition | Planned code | Notes |
|----|---------------------|--------------|-------|
| F5.1 | `v = S̄²_{r⁻} / max(n_eff,1) + v_floor` | `metrics/variance.py` + aggregator state | Current-window var → **next** window only |
| F5.2 | `d = min{d_max, 1/max(q̂, q_min)}` | **IMPLEMENTED:** `correction/second_stage.py::d_weight` | E0.1 |
| F5.3 | `b = m · d` | **IMPLEMENTED:** `correction/second_stage.py::two_stage_mass` | E0.1 |
| F5.4 | `β̂ = b / Σ_{j∈A_r} b_j` | **IMPLEMENTED:** `correction/second_stage.py::beta_hat` | β≥0, Σβ=1; E0.1 |

---

## 6. Target debt and P2

| ID | Symbol / definition | Planned code | Notes / bans |
|----|---------------------|--------------|--------------|
| F6.1 | `M_r = [c_{k,r}]_{k∈A_r}` | **IMPLEMENTED:** `aggregation/debt.py`, `window_runner.py` P2 inputs | Composition from records (P10), not workload softmax |
| F6.2 | `ω_r = M_r α_r` | **IMPLEMENTED:** `aggregation/debt.py::coverage_mix` | E0.4 |
| F6.3 | `Q_{r+1} = [Q_r + η_r(μ − ω_r)]_+` | **IMPLEMENTED:** `aggregation/debt.py::update_debt` | Empty window: no θ/Q update; E0.4 |
| F6.4 | P2: `−QᵀMα + (λ_g/2)‖Mα−μ‖² + (λ_β/2)‖α−β̂‖² + (λ_v/2)αᵀVα + λ_s τ̄ᵀα` | **IMPLEMENTED:** `aggregation/p2_cvxpy.py::solve_p2` | Convex; CLARABEL primary; E0.3 |
| F6.5 | `1ᵀα=1`, `0≤α≤ᾱ`, `‖α‖₂²≤1/Ē` | **IMPLEMENTED:** `aggregation/feasibility.py` | `ᾱ=min(1,max(α_max,1/K))`; `Ē=min(E_min,K)` |
| F6.6 | `λ_β>0`, `λ_g ≥ max_server_lr` | **IMPLEMENTED:** `utils/validation.py` + `aggregation/feasibility.py::validate_p2_lambdas` | E0.3 |
| F6.7 | **Ban:** P2 uses current `u` coords/norm/dir for own weight | **IMPLEMENTED:** `solve_p2` has no `u` argument; guarded in E0.3 | α then aggregate |
| F6.8 | `θ_{r+1} = θ_r − η_r Σ α_k u_k` | **IMPLEMENTED:** `training/window_runner.py::FullWindowRunner` | One update per active window; P10 |

---

## 7. Theory diagnostics

| ID | Symbol | Planned code |
|----|--------|--------------|
| F7.1 | Effective pair `Π̂` | `metrics/distribution.py` |
| F7.2 | RAVEN: `w=ā` | same |
| F7.3 | `Δ_group = ‖ω̂−μ‖_1` | same |
| F7.4 | `Δ_pair = ‖Π̂−π^tar‖_1` | same |
| F7.5 | `Δ_{c-s}` | same (esp. T-Drive) |
| F7.6 | `avg_δ_group`, `avg_δ_ref` | same |
| F7.7 | `debt_normalized = ‖Q_R‖_1/S_R` | **IMPLEMENTED:** `metrics/debt.py::debt_normalized` | E0.4 |
| F7.8 | Prefix: `‖ω̄_r−μ‖_1 ≤ 2‖Q_r‖_1/S_r` (tol 1e-8) | **IMPLEMENTED:** `metrics/debt.py::prefix_debt_bound_holds` | E0.4; full G5 later |
| F7.9 | True `ε_reach(B)` via CVXPY | **IMPLEMENTED:** `metrics/reachability_optimization.py::solve_epsilon_reach` | P10; renamed from old epsilon_reach |
| F7.10 | Realized deviation (formerly ε_reach) | **IMPLEMENTED:** `metrics/reachability.py::realized_block_group_deviation` | P10 rename |
| F7.11 | Tail/Head RMSE via R_g = rho_g/mu_g | **IMPLEMENTED:** `metrics/accuracy.py::tail_head_rmse` | P10; replaces prediction-error-based tail |

---

## 8. Risks and RMSE

| ID | Symbol | Planned code | Notes |
|----|--------|--------------|-------|
| F8.1 | `RMSE_μ` with `ϖ̃^tar` | `metrics/accuracy.py` | |
| F8.2 | `RMSE_ρ` with **atomic** `ρ̃^arr` | `metrics/accuracy.py` | **Ban:** group-level arrival substitute |
| F8.3 | `r̂^arr_i = Σ_k π̂^opp ν̂^opp p̂ q̂` then normalize | `metrics/accuracy.py::arrival_intensity` | Frozen models |
| F8.4 | `Gap_mis = RMSE_μ − RMSE_ρ` | `metrics/accuracy.py` | |

---

## 9. Client measurement (controlled)

| ID | Symbol | Planned code |
|----|--------|--------------|
| F9.1 | `Z* = Y + b + ε` | `data/*` generators |
| F9.2 | noise `0.05·train_std`; bias ratios `{0,0.1,0.2,0.4}`; main `Δ_cal=0` | scenario configs |

---

## 10. Method → formula usage (P10-C semantics)

| Method | ζ/p (ā,m) | q/d/β | Inst. P2 | Debt Q | Client Embed | Status |
|--------|-----------|-------|----------|--------|-------------|--------|
| Central-All | — | — | — | — | No | True centralized training only |
| Central-Delivered | — | — | — | — | No | True centralized training only |
| FedAvg-Window | raw counts | — | — | — | No | Deployable |
| FedAsync-Window | raw·e^{−κτ} | — | — | — | No | Deployable |
| TimeAlign-Agg | — | — | stale align | — | No | Deployable |
| Local-Hajek | ✓ | — | — | — | No | Deployable |
| TwoStage-Hajek | ✓ | ✓ α=β̂ | — | — | No | Deployable |
| Inst-Cal | ✓ | ✓ | full; Q≡0 | — | No | Deployable (P10 fix) |
| Debt-Cal | raw c | — | group+debt | ✓ | No | Deployable (P10 fix) |
| RAVEN-MCS | ✓ | ✓ | full | ✓ | No | Deployable |
| RAVEN-SimOracle | oracle ζ/p + MC q | ✓ | full | ✓ | No | Deployable |
| FLAMF-Original | — | — | — | — | — | EXTERNAL_BASELINE_NOT_INTEGRATED |

---

## 11. Hard-gate ↔ formula checklist

| Gate | Focus |
|------|--------|
| G0 | Phase 2B: `scripts/check_g0_data.py` + frozen `sensorscope`/`uair`/`traffic`/`tdrive_speed`; Traffic preferred ≥60 stations not met (43×720) but hard floor passed |
| G1 | **PASS:** `simulation/event_trace.py` + `scripts/check_hard_gates.py` |
| G2 | **PASS:** WindowRunner frozen θ + one update |
| G3 | **PASS:** Hájek/ESS/β identities |
| G4 | **PASS:** CVXPY P2 constraints |
| G5 | **PASS:** debt prefix bound on runner path |
| G6 | Balanced no-harm (empirical) |
| G7 | SimOracle ordering on ζ/p/q error and Δ_pair / Δ_{c-s} |

---

## 12. Leakage keyword denylist (E0.6)

Forbid in `q` / usable feature names:  
`realized`, `arrival`, `future`, `update_norm`, `update_value`, `actual_delay`

---

## 13. Maintenance

After each implementing phase: mark IDs IMPLEMENTED, link unit tests, record teacher-approved deviations only in `ISSUES.md`.

---

## 14. P10 additions

| ID | Symbol / definition | Code | Notes |
|----|---------------------|------|-------|
| P10.1 | `AtomicUnit`, `ClientMeasurement` dataclasses | `data/processed_dataset.py::ProcessedDataset` | Train/val/test no overlap; scaler fit on train only |
| P10.2 | Per-window data extraction | `data/window_dataset.py::extract_window_slice` | |
| P10.3 | Feature extraction for Common-NDMF | `models/features.py::extract_features` | |
| P10.4 | ClientTrainer with local Hájek SGD | `training/client.py::ClientTrainer` | No client_id feature |
| P10.5 | `F̂^H` local objective | `training/local_objective.py::local_hajek_loss` | |
| P10.6 | MethodPolicy | `aggregation/method_policy.py::MethodPolicy` | Declarative capability flags |
| P10.7 | Full training WindowRunner | `training/window_runner.py::FullWindowRunner` | 12-step window pipeline |
| P10.8 | Tail/Head via R_g ratio | `metrics/accuracy.py::tail_head_rmse` | |
| P10.9 | True ε_reach CVXPY | `metrics/reachability_optimization.py::solve_epsilon_reach` | |
| P10.10 | Realized deviation rename | `metrics/reachability.py::realized_block_group_deviation` | Formerly epsilon_reach |
| P10.11 | Frozen config gate | `scripts/freeze_config.py` | SHA256 hash + test-entry gate |
| P10.12 | Real-data-only trace loading | `scripts/run_experiment.py::_get_or_generate_trace` | FileNotFoundError for real datasets |
| P10.13 | Statistical tests from real results | `scripts/statistical_tests.py` | No random example data |
| P10.14 | Observation diagnostics | `propensity/observation.py::ObservationPropensityDiagnostics` | Brier, log loss, ECE |
| P10.15 | Zeta diagnostics | `correction/design_ratio.py::compute_zeta_with_diagnostics` | Support flag, drift L1 |

## 15. E1-ENTRY-R1 semantic closure

| Definition | Code | Audit identity |
|---|---|---|
| Repeatable UTC G=4 | `RepeatableTimeOfDayMapper` | `e1_sensorscope_groups.yaml` |
| Client measurement \(Z^*_{k,i}\) | `ProcessedDataset.get_potential_measurement` | `(client_id, unit_id)`; no Y fallback |
| Pre-outcome \(\hat p\) | `ObservationPropensity.feature_names` | `p_feature_whitelist.yaml` |
| \(\pi^{tar}_{k,s}=\Lambda_s^{tar}\lambda_{k\mid s}^{tar}\) | `correction/pi_target.py` | frozen parquet + SHA-256 |
| \(v_{k,r}=S^2_{k,r^-}/\max(n_{eff},1)+v_{floor}\) | `FullWindowRunner` | state updated after close |
| \(\bar\tau=\tau/S_{max}\) | `FullWindowRunner._process_window` | raw and normalized τ diagnostics |
| FLAMF-TimeAlign-Adapted \(s_k=\sum_{t\in T_k}1/c_t\) | `FLAMFTimeAlignAdaptedAggregator` | teacher-frozen common-backbone adaptation |
| Record-level p history | `ObservationPropensity.update_records_after_completion` | one row per `(client, window, unit)` after close |
| Arrival-risk planned workload | `e1_entry._arrival_weights` | frozen train history; no raw observed count |

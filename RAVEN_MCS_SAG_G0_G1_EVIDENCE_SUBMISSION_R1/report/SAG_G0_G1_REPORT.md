# SAG G0/G1 Report

# 1. Executive Verdict
REPAIR

This is a G1 5-seed **rerun** on the same frozen G0 code, thresholds, EventTraces, and seeds (30001–30005). Numbers match the first G1 pass (deterministic). Previous files are in `outputs/sag_g1/archive_rerun_20260829-122556/`.

G0 implementation audit passed. SAG is **identically No-Design** (Gate never ON). Do **not** expand to 10 seeds, E1–E5, or T-Drive.

# 2. G0 Implementation Audit
G0 full verdict: **PASS** (SensorScope + U-Air, seeds 30001–30003, sealed E3 EventTraces).

| Check | Result |
|---|---|
| timing correct? | PASS |
| p_obs frozen before O? | PASS |
| q_use frozen before U? | PASS |
| B_r / A_r correct? | PASS |
| shared EventTrace? | PASS |
| no dataset-name Gate? | PASS |
| no forbidden Gate feature? | PASS |
| counterfactual audit valid? | PASS |
| No-Design ζ̃=1 with IPW/P2/V/staleness/Debt on? | PASS |

# 3. Gate Behavior

SAG mean ON rate: **0.000** (900 SAG windows; 0 ON).

| dataset | OFF_COLD_START | OFF_LOW_COVERAGE | ON |
|---|---:|---:|---:|
| SensorScope | 40 | 460 | 0 |
| U-Air | 40 | 360 | 0 |

Always-Design false-enable (`active_set_mismatch==1` among G=1 windows):

- SensorScope: **0.00**
- U-Air: **0.46–0.59**

SAG false-enable: **0.00** because it never enables.

Comparison A still shows the old boundary: SensorScope Design is slightly better structurally; U-Air Always-D raises RMSE / WorstGroupRMSE and damages the active set.

# 4. Certificate Calibration

Joint coverage of (Δβ, ΔM, ΔV) on common nonempty A^D=A^0:

- SensorScope: 0.89–0.94
- U-Air: 0.76–0.97 (seed 30003 = 0.76)

Mean joint coverage is below the 0.90 development floor. Dominant OFF cause is `C_cov_LCB < τ_cov`: realized C_cov is the fraction of all π^tar>0 pairs that appear in this window’s R, which stays far below 0.05.

# 5. Prediction Safety

SAG ≡ No-Design on every seed.

- mean relative RMSE harm vs No-D: **0.000** (budget 0.5%)
- mean relative WorstGroup harm vs No-D: **0.000**

# 6. Structural Utility

- mean `gain_group` = **0**
- mean `gain_cs` = **0**
- `NAG_NOT_AVAILABLE_IN_G1`

# 7. Failure Analysis

After 8-window cold start, remaining windows are all `OFF_LOW_COVERAGE`. U-Air Always-D mismatch is ~50%. SAG avoids those windows by never turning ON, including on SensorScope-compatible windows.

# 8. Go/Repair/Stop Decision

| Gate | Result | Note |
|---|---|---|
| Gate-1 Predictability | PASS | G0 full PASS |
| Gate-2 Certificate | FAIL | joint coverage < 0.90; C_cov unusable |
| Gate-3 Safety | PASS | SAG false-enable < Always-D |
| Gate-4 Prediction | PASS | harm 0.0 vs No-D |
| Gate-5 Utility | FAIL | ON rate 0; degenerates to Always-No-Design |

**Decision: REPAIR**

Do not retune τ after seeing G1. Next work only after you confirm: repair `C_cov` to an F_{r-}-measurable opportunity-probability LCB on S_tar, then rerun G0 smoke/full + G1 5-seed.

# 9. Files Produced

- `outputs/sag_g1/SAG_G0_G1_REPORT.md`
- `outputs/sag_g1/G1_VERDICT.json`
- `outputs/sag_g1/G1_METHOD_SUMMARY.csv`
- `outputs/sag_g1/G1_GATE_WINDOW_LOG.csv`
- `outputs/sag_g1/G1_CERTIFICATE_COVERAGE.csv`
- `outputs/sag_g1/G1_PREDICTION_SAFETY.csv`
- `outputs/sag_g1/G1_STRUCTURAL_GAIN.csv`
- `outputs/sag_g1/configs/config_g1_5seed.json`
- previous run: `outputs/sag_g1/archive_rerun_20260829-122556/`

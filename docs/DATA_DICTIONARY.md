# DATA_DICTIONARY — RAVEN-MCS V2.3 Phase 2B

Canonical processed tables live under `data/processed/<dataset>/`.
Raw provenance is recorded in `data/raw/<dataset>/provenance.json`.

## Pre-E1 q-model information boundary

`deadline_slack_pre` is defined at registration time as:

```text
deadline_slack_pre = window_close_time - registration_time
```

It is available before local compute and network transfer. It does not use
actual completion time, actual network duration, actual arrival time, current
update/vector/norm, current loss improvement, or post-window information.

## E1-R1 p-model information boundary

The frozen observation-propensity vector is
`(bias, hour_block, planned_workload_pre)`. The intercept and repeatable
time-of-day block are available when the risk set forms.
`planned_workload_pre` is the number of scheduled risk-set units before O is
realized. No feature uses the current O outcome. `raw_workload`,
`observed_count`, `len(observed)`, and current successful-measurement counts
are forbidden.

Local training labels are looked up exclusively as
`client_measurements[(client_id, unit_id)].potential_measurement`.
`atomic_units.target_value` is reserved for evaluation.

The formal arrival-risk reconstruction uses the same pre-outcome feature
boundary and only frozen train EventTrace history. Observation-propensity
history is persisted one row per risk record after window close, with
`prediction_time`, `update_time`, p-model version and source split. Current O
is never used for its own prediction.

## Shared processed schema

### `atomic_units.parquet`

| Column | Type | Meaning |
|--------|------|---------|
| `unit_id` | string | Atomic spatial×time unit id |
| `spatial_id` | string | Station / grid cell id |
| `absolute_time` | timestamp[ns, UTC] | Slot start time |
| `time_index` | int64 | Dense index over selected timeline |
| `target_value` | float64 | Public field value \(Y\) |
| `split` | string | `train` / `validation` / `test` (temporal) |
| `target_group` | string | Spatial×time-block grouping |
| `opportunity_stratum` | string | Opportunity stratum label |
| `public_features` | JSON string | Public covariates (time-of-day, etc.) |
| `support_flag` | bool | Whether the unit is supported |
| `is_warmup` | bool | First 20% of train slots |

### `client_measurements.parquet`

| Column | Type | Meaning |
|--------|------|---------|
| `client_id` | string | Client / vehicle identity |
| `unit_id` | string | Joins to atomic unit |
| `potential_measurement` | float64 | Potential observation \(Z^*\) |
| `controlled_generator_parameters` | JSON/null | Controlled \(Z^*=Y+b+\varepsilon\) params |
| `split` | string | Copied from atomic unit |
| `source_trace_id` | string | Raw-record provenance id |

**Hard rule:** `target_source_trace_ids` and client `source_trace_id` are disjoint.

## Dataset-specific notes

### SensorScope (`sensorscope`)

- **Source:** Zenodo `https://zenodo.org/records/2654726` (`Sensorscope.zip`, md5 `4bbed2bbd48e535bc2877cad339fbbd6`)
- **Target:** ambient temperature (°C) from nested Luce/meteo station packs
- **Filters:** drop non-finite; keep \([-40, 60]\) °C; dense window toward ~55×312 hours
- **Clients:** controlled generator from public \(Y\)

### U-Air (`uair`)

- **Source:** MSR Urban Air page; artifact `Data-1.zip` (`Data/airquality.csv`)
- **Target:** `PM25_Concentration` (µg/m³)
- **Filters:** drop non-finite; keep \([0, 1000]\); dense window toward ~36×264
- **Substitution ban:** UCI Beijing / other proxies are forbidden

### NSW Traffic (`traffic`)

- **Source:** TfNSW Open Data Hub station reference CSV + hourly permanent zip
- **Target:** hourly traffic volume (vehicles/hour); wide `hour_00`…`hour_23` melted
- **Quality:** `data/raw/traffic/station_quality_report.csv` required
- **Hard floor:** ≥30 stations × 336 continuous hours (prefer ≥60×720)
- **Substitution ban:** PEMS-BAY only with teacher approval

### T-Drive-Speed (`tdrive_speed`)

- **Source:** MSR T-Drive trajectory sample zips (`06.zip`…`014.zip`)
- **Grid:** 500 m cells; slot length frozen at 30 minutes (validation)
- **Fleet:** stratified 30% reference / 70% client by trajectory length (`fleet_assignments.parquet`)
- **Target \(Y\):** mean speed in cell×slot from **reference** fleet only
- **Clients:** measurements from **client** fleet only
- **Filters:** drop speeds `<5` or `>120` km/h; gaps `>15` minutes ignored for speed

## Interim artifacts

| Path | Purpose |
|------|---------|
| `interim/<ds>/audit_report.json` | Schema/split/anomaly audit |
| `interim/<ds>/scaling.json` | Train-only standardizer stats |
| `interim/<ds>/metadata.json` | Dataset metadata |
| `interim/<ds>/physical_anomalies.parquet` | Dropped/recorded anomalies |
| `interim/<ds>/target_source_trace_ids.parquet` | Target provenance set |
| `interim/<ds>/fleet_assignments.parquet` | T-Drive fleet labels |
| `manifests/<ds>_manifest.json` | Frozen hashes |

# E1 Target Hash Semantics

Field names must not alias distinct payloads.

## `atomic_target_weight_hash`

- Object: ordered atomic test-unit target weights from `TargetBuilder`
- Columns: `unit_id`, `target_weight`
- Canonical records are sorted by `unit_id`
- Produced by `scripts/freeze_e1_pi_target.py` and
  `scripts/recompute_e1_delta_cal.py` (calibration residual audit)

## `client_stratum_target_mass_hash`

- Object: ordered client × opportunity-stratum target mass
- Columns: `client_id`, `opportunity_stratum`, `pi_k_s_tar`
- Source: `configs/frozen/e1_pi_target_client_stratum.parquet`
- Recorded in `configs/frozen/e1_pi_target_manifest.json` and run manifests

## Protocol hashes

- `protocol_file_hash`: SHA-256 of checkout bytes for
  `configs/frozen/e1_r2_protocol.yaml`
- `protocol_payload_hash`: SHA-256 of the normalized YAML object
  (canonical JSON). This remains the primary protocol identity.

Use `.gitattributes` LF rules so checkout bytes are stable across platforms.
Coordinate any `git add --renormalize` via `scripts/renormalize_text_eol_lf.py`.

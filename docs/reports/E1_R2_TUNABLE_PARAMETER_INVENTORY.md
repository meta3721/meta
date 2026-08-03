# E1 R2 Tunable Parameter Inventory

## Scope

This inventory governs `E1-R2-PROTOCOL-CALIBRATION-R1`. R2 addresses the
first-stage weight-cap failure retained from E1 R1. It does not authorize an
algorithm change, formal-data tuning, seed substitution, or formal training.

## Registered candidate space

`a_max` is the only tunable parameter:

| Candidate | `a_max` |
|---|---:|
| C0 | 20 |
| C1 | 30 |
| C2 | 40 |
| C3 | 60 |

The complete candidate set is written to
`configs/e1_r2/candidate_registry.yaml`. Its
`candidate_registry_hash` is computed over the canonical registry payload,
excluding only the hash field itself. The registry is a pre-run artifact and
the builder refuses to replace a different existing registry.

## Frozen parameters

The following correction parameters are not tunable in R2:

| Parameter | Frozen value | R2 status |
|---|---:|---|
| `p_min` | 0.05 | frozen |
| `pi_min` | 1e-6 | frozen |
| `d_max` | 10 | frozen |
| `q_min` | 0.05 | frozen |

`opportunity_forgetting=0.95` is unchanged and informational. It is recorded
for traceability but is not a candidate dimension and cannot participate in
selection.

All other E1 protocol, dataset, grouping, client mapping, target-mass,
training, method, and gate settings remain outside the R2 candidate space.

## Data roles and access

The role-separated, 100-window structural traces are:

- calibration: seeds 27001, 27002, 27003, 27004, 27005;
- validation: seeds 27101, 27102, 27103, 27104, 27105;
- formal: seeds 28001, 28002, 28003, 28004, 28005.

Candidate evaluation and selection may use calibration data only. Validation
is reserved for the separately authorized validation step. Formal traces may
be generated, frozen, hashed, and structurally audited, but formal outcomes
must not be evaluated and no formal training is authorized by this
foundation. Each trace records `candidate_assignment: null` because trace
identity is independent of candidate selection.

## R1 closure

The R1 archive is evidentiary, not a retry. Its fixed final status is
`FAILED_WEIGHT_SAFETY`: one formal run completed, none was admitted,
E1-RUN-G6 failed, no retuning occurred in R1, no remaining formal run started,
and E2-E9 remain not started. Source evidence is copied without modification
and the archive records SHA-256 hashes for every archived file.

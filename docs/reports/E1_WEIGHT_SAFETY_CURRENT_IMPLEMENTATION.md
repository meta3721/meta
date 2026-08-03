# E1 Weight-Safety Current Implementation Audit

## Frozen failed run

`outputs/runs/E1_FORMAL_fedavg_window_26001_20260802_154112_605315`

## Code path and exact current definition

1. `src/raven_mcs/training/window_runner.py`, `_process_window`,
   lines 267–314 computes `a_raw = min(a_max, zeta / max(p_hat, p_min))`.
   `a_raw` is already capped.  The record-level indicator is
   `I(abs(a_raw) >= a_max)` at line 313.  Therefore equality with the cap is
   counted, with no explicit epsilon.
2. Lines 316–325 form `E_r`: clients with positive corrected mass, and assert
   that it equals the frozen attempted-client set.  Lines 572–574 take the
   unweighted mean of the client proportions across `E_r`.
3. `src/raven_mcs/experiments/e1_entry.py`, lines 952–980 writes
   `metrics_run.json`; line 973 takes the unweighted mean of
   `clip_rate_stage1` across active windows only.
4. `scripts/check_e1_run_gates.py`, lines 51–55 applies the `<= 0.05` gate to
   that reported scalar.

Let `R_{kr}` be all risk records for attempted client `k` in active window
`r`, `a_{kri}=min(a_max, u_{kri})`, and `u_{kri}=zeta_{kri}/max(p_hat,p_min)`.
The current implementation is:

`c_current = mean_{r in W_active} mean_{k in E_r} [ |R_kr|^-1 sum_i I(|a_kri| >= a_max) ]`.

It is a client-window macro average, not a global risk-record micro average.
All risk records are included in a client denominator, including unobserved
records. Empty/inactive windows return zero locally but are excluded from the
final mean. `E_r` is attempted clients; nonattempted clients are absent.
The calculation has no NaN-specific branch: normal NumPy `mean` semantics
apply, and the persisted formal run has finite vectors.

## Equality distinction for DIAG-R1

The diagnostic reconstruction uses frozen `eps_clip=1e-12`:

- true exceed: `u > a_max + eps_clip`
- exact boundary: `abs(u-a_max) <= eps_clip`
- at-or-above: `u >= a_max - eps_clip`

The historic metric uses the third interpretation operationally (`>=` on the
capped weight) and does not distinguish the first two.  The diagnostic retains
the old value and reports all three definitions; it never rewrites the run.

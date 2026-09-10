# Claim ceiling — TD-R-E3 (copy into round outputs)

## Allowed

- Method ranking under real taxi opportunity \(R\) (trajectory occupancy).
- \(O\) and \(U\) remain Complete-aligned controls (\(p_{\mathrm{obs}}=0.35\), `compute_usable_r3`, \(s_{\max}=5\)). Never call them real sensor or network logs.
- SCD: \(\mathrm{Design}=\mathrm{ON}\) iff \(\phi=0\), frozen before RMSE.
- SensorScope / U-Air Table II remains protocol MCS (station arrays). This block does not give those cities mobile clients.

## Forbidden

- End-to-end mobile MCS; jointly measured \(R/O/U\); real federated updates.
- Mixing T-Drive rows into Table II.
- Overlaying T-Drive GPS onto SensorScope / U-Air.
- INT-R occupancy as this experiment.
- Gate as the Design switch.
- T-Drive RMSE dominance as the headline for C1.
- "We now have a mobile MCS ranking."

# FLAMF-TimeAlign-Adapted

## Name and source boundary

The frozen baseline name is **FLAMF-TimeAlign-Adapted**. It is a
common-backbone adaptation of FLAMF-style timestamp-aligned asynchronous
aggregation. The project sources define only the source semantics, not an
original executable FLAMF formula. The formula below is the teacher-frozen
RAVEN-MCS adaptation.

It is not the original FLAMF implementation, an exact reproduction of FLAMF,
or an official TimeAlign implementation.

## Frozen formula

For usable clients \(A_r\), let \(T_{k,r}\) be client \(k\)'s set of frozen
discrete sensing slots represented by its observed atomic units. Define

\[
c_{r,t}=\sum_{j\in A_r}\mathbf{1}\{t\in T_{j,r}\},\qquad
s^{TA}_{k,r}=\sum_{t\in T_{k,r}}\frac{1}{c_{r,t}},
\]

\[
\alpha^{TA}_{k,r}=
\frac{s^{TA}_{k,r}}{\sum_{j\in A_r}s^{TA}_{j,r}}.
\]

Duplicate observations of a slot within one client are collapsed before
credit calculation.

## Time-slot definition

`time_slot_id` is `atomic_units.time_index`, the frozen discrete sensing slot.
Server arrival time, completion time, network delay, model version and
staleness `tau` are forbidden as coverage-slot definitions.

## Difference from FedAsync

FedAsync uses sample size and model staleness:
`alpha proportional to n * exp(-kappa_tau * tau)`.
FLAMF-TimeAlign-Adapted uses only temporal coverage overlap. It contains no
exponential staleness formula and is invariant to tau when coverage is fixed.

## Boundary behavior

- Empty usable set: WindowRunner performs no update.
- Empty \(T_{k,r}\): client credit is zero.
- Zero total credit: explicit run failure; no FedAvg/FedAsync fallback.

## Complexity

With \(M=\sum_k |T_{k,r}|\), construction and normalization are \(O(M)\) time
and \(O(|\cup_k T_{k,r}|+|A_r|)\) memory.

## Frozen parameters

There are no tunable aggregation parameters. Set semantics, slot identity,
zero-credit failure and normalization are frozen.

## Applicability and permitted wording

This baseline is valid only with the shared Common-NDMF model, local-training
protocol, frozen EventTrace and evaluation backbone.

Permitted paper wording:
“a common-backbone adaptation of FLAMF-style timestamp-aligned asynchronous
aggregation.”

Forbidden wording:
“the original FLAMF implementation,” “exact reproduction of FLAMF,” and
“official TimeAlign implementation.”

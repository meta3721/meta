RAVEN-MCS v2.0 — Cursor Handoff README
======================================

IMPORTANT: Read this file before changing or running any code.

This package contains the CURRENT authoritative theory and experiment instructions.
Do NOT rely on older RAVEN-MCS manuscript code comments, old dataset-gated logic,
or prior Sections III--VI if they conflict with the files below.

AUTHORITATIVE ORDER
-------------------

1. RAVEN_MCS_Support_Aware_Gate_Spec_v1.2_Final_Closure.txt
   Role:
   - final SAG theory specification;
   - authoritative definitions of predictability, A8a/A8b/A9,
     Theorems 2--4, B_tot, and Gate safety semantics.

2. RAVEN_MCS_v2_Sections_III_VI_PostAudit_Final.txt
   Role:
   - CURRENT paper technical master for Sections III--VI;
   - supersedes all earlier Sections III--VI;
   - contains the post-audit fixes for:
       * event-mark opportunity law vs R indicator semantics;
       * pre-U set B_r and post-U set A_r;
       * p_obs freeze before O;
       * q_use freeze before U;
       * both-empty common-set handling;
       * B_M^cf vs B_M^pre;
       * updated Theorems 2--4 and Algorithm 1 ordering.

3. RAVEN_MCS_Cursor_SAG_G0_G1_Experiment_Instruction_v1.0.txt
   Role:
   - implementation and experiment execution instructions;
   - execute only after understanding Files 1 and 2.

NON-NEGOTIABLE AUTHORITY RULE
-----------------------------

If the existing code, old experiment scripts, old manuscript text, or comments
conflict with the current Sections III--VI, use:

  Final SAG Spec v1.2
      ->
  Sections III--VI PostAudit Final
      ->
  Cursor G0/G1 Experiment Instruction

in that order.

DO NOT IMPLEMENT THE OLD DATASET-LEVEL GATE.

The current Gate must be predictable and computed before current-window R/O/U.
Do not use dataset identity to select Design ON/OFF.

MANDATORY CURRENT WINDOW ORDER
------------------------------

completed history
  ->
predictable SAG certificates
  ->
freeze G_r
  ->
realize R
  ->
freeze p_hat_obs from legal pre-O history
  ->
realize O
  ->
form E_r
  ->
form B_r = {k in E_r : m_{k,r} > 0}
  ->
local weights/compositions/n_eff and local training
  ->
freeze q_hat_use from legal pre-U history
  ->
realize U
  ->
A_r = B_r cap U_r
  ->
usable correction
  ->
beta_hat / M / V / C
  ->
P2
  ->
global update / optional Debt
  ->
post-window Full-Design vs No-Design audit
  ->
future Gate state.

FIRST ACTION IN CURSOR
----------------------

Before editing code, Cursor must produce:

  SAG_IMPLEMENTATION_PLAN.md

That plan must:
- list the existing files/functions implementing old Design logic;
- identify where R/O/U are realized;
- identify where p_obs and q_use are estimated/frozen;
- identify local-training set construction;
- identify P2 and EventTrace;
- list exactly which files will be modified;
- confirm that no dataset-name Gate will remain.

Only after this plan is reviewed should implementation begin.

END

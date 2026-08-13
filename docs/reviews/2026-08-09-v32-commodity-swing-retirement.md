# Inactive v32 commodity Swing retirement candidate

## Problem restatement

The inactive v31 candidate removed SNDK and BRENTOIL Swing execution but
retained GOLD Swing as a control. Exact GOLD side/timing attribution now shows
that zero of eight tested arms survives chronological partitions, stress costs,
and largest-winner removal. Authorizing v31 unchanged would therefore preserve
an execution route whose stated rescue experiment has already failed.

## Exact v32 delta

V32 supersedes v31 as an inactive candidate. Its only semantic change from v31
is:

- `hip3_swing_ha_sndk_gold_brent_bidirectional_v1` execution symbols change
  from `["xyz:GOLD"]` to `[]`.

The provider continues observing SNDK, GOLD, and BRENTOIL in both directions.
All nine assets, all other providers, all execution sides, priorities,
timeframes, notional limits, leverage, stops, targets, maximum holds, the
nine-position ceiling, isolated margin, ledger path, and polling contract are
unchanged. Commodity breakout-pressure routes remain executable controls.

V32 contains 21 executable provider-symbol mappings. It is not armed and has
not been reconciled, launched, or used to place an order.

## Evidence-based rationale

The existing SNDK and BRENTOIL Swing removals remain unchanged from v31. The
new GOLD delta is supported by the exact 32-cell side/timing attribution:

- provider long lost in both development and validation under stress;
- provider short changed from negative development to positive validation;
- next-bar confirmation did not repair cross-partition stability;
- fast-EMA pullback produced zero GOLD trades;
- zero of eight side/timing arms passed the declared repeatability rule.

This is explicit candidate design, not an automatic runtime performance gate.
The live v25 process continues under its already-authorized profile.

## Transition and rollback boundary

V32 must remain inactive until a fresh transition contract binds its exact
fingerprint and evidence. Any future transition requires all assets flat,
owned orders absent, archived drain evidence, a verified prechange backup,
reconciliation without placement, explicit live-risk authorization, and
post-start source/pressure acceptance. Rollback cannot hot-load the old profile;
it requires the same flat and order-free process.

The existing v31 tracker remains report-only historical evidence and was not
restarted or repointed by this candidate preparation.

## Uncertainty and falsifiers

Confidence is high that the machine-checked v31-to-v32 diff changes only GOLD
Swing execution authority. Confidence is medium that the removal improves the
portfolio because the current live GOLD sample remains sparse and shared-route
displacement is not replayed. The candidate is invalidated by a profile diff
outside the declared route, missing both-side observation, evidence hash drift,
transition without a flat/order-free boundary, or any automatic activation.
Its economic recommendation is updated by a preregistered new GOLD mechanism
or independent both-side evidence that survives costs, concentration, and
shared-portfolio interaction.

## Evidence

- Candidate:
  `configs/multi_asset_bidirectional_commodity_swing_retired_candidate_v32.toml`
- GOLD attribution:
  `data/logs/research/bidirectional_cohort/gold_side_mechanism_attribution_20260809T215535Z.json`
- GOLD decision journal:
  `docs/research-journal/hip3-entry-timing-challenger-v3.json`

# V31 Route-Pruning Prospective Tracking Plan

## 1. Problem restatement

Track the proposed v31 route-authority change prospectively without modifying
the active v25 backend. The tracker must distinguish cumulative v25 baseline
evidence from future v31 observation-only evidence, preserve exact run/profile
provenance, and expose enough route-level data to measure avoided losses,
missed opportunity, and retained-control behavior after a transition.

## 2. Fixed hypothesis and route scope

The candidate hypothesis was declared at `2026-08-09T18:44:02Z` in journal
revision `hip3-route-authority-pruning-v1`.

Removed-from-execution routes:

- `hip3_swing_ha_sndk_gold_brent_bidirectional_v1|xyz:SNDK`
- `hip3_swing_ha_sndk_gold_brent_bidirectional_v1|xyz:BRENTOIL`

Retained controls:

- commodity Swing on GOLD;
- commodity Breakout on SNDK, GOLD, and BRENTOIL.

All routes retain both directional hypotheses. The removed routes must remain
observable after v31 activation; their completed-candle forward paths are not
orders or counterfactual fills.

## 3. Assumptions and evidence boundaries

- The bounded live checkpoint is the authoritative read-only projection of the
  current ledger prefix.
- A scorecard counter is cumulative within one exact run/profile identity.
- The first snapshot is a baseline; only same-run/profile deltas are economic
  evidence. A profile transition creates a new baseline rather than a numeric
  continuation.
- Resolved venue lifecycles and signal markouts are separate evidence types.
- Open marks are provisional and cannot change the route decision.

Confidence: high for the tracking contract, because each assumption is
machine-verifiable. Confidence remains medium for the route-pruning hypothesis.

## 4. Required validation

1. Reject any checkpoint that is not report-only or claims execution authority.
2. Accept only the exact v25 source profile or exact v31 candidate identity.
3. Validate the journal revision, timestamp cutoff, and no-authority contract.
4. Validate all six exact route scorecards without defaulting missing data.
5. Under v25, require all six routes executable.
6. Under v31, require the two removed routes observe-only and all four controls
   executable.
7. Preserve candidate config fingerprint, all nine assets, both directions,
   and nine-position capacity.
8. Refuse economic mutation without a new resolved lifecycle in later deltas;
   use the existing immutable cohort audit-delta command for that comparison.

## 5. Success criteria

The tracker is acceptable when focused tests cover both lifecycle phases,
unknown profile rejection, authority drift, missing route evidence, and invalid
journal identity; its first current-v25 baseline publishes atomically; and the
output explicitly states that it cannot route, size, enter, close, pause,
restart, or promote.

## 6. Failure modes and falsifiers

- A removed route appearing executable under v31 is a configuration-integrity
  failure.
- A retained control becoming observe-only is unintended opportunity loss.
- Missing or changed profile/run identity makes snapshots incomparable.
- A checkpoint with fabricated zeros or missing route scorecards fails closed.
- Positive repeated after-cost observation-only paths on both SNDK and
  BRENTOIL, especially with negative retained controls, would falsify pruning.
- Continued negative removed-route paths with stable or positive controls would
  strengthen—but not prove—the candidate.

## 7. Live-state boundary

This plan grants no transition or execution authority. V25 remains unchanged
until every lifecycle is flat, the operator explicitly approves v31, and the
separate transition/backup/rollback contract is verified.

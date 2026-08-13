# HIP-3 Route-Authority Pruning Review

## 1. Problem restatement

Determine whether the live v25 HIP-3 route set should remain unchanged or whether
specific weak routes should lose execution authority without removing their
observation telemetry. The success criterion is a minimal, reversible authority
change supported by common-clock portfolio replay, stressed friction, live-close
reconciliation, and an exact configuration-diff test.

## 2. Assumptions and known facts

- Source profile: `multi_asset_bidirectional_complete_portfolio_canary_v25`,
  fingerprint `ec7715f671fa369d0a415d8941061eb9a577b232bbd4e06367a7342267ff7ecc`.
- The source HIP-3 sidecar contains ten provider-symbol routes across Swing and
  Breakout providers for SP500, SPCX, SNDK, GOLD, and BRENTOIL.
- Index and commodity evidence use different development and validation boundaries.
  Combining their native phase labels would create false cross-family contention.
- The corrected experiment therefore compares variants on identical wall-clock
  intersections: common early, common later descriptive, and common full.
- The artifact is descriptive opened-window evidence. It is not a sealed holdout and
  grants no execution authority.
- Open live marks are excluded from the reconciliation because they are provisional.

Confidence in these facts: high. They are directly encoded in the immutable report
artifact and exercised by focused tests. A source-sidecar identity mismatch or a
reproduction hash mismatch would falsify them.

## 3. Analysis

The broad hypothesis that all commodity Swing routes should be removed was rejected.
GOLD Swing was positive under unchanged-exit validation stress, while SNDK and
BRENTOIL Swing were the weak pair. Five frozen portfolio variants were then replayed
under the same nine-position, $500 initial-equity, strategy-priority, and friction
contracts.

| Common-full result | Trades | Net USD | PF | Max DD % | Net excluding largest winner |
|---|---:|---:|---:|---:|---:|
| v25 nominal | 195 | +18.09 | 1.229 | 3.53 | +2.92 |
| SNDK/BRENT Swing pruned nominal | 174 | +17.23 | 1.247 | 3.62 | +2.12 |
| v25 stress | 202 | -1.68 | 0.982 | 4.19 | -16.59 |
| SNDK/BRENT Swing pruned stress | 179 | +1.93 | 1.024 | 4.11 | -12.98 |

The minimal prune gives up $0.86 nominal net over the full common window while
improving stressed net by $3.60 and stressed PF by 0.042. It does not materially
improve drawdown, and both stressed variants remain negative after removing their
largest winner. Therefore the result supports a reversible candidate, not a claim of
independent profitability.

The 18:05 UTC immutable live reconciliation contains only four closed HIP-3
lifecycles. Full v25 was 1W/3L, -$0.42, PF 0.787. Excluding the observed SNDK Swing
loss gives 1W/2L, +$0.67, PF 1.743. This is directionally consistent with pruning but
far too sparse to establish an edge.

## 4. Uncertainties, risks, and failure modes

- Shared-capital replay is path dependent. Removing a route can expose later entries,
  so the delta is not a simple sum of isolated route PnL.
- The common-later window mixes family-local phase labels and is descriptive only.
- Common-early coverage is sparse for several variants; the SPCX-only variant has no
  trades there.
- The minimal candidate remains concentration-sensitive under stress.
- Historical replays cannot reproduce future venue liquidity, latency, rejects, or
  the exact displacement caused by simultaneous live intents.
- Four live closes cannot distinguish route weakness from chance.

Confidence in the recommendation: medium. It is consistent across corrected
common-clock stress and the available live-close record, but it lacks sealed forward
confirmation. New compatible live closes showing positive SNDK/BRENTOIL Swing
performance across both directions, or a corrected source/simulator defect, would
update or falsify it.

## 5. Validation plan

1. Keep v25 unchanged while any position is open.
2. Validate the inactive v31 config with an exact-diff regression test.
3. At a flat boundary and only after explicit operator approval, transition to v31.
4. Continue recording SNDK and BRENTOIL Swing intents as observation-only evidence.
5. Compare resolved v31 opportunities and displaced same-symbol intents against the
   frozen v25 counterfactual; do not infer from raw signal counts alone.
6. Roll back to frozen v25 if the new profile identity is wrong, protection is absent,
   runtime faults appear, or the executed authority differs from the exact diff.

Good enough for a reversible canary means: exact profile identity, all nine assets
visible, both directions retained, all open positions protected, zero route-authority
drift, and enough resolved forward opportunities to evaluate missed versus avoided
PnL. It does not mean profitability has been established.

## 6. Recommendation and trade-offs

| Option | Expected benefit | Cost or risk | Recommendation |
|---|---|---|---|
| Keep v25 | Preserves all opportunity | Retains weak Swing exposure | Valid rollback |
| Remove all commodity Swing | Simplifies route set | Incorrectly discards supported GOLD evidence | Reject |
| Remove SNDK/BRENTOIL Swing execution only | Improves full-window stress while retaining telemetry and Breakouts | May miss a recovered Swing edge; forward evidence is sparse | Prepare v31 candidate |
| Remove SNDK Breakout too | Better early-window stress | Worse later/full nominal opportunity capture | Do not include |
| Promote v29/v30 | Stronger stressed replay | Much narrower coverage and fewer trades | Continue as research challengers |

The exact v31 change is:

- `hip3_swing_ha_sndk_gold_brent_bidirectional_v1.execution_symbols` changes from
  `SNDK, GOLD, BRENTOIL` to `GOLD`.
- The provider still observes SNDK, GOLD, and BRENTOIL.
- GOLD Swing, all commodity Breakout routes, all index routes, all nine assets, both
  sides, position capacity, sizing, stops, targets, and maximum holds remain unchanged.

No live runtime, order, position, or current v25 configuration was changed by this
review.

## 7. Operator decision required

The inactive v31 candidate can be considered only after the live portfolio is flat.
Arming it requires explicit operator approval at that boundary; preparation of this
file is not authorization to transition or trade.

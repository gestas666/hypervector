# BTC Cross-Sectional Breadth-Expansion Review

**Decision:** Reject this exact contract. Do not build an execution replay,
runtime adapter, TUI strategy tile, shadow allocation, or live authority from
this evidence.

## Problem and frozen test

The experiment tested whether BTC continuation improves when completed
15-minute BTC/ETH/SOL/HYPE 90-minute normalized returns align and
cross-sectional dispersion freshly expands above its strictly prior seven-day
75th percentile. BTC was the only labeled asset. Both long and short were
required. The only horizon was 60 minutes, with a one-minute delayed-entry
diagnostic and 60-minute cooldown.

The primary was compared with two nonselectable controls: a BTC-only momentum
onset and a 24-hour-lagged peer-breadth placebo. It used gross bar returns with
13 bps nominal and 20 bps stressed round-trip references. It did not model
orders, fills, sizing, liquidation, funding, or portfolio PnL and carried
`execution_authority=none` throughout.

## Pre-outcome technical amendment

The first command attempt wrote no artifact or sidecar. It failed because the
original 672-of-672 validity requirement produced no lagged-placebo labels on
the immutable source's small explicit weekly gaps. A signal-only diagnostic
found 990 finite primary dispersion rows and zero finite placebo thresholds; no
return, PnL, cell metric, or selection result was inspected.

Before retrying, the frozen contract retained a 672-position rolling window but
required at least 666 valid observations (99.1%). Candidate bars and label
anchors touching explicit gaps remained invalid. No percentile, breadth count,
direction, horizon, cooldown, cost, control, or economic criterion changed.

The valid run wrote both immutable files. Its first post-publication validation
then exposed an order-sensitive source-key assertion because canonical JSON
sorted HYPE before SOL. A failing regression test was added and only the
validator was made order-insensitive. The experiment was not rerun or
overwritten. The existing artifact then passed a full causal rebuild.

## Primary evidence

All returns below are gross basis points before the 13 bps nominal cost.

| Fold | Events | Long/short | Immediate mean | Delayed mean | Immediate median | Delayed median |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 6 | 1 / 5 | +2.112 | +1.981 | +6.042 | +7.034 |
| 2 | 36 | 13 / 23 | -1.064 | -0.974 | +5.451 | +8.318 |
| 3 | 2 | 1 / 1 | +9.028 | +8.699 | +9.028 | +8.699 |
| Pooled | 44 | 15 / 29 | -0.173 | -0.131 | +6.350 | +8.180 |

Pooled 10%-trimmed means were only +3.932 bps immediate and +3.032 bps
delayed. Long and short immediate means were -3.123 and +1.354 bps. Only 34.1%
of immediate and 38.6% of delayed events exceeded 13 bps gross.

Cadence was 0.239 resolved events per calendar day. The median event gap was
270 minutes and p90 was 714 minutes, but the maximum gap was 89,775 minutes
(62.3 days). This combination shows clustered events separated by long inactive
regimes, not reliable daily opportunity flow.

The primary failed nine frozen criteria:

- insufficient total events per fold;
- insufficient long/short events per fold;
- insufficient events per calendar day;
- immediate and delayed fold means below nominal cost;
- immediate and delayed pooled trimmed means below cost;
- both direction means below cost;
- failure to dominate both delayed controls in every fold.

## Controls and causal contradiction

| Control | Events by fold | Pooled immediate mean | Pooled delayed mean | Interpretation |
|---|---:|---:|---:|---|
| BTC-only momentum | 1 / 66 / 139 | +1.412 | +0.869 | Adequate aggregate cadence, but sub-cost and unstable by fold |
| 24h-lagged breadth placebo | 0 / 17 / 1 | +13.667 | +14.530 | Sparse, absent in fold 1, and directionally asymmetric |

The placebo's pooled value is not promotable evidence: it is based on 18
events, has no fold-1 observations, a single fold-3 observation, long mean
-17.318 bps, and short mean +25.584 bps. Its outperformance of the real breadth
signal weakens the claimed causal mechanism and is consistent with clustered
regime exposure or sampling noise.

## Integrity and reproducibility

Independent validation rebuilt all features, primary/control events, labels,
folds, aggregates, selection, and source identity from the bound repaired
Hyperliquid inputs. It verified one primary cell, two controls, 536 event rows,
four source symbols, 12 generator modules, and zero execution authority.

- JSON SHA-256:
  `903835ee504449161d79a6304ce086591965b37a960b4cc0a0fe71120c1a4dc9`
- Parquet SHA-256:
  `4a52bc5cb5e052954638460a0c08bc981441b0da798701054cbdade40816d0f7`

As with the prior impulse artifact, the historical validator self-hash is
required to be well formed but cannot equal the current validator after fixing
its own validation code. Every non-self generator module is matched exactly.

## Recommendation, confidence, and falsifier

Do not tune the breadth count, percentile, lookback, normalization, horizon, or
direction on this development window. The primary is negative on average before
costs and the placebo contradiction is material. Return to the live disarmed
observer for forward cadence evidence while selecting a causally different
mechanism, not a neighboring breadth threshold.

**Confidence: high in rejecting this exact contract on this development
window.** The conclusion does not depend on a marginal gate: pooled gross mean
is negative, both directions are sub-cost, cadence is uneven, and controls do
not support the causal thesis. Confidence is low about all possible breadth
strategies because only one preregistered formulation and horizon were tested.

The rejection would be updated by a material source/causality defect or a
separately frozen mechanism that produces stable immediate and delayed gross
returns above measured costs in both directions and dominates controls across
chronological folds. A post-hoc threshold change or the sparse profitable
placebo subgroup would not falsify it.

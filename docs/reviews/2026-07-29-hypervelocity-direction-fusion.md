# Hypervelocity 1m-First Direction-Fusion Review

## Question

Does preferring the completed 1m trend direction, with the canonical 5m entry
direction as a fallback, improve both creator-entry alignment and realistic
trade economics?

## Frozen comparison

- Window: 2026-04-28 00:00 UTC through 2026-07-27 00:00 UTC.
- Venue evidence: 2,160 checksum-verified 0xArchive hourly Hyperliquid bundles.
- Control: current faithful canonical 5m authority with a 300-second cooldown.
- Challenger: completed 1m `TREND_UP`/`TREND_DOWN` direction first, otherwise
  retain the canonical entry direction.
- Execution: public-trade-through maker fills, authentic Hyperliquid mark/oracle
  context, settled funding, 70% isolated margin allocation, 40x BTC leverage,
  and the existing 8% margin target.
- The challenger is report-only. Runtime, TUI, configuration, and ML authority
  were not changed.

The base creator tracker contains 34 reconciled logical entries. The
supplemental screenshot evidence contributes one new July 25 long, so the
extended comparison contains 35 entries. This is the sole reason earlier
34-entry and current 35-entry denominators differ.

## Results

| Metric | Canonical 5m | Prefer 1m, else 5m |
|---|---:|---:|
| Exact creator direction matches | 24/35 | 31/35 |
| Maker submissions | 345 | 27,990 |
| Entry fills | 277 | 274 |
| Targets | 241 | 237 |
| Full liquidations | 36 | 37 |
| Partial liquidations | 10 | 11 |
| Fees | $6,003.51 | $6,285.95 |
| Funding cashflow | +$22.38 | +$31.47 |
| Final equity from $10,000 | $27.04 | $14.95 |
| Maximum drawdown | -99.85% | -99.92% |

The fusion increased exact source recall by seven entries but generated
27,645 more maker submissions. Most were canceled when the preferred 1m
direction changed while an intent was pending. This is adverse operational
churn even before private queue position and genuine cancellation latency are
modeled.

The two candidates shared 234 resolved signal-time/direction identities. All
201 shared targets stayed targets, and all 33 shared liquidations stayed
liquidations. The fusion removed 43 resolved control opportunities and added
40 different opportunities, changing the equity and sizing path without
improving shared outcomes.

Shorts remained the larger loss source. The canonical control recorded 145
short fills, 20 short liquidations, and -$8,254.87 short net PnL. The fusion
recorded 143 short fills, 22 short liquidations, and -$8,472.01 short net PnL.
Its long side improved modestly but not enough to offset the short-side and fee
damage.

Both runs used the same archive limitations: 21 empty book hours, 496 stale
mark events, zero missing mark events, and zero missing or stale oracle
settlements. Those limitations weaken absolute performance inference but do
not explain the relative difference because they were identical across arms.

## Decision

Reject the broad 1m-first fusion. Preserve 5m as canonical execution authority
and retain 1m as tactical telemetry and breakout confirmation. The result also
does not validate the canonical control: it lost nearly all starting equity in
this window.

Confidence is high for the relative 90-day comparison because inputs,
friction, archive identity, and execution code were matched. Confidence is low
that either arm has a profitable edge. An untouched venue-matched window in
which the fusion improves terminal equity, drawdown, liquidation count, and
submission load together would update this conclusion.

## Evidence

- Canonical control:
  `data/logs/research/hypervelocity_faithful_canonical_5m_maker_90d_20260729.json`
  (`e55860b473c3d6a3fc23b63e6597e8a529a09db4bfad978ae2028262ba4ca050`).
- 1m-first fusion:
  `data/logs/research/hypervelocity_faithful_prefer_1m_fusion_maker_90d_20260729.json`
  (`b0edd19dcdd24478592a04372ea6fabb39c435146d8ebd13f506acb257a4df5b`).
- Fast serial screen:
  `data/logs/research/hypervelocity_faithful_prefer_1m_fusion_screen_20260729.json`
  (`2d188966b1c9f57b9490acfee2007519cb06a6841e7c5862cda8c508d22ab4e2`).

# Recent weak/choppy short-sizing review

Date: 2026-07-30

## 1. Problem restatement

The frozen weak/choppy sizing rule improved the older source-follow path but
had not been replayed on the later 2026-04-28 through 2026-07-28 Hyperliquid
tape. This experiment asks whether halving only `TD_WEAK_CHOPPY` entries
improves the current 35%-margin, 30x short strategy without deleting signals or
changing target, holding period, fees, funding, liquidation, or order rules.

Success requires exact reproduction of the frozen all-day control, unchanged
signal/submission counts, and improved net equity or drawdown without worsening
profit factor or liquidation count. The experiment is report-only; runtime and
ML authority remain unchanged.

## 2. Known facts and assumptions

- Pinned source revision: `ad15f2bdc949619be495a5f516babd08f7f52a90`.
- Initial equity: $15,000; isolated allocation: 35%; leverage: 30x.
- Target: 8% gross margin return; maximum hold: 24 hours.
- Entry: 60-second post-only public-trade-through reconstruction.
- The 33 source decisions are joined to their subtype at the exact causal
  `available_at` timestamp; 19 are weak/choppy and 14 remain full size.
- Twenty-one archive hours contain no L2 rows. No pending order or position
  overlaps those hours, but the report conservatively remains marked
  execution-economics inconclusive.

Before replay, attribution showed that the one 24-hour loss was weak/choppy,
while both liquidations were strong/high-vol. The scaler could therefore
reduce one loss but could not directly change either liquidation's size.

## 3. Exact venue result

The uniform arm exactly reproduced the frozen shared-portfolio short control
after canonical JSON normalization.

| Metric | Uniform control | Weak/choppy half | Difference |
|---|---:|---:|---:|
| Submitted entries | 33 | 33 | 0 |
| Filled trades | 26 | 25 | -1 |
| Targets | 23 | 22 | -1 |
| Liquidations | 2 | 2 | 0 |
| Time exits | 1 | 1 | 0 |
| Final equity | $9,586.10 | $8,744.33 | -$841.78 |
| Net PnL | -$5,413.90 | -$6,255.67 | -$841.78 |
| Profit factor | 0.558 | 0.424 | -0.134 |
| Maximum marked drawdown | -60.74% | -58.19% | +2.56 pp |
| Funding cashflow | +$16.68 | +$15.22 | -$1.46 |

The 24-hour weak/choppy loss fell from -$2,413.56 to -$1,206.78. Both
strong/high-vol liquidations remained, at -$5,100.41 and -$4,557.32 in the
scaled path. Compounding changed later full-size quantities slightly.

One May 27 full-size entry expired only in the scaled path. Earlier sizing
differences changed portfolio equity and therefore its required public
trade-through quantity. This is a stateful capacity effect, not a deleted
signal: both arms submitted all 33 entries.

## 4. Risks, uncertainty, and falsifiers

- Public trade-through proves displayed public volume crossed the limit but
  cannot reveal private queue rank or cancellations.
- This later interval is diagnostic rather than a pristine holdout because the
  broader source logic and tail problem were already inspected.
- The older improvement depended partly on smaller orders completing before
  reversals; that mechanism did not repeat consistently here.
- A replay-accounting defect, altered source-label identity, or materially
  different venue evidence would update this result.

Confidence is high that the scaler worsens this exact interval and high that
it does not solve the observed liquidation tail. Confidence about future
expectancy remains low because regime/subtype payoff relationships changed
between historical blocks.

## 5. Recommendation and next validation

Reject weak/choppy half-sizing for runtime promotion. Preserve the running
uniform 35%/30x shadow control. The next bounded challenger is the already
frozen 06:00-15:00 UTC source session: it predates these losses, was the older
development leader, and all three recent losing entries occurred outside it.
That session must be replayed statefully against the identical all-day control;
the apparent 14-target/no-loss subset is attribution only, not a portfolio
result.

The session hypothesis fails if exact replay is non-positive after costs,
retains liquidation exposure, or does not survive older frozen evidence. Even
if positive, it remains a report-only candidate until forward observations
distinguish a market-session effect from the creator's waking schedule.

## 6. Evidence identity

- Artifact:
  `data/logs/research/hypervelocity_short_weak_choppy_scaling_20260428_20260728_trade_through_v1.json`
- SHA-256:
  `ae9d6277d5549378ba6c0e19f2a186ef6107d1e3b8dfc2ca48f500abd4f81d3a`
- Runtime changed: false.
- Execution authority: none.
- Model authority: observe.

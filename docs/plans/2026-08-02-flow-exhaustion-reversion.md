# Flow exhaustion reversion — frozen development contract

**Status:** Development-falsified. A technical data-boundary amendment was
recorded below before any strategy outcome was inspected. The immutable result
is summarized at the end of this document. This document grants no live
authority and does not change the running disarmed observer.

## Problem restatement

The executable SOL range-onset sleeve has historically produced about 0.8
trades per week, while the existing BTC Hulk and maker-entry branches are also
sparse. Previous five-minute EMA pullbacks, oscillator crossovers, simple wick
sweeps, and compression breakouts failed after realistic friction. The next
candidate must therefore test a different market mechanism while preserving
both directions and a useful portfolio-level observation cadence.

## Evidence and assumptions

- `market.duckdb` contains historical Hyperliquid L2 and public trades for BTC
  and SOL. It does not contain matching historical OI or explicit liquidation
  events. The candidate is therefore named **flow exhaustion**, not liquidation
  reversal.
- ETH and HYPE do not have matching historical L2 coverage in the current
  database. They remain forward-observation assets and cannot be included in
  this historical economic claim.
- The Trade-Oracle notebook suggested structural sweep/reclaim. That mechanism
  was already tested locally. The ML4T notebook suggested forced-flow reversal,
  but its liquidation interpretation requires OI evidence that is unavailable.
- This candidate is distinct because it requires event-time aggressor-flow
  reversal and opposing terminal-book replenishment after displacement. A wick
  or close reclaim alone is insufficient.

## Frozen causal signal

Evaluate every completed five-minute bar independently for BTC and SOL.
Features use exchange timestamps no later than the bar close.

1. `shock_bps = (close / open - 1) * 10_000` and `shock_side` is its sign.
2. The absolute shock must exceed both 26 bps and the prior-only rolling 97.5th
   percentile of absolute five-minute returns over 2,016 bars (seven days).
3. Five-minute aggressor imbalance must align with the shock and exceed the
   prior-only rolling 75th percentile of absolute imbalance over the same
   window.
4. During the final 60 seconds, aggressor imbalance must reverse to the
   opposite sign.
5. The final top-five book imbalance must also oppose the shock. This is the
   observable replenishment condition.
6. Enter the opposite direction at the next available one-minute open. Reject
   a delayed or gapped entry when the pre-shock open no longer offers at least
   26 bps gross target distance. This is an explicit strategy rule.

No EMA, RSI, BBWP, model probability, or regime state can veto the entry.
Canonical regime, funding, OI when available, and ML predictions remain
annotations for later conditional analysis.

## Frozen lifecycle and portfolio rules

- Target: the shock bar open, representing full displacement reversion.
- Stop: two bps beyond the shock-bar wick extreme.
- Maximum hold: 30 minutes after entry.
- Same-minute ambiguity: liquidation, then stop, then target.
- Nominal round-trip friction: 13 bps; stress surface: 20 bps.
- Funding: apply only verified venue funding events crossed by the lifecycle.
- One position per symbol; at most two total positions across BTC and SOL.
- Simultaneous signals rank by `abs(shock_bps) / causal_shock_threshold`;
  stable ties rank BTC before SOL. No pyramiding or same-symbol overlap.
- Research accounting begins at $15,000 with 5x isolated leverage and 0.25%
  desired equity risk per setup, capped by 10% isolated margin per position.

## Development boundary and immutable outputs

- Original proposed development start: `2025-07-28T00:00:00Z`.
- Amended development: `2025-08-04T00:00:00Z` through
  `2026-01-28T00:00:00Z`.
- Reason recorded before outcome generation: BTC has no canonical trade bars
  from `2025-05-28T00:00:00Z` through `2025-07-27T23:59:59Z`; July 28 is the
  first recovered BTC bar and therefore cannot have the frozen seven-day
  causal warm-up. SOL also has no bars on July 27. August 4 is the earliest
  common boundary with 2,016 contiguous prior five-minute bars.
- Both assets lack the `2025-08-23T08:50:00Z` bar. The implementation must
  reset the rolling history at that gap and cannot resume decisions until
  2,016 new contiguous bars have completed. No interpolation or cross-gap
  percentile is permitted.
- Candidate-specific validation and pseudo-holdout remain untouched unless the
  development criterion is met.
- Output must preserve every eligible signal, rejection, fill, lifecycle,
  side, symbol, cost, funding event, and portfolio conflict in immutable JSON
  plus Parquet sidecars.
- Authority fields must state `report_only=true`,
  `execution_authority=none`, and `place_attempted=false`.

These periods have been inspected for other strategies, so later segments are
candidate-specific holdouts rather than pristine research-process holdouts.
Fresh forward evidence remains necessary.

## Declared development criterion

All results are retained whether they pass or fail. Validation is consumed only
if the development artifact has:

- at least 100 completed shared-portfolio trades;
- 0.5 to 5.0 completed trades per calendar day, with 1 to 3 per day the cadence
  objective rather than a profitability gate;
- positive net PnL and profit factor above 1.15 at 13 bps;
- profit factor above 1.00 at 20 bps;
- at least 20 completed trades in each direction and positive net PnL for both
  long and short sleeves; and
- no eligible lifecycle crossing a missing one-minute evidence row and no
  modeled liquidations. Historical gaps outside a lifecycle remain disclosed
  and force the seven-day signal-history reset described above.

Failure does not justify post-hoc percentile, target, stop, or direction
changes. A materially different mechanism requires a new preregistration.

## Validation and falsifiers

Implementation is falsified by future timestamps in any feature, current-bar
values entering prior-only percentiles, a missing five-minute interval treated
as continuous, optimistic same-minute ordering, fabricated OI/liquidation
labels, duplicated positions, unreported conflicts, or a TUI-derived trade.

The economic hypothesis is weakened by sub-cost gross excursions, profit
factor at or below one after nominal cost, one direction carrying all gains,
cadence below 0.5/day, or failure in an untouched chronological segment.
Passing development is not proof of profitability; exact venue-event replay
and a disarmed backend-owned forward shadow journal are required next.

## Frozen development result

Artifact:
`data/logs/research/flow_exhaustion_development_v1_20260802T091000Z.json`.
The candidate generated 16 completed trades over 177 calendar days, or 0.0904
per day. Nominal 13-bps replay finished at `$14,808.09`: `-$191.91`, PF `0.284`,
three wins, thirteen losses, and `-1.28%` maximum drawdown. Stress replay at 20
bps lost `$272.07` with PF `0.180`.

Both sides failed: eight longs lost `$150.57` with PF `0.023`, and eight shorts
lost `$41.34` with PF `0.637`. BTC lost `$89.33`; SOL lost `$102.58`. There were
zero modeled liquidations, zero impacted-lifecycle data gaps, and zero replay
rejections. The technical-integrity criterion passed while every cadence and
economic criterion failed. Candidate-specific validation and pseudo-holdout
remain unconsumed. Lowering the shock or flow thresholds after observing this
result is prohibited under this contract.

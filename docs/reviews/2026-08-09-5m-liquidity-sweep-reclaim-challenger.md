# Five-Minute Liquidity Sweep/Reclaim Challenger Review

## Problem restatement

The test asked whether a completed five-minute sweep of a causal one-hour
structural high or low predicted enough next-bar continuation or reclaim
reversal to survive Hyperliquid friction. The fixed contract covered BTC and
SOL, both sides, a next-five-minute-open entry, a candle-extreme structural
stop, a 2R target, a six-hour maximum hold, recorded funding, 13-bps nominal
cost, 20-bps stress cost, one position per symbol and arm, and pessimistic
stop-first ordering.

The output was report-only. It did not change v25, activate v30, place an order,
or grant a model execution authority.

## Observable facts

- Development interval: 2025-07-28 through 2026-01-28, 184 days.
- Accepted non-overlapping lifecycles: 15,321.
- Displaced, invalid, truncated, or purge-boundary rows: 13,953.
- BTC emitted 14,766 events; SOL emitted 14,508 events.
- Fifty-eight dual sweeps were classified as ambiguous and excluded.
- 2,804 events lacked the observed terminal spread required to construct the
  frozen structural stop and were rejected as invalid barriers.
- 111 labels encountered an unavailable next bar or path gap and were
  truncated.
- Funding was included at recorded hourly venue boundaries.

## Results

| Fixed arm | Trades | Mean nominal | Nominal PF | Stress mean | Stress PF | Nominal MTM DD | Net ex largest |
|---|---:|---:|---:|---:|---:|---:|---:|
| Acceptance continuation | 6,396 | -13.37 bps | 0.529 | -20.37 bps | 0.392 | 85,558 bps | -87,446 bps |
| Reclaim reversal | 8,925 | -12.00 bps | 0.428 | -19.00 bps | 0.274 | 107,106 bps | -107,436 bps |

The pre-fee path did not contain an edge. `gross_return_bps` already includes
the fixed 2-bps adverse entry and exit slippage but excludes the 9-bps fee:

- acceptance continuation averaged -4.36 bps before fees;
- reclaim reversal averaged -3.00 bps before fees; and
- mean funding was approximately zero for both arms.

Removing transaction costs therefore would not turn the observed directional
relationship positive. Removing the largest winner also left both arms deeply
negative.

## Side and asset decomposition

Every nominal BTC/SOL and long/short cell was negative:

| Arm | Asset | Side | Trades | Mean | Net |
|---|---|---|---:|---:|---:|
| Acceptance | BTC | Long | 1,574 | -14.17 bps | -22,300 bps |
| Acceptance | BTC | Short | 1,645 | -12.86 bps | -21,161 bps |
| Acceptance | SOL | Long | 1,606 | -13.84 bps | -22,219 bps |
| Acceptance | SOL | Short | 1,571 | -12.64 bps | -19,865 bps |
| Reclaim | BTC | Long | 2,221 | -13.16 bps | -29,228 bps |
| Reclaim | BTC | Short | 1,992 | -12.36 bps | -24,618 bps |
| Reclaim | SOL | Long | 2,350 | -11.51 bps | -27,055 bps |
| Reclaim | SOL | Short | 2,362 | -11.08 bps | -26,174 bps |

## Chronological and regime checks

Three development folds were separated by one-day purge windows. Both arms
were negative at nominal and stress friction in every fold. Nominal arm means
were:

- fold 0: continuation -13.45 bps; reclaim -11.65 bps;
- fold 1: continuation -12.93 bps; reclaim -12.68 bps; and
- fold 2: continuation -13.66 bps; reclaim -11.79 bps.

The causal canonical 15-minute annotations did not reveal a positive slice.
Continuation means ranged from -3.68 bps in `BREAKOUT` to -14.81 bps in
`TREND_DOWN`. Reclaim means ranged from -11.43 bps in `TREND_UP` to -15.75 bps
in `TRANSITION`. These are descriptive opened slices, not a basis for a new
gate.

## Decision and confidence

Decision: reject both exact arms. Do not tune the structural lookback, reward
multiple, hold, spread pad, regime slice, or asset subset on this opened
interval. Do not train Ridge or LightGBM to rescue a base event whose raw
directional expectancy is negative. Do not add either arm to v30 or increase
leverage.

Confidence: high for rejecting this exact contract. It is supported by 15,321
non-overlapping lifecycles, both directions, two assets, three negative folds,
all negative side cells, all negative regime slices, realistic fixed costs,
exact funding, and negative pre-fee path expectancy.

This does not establish that every liquidity-sweep strategy is unprofitable. It
establishes that this fixed one-hour-level, next-open, candle-extreme, 2R family
did not show an edge in the opened venue window.

## Uncertainties and failure modes

- Five-minute OHLC cannot recover sub-bar event order. Same-bar stop and target
  touches were deliberately resolved stop-first.
- Public terminal L2 is not private queue evidence. It was annotation-only,
  except the observed spread was required by the frozen stop construction.
- Completed-bar fills approximate market execution and do not model a private
  IOC acknowledgement sequence.
- The opened interval cannot support nearby threshold tuning or a confirmation
  claim.
- Sampled mark-to-market drawdown uses five-minute bar extrema; live gaps can be
  worse.
- BTC and SOL archive discontinuities reset structural warmup rather than being
  filled.

The rejection would be updated if an independent implementation reproducing
the same causal contract finds materially different lifecycle arithmetic, if
the evidence bytes change, if future observations entered decision rows, or if
the fee/slippage/funding identity is disproven. A different preregistered
mechanism may be tested, but it would not falsify this exact rejection.

## Recommended next actions

1. Keep live v25 unchanged while it owns positions and venue stops.
2. At a verified flat-and-order-free boundary, request renewed explicit live
   authority before any transition.
3. If authorized, use the already frozen v30 composition at 1.00x: SOL Range
   Onset `$75`, ETH Range Onset `$25`, and SPCX Swing/HA `$75`, all at 5x,
   one position per symbol, maximum three positions.
4. Do not increase v30 leverage or notionals. Its confidence remains
   low-medium because the common final opened interval contains only 29 trades.
5. Reconcile prospective v30 fees, funding, stop gaps, and adverse excursions
   after five closes or 72 hours, whichever comes first.
6. Pause nearby one-minute shock and five-minute sweep tuning. The next offline
   challenger, if pursued, should be a materially different mechanism with a
   frozen contract and a sealed time boundary, not another threshold variant.

## Validation performed

- Fourteen focused unit tests passed.
- Ruff static checks passed for all new source, script, and test files.
- The immutable JSON report and Parquet lifecycle sidecar were generated once.
- Source, artifact, and sidecar SHA-256 identities were recorded.
- No runtime, profile, process, order, position, stop, leverage, or notional was
  changed.

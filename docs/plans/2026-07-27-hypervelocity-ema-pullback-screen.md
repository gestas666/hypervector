# Hypervelocity EMA Pullback Trigger Screen

**Status:** Completed exploratory serial screen; no runtime change.

## Hypothesis

The external reverse-engineering note proposed EMA9/21 trend, an EMA9
pullback/reclaim, 3- or 5-bar directional momentum, and RSI 30/70 avoidance as
the likely tactical entry trigger. The screen kept the current hard BBWP25,
recovery-6 5m regime context, 70%/40x sizing, 8% target, and target-only
same-side event re-entry fixed.

## Causal definitions

- Long: current 5m eligibility is long, EMA9 > EMA21, completed-bar low touches
  EMA9, close reclaims EMA9, close exceeds close 3 or 5 bars earlier, RSI < 70.
- Short: exact directional mirror with RSI > 30.
- Only the rising edge of a qualifying condition emits an entry event.
- Both 3 and 5 were declared in the external note; no additional lookback was
  added after results.

## Result

| Momentum lookback | Events | Trades | Targets | Liquidations | Final equity | Max drawdown | Source match <=10m |
|---|---:|---:|---:|---:|---:|---:|---:|
| 3 bars | 3,091 | 394 | 351 | 43 | $465.54 | -98.93% | 8/35 |
| 5 bars | 3,068 | 390 | 342 | 48 | $32.00 | -99.82% | 7/35 |

The 3-bar variant matched 18/35 source entries within 30 minutes and the
5-bar variant 17/35, but neither beat the hard/recovery serial control and both
were materially worse. Full L2 replay was not justified because the cheap
screen failed on equity, liquidation count, and source timing simultaneously.

## Decision and uncertainty

Do not install the older inferred EMA9/21 pullback trigger. This falsifies the
specific operational definition, not every possible pullback strategy. A
different result from fresh source records containing the actual entry signal
would update the conclusion. Confidence is medium for this 90-day serial
comparison and low for undocumented details of the original strategy.

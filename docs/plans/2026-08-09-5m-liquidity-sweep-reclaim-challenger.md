# Five-Minute Liquidity Sweep/Reclaim Challenger

## Purpose

Test a materially different cadence mechanism after the one-minute shock family
failed. This is report-only research and cannot change v25, activate v30, or
place an order.

## Hypothesis

A five-minute sweep of a causal one-hour structural high or low may contain an
after-cost edge when the completed candle either reclaims the level or accepts
beyond it. This differs from the rejected one-minute impulse family because the
event is defined by a prior structural liquidity level and close location, not
by body size, volume percentile, or a generic price shock.

## Fixed scope

- Symbols: BTC and SOL, both long and short.
- Development source: venue-matched Hyperliquid candles, public trades, L2, and
  funding already available locally.
- Decision timeframe: completed 5-minute candle.
- Context: causal 15-minute regime, volatility, signed public-trade flow, L2
  imbalance, microprice displacement, and spread are annotations, not live gates.
- Entry: next available 5-minute open with adverse taker slippage.
- One position per symbol and arm.

## Predeclared arms

1. `sweep_reclaim_reversal`
   - high sweeps the prior 12 completed 5-minute highs and closes back below for
     a short, or low sweeps the prior lows and closes back above for a long;
   - stop is beyond the sweep extreme plus one observed spread;
   - target is 2R; maximum hold is six hours.
2. `sweep_acceptance_continuation`
   - the candle sweeps and closes beyond the prior structural level;
   - entry follows the close direction;
   - the same structural stop, 2R target, and six-hour maximum hold apply.

If stop and target are both touched in one bar, resolve stop first. No nearby
threshold search is allowed in the first pass.

## Friction and validation

- Nominal crypto round trip: 13 bps.
- Stress crypto round trip: 20 bps.
- Include recorded funding at its observed venue boundary.
- Purge overlapping lifecycles and split chronologically into non-adjacent
  development folds.
- Report each symbol, side, arm, and regime slice separately.
- Report net, PF, trade count, maximum mark-to-market drawdown, MAE/MFE, time in
  trade, and net excluding the largest winner.
- Ridge or LightGBM may annotate outcomes only after the deterministic contract
  is frozen. A model has no execution authority.

## Decision rule

Reject the exact arm if aggregate or side-specific after-cost evidence is
negative, if the result depends on one winner, or if non-adjacent folds disagree
without an explicit causal explanation. A surviving arm remains a canary
candidate, not an automatic promotion.

## Failure modes

- Five-minute OHLC cannot recover sub-bar event order or private IOC queue
  position.
- Structural levels can cluster many correlated events; lifecycle purging is
  mandatory.
- L2 terminal state may be consequence rather than cause, so it remains an
  annotation in the first pass.
- A positive opened result may be selection bias; only prospective route-matched
  closes can raise confidence.

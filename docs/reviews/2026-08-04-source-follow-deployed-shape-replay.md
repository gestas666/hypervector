# BTC Source Follow Deployed-Shape Replay

**Observed:** 2026-08-04 EDT  
**Artifact:** `data/logs/research/source_follow_deployed_shape_btc_1y_20260804.json`  
**SHA-256:** `ddc095ab93a1c0d15a9eb3c8ad93a349b8330b767e5c49bab1927404ca6b22bc`

## Problem restatement

The prior BTC Source Follow research contract modeled maker entry, no stop, and
the legacy lifecycle while the active cohort uses taker IOC entry, a fixed
80-bps safety stop, a 26.6667-bps maker target, and a fixed 24-hour maximum
hold. This prevented economic research results from being compared honestly
with live outcomes.

## Frozen evidence

- Window: 2025-07-28 00:00 UTC through 2026-07-27 23:55 UTC.
- Inputs: 525,600 Hyperliquid one-minute bars, 105,120 exact five-minute source
  labels, and 8,760 hourly funding observations.
- Signal policy: both directions, confidence at least 0.70, signal range from
  12 through 100 bps, and one BTC position at a time.
- Execution shape: 3% margin, 5x leverage, $25 maximum notional, 4.5-bps taker
  entry fee, 2-bps adverse IOC entry slippage, 80-bps stop, 26.6667-bps maker
  target, and 24-hour maximum hold.
- The replay is report-only and has no execution, sizing, routing, or promotion
  authority.

## Results

| Scope | Trades | Wins/Losses | Net PnL | Profit factor |
|---|---:|---:|---:|---:|
| Combined | 782 | 571/211 | -$17.8237 | 0.6193 |
| Long | 365 | 261/104 | -$9.9154 | 0.5707 |
| Short | 417 | 310/107 | -$7.9083 | 0.6667 |

Additional observed results:

- Final normalized equity: $482.1763 from $500.
- Realized-close maximum drawdown: -3.5952%.
- Exit outcomes: 571 targets, 208 stops, 3 maximum holds, 0 liquidations.
- Total fees: $13.0824; funding cashflow: -$0.0173.
- Eligible signals: 815; 33 arrived while the single BTC slot was occupied.
- Ten trades overlap continuity-filled bars and retain incomplete venue
  provenance.

The gross target-to-stop ratio requires a win rate above 75% before costs.
The observed win rate was approximately 73.0%, and fees reduced the result
further. Both sides were negative under this execution shape.

## Assessment and recommendation

Confidence is **high for mechanical contract alignment**: the current runtime
and replay now agree on entry liquidity, stop, target, and maximum hold, and the
production-ledger checkpoint reports 10/10 provider-symbol contracts aligned.

Confidence is **medium that this exact BTC configuration lacks historical
edge**: the sample is broad and venue-matched, but one-minute bars cannot reveal
private queue position or exact intrabar ordering, slippage is fixed, funding
uses entry-price notional, and drawdown is sampled only at resolved closes.

Do not interpret `runtime_shape_aligned` as a profitability claim. Keep the
current canary evidence descriptive, do not increase its allocation based on
this replay, and compare future exact live fills with the modeled fee,
slippage, stop, and target distributions before changing the signal or
execution contract.

This assessment would be updated by a material replay defect, different exact
venue mechanics, or a sufficiently broad forward sample whose net profit
factor remains above 1 after fees, funding, and slippage. A few favorable live
trades would not by themselves falsify the one-year result.


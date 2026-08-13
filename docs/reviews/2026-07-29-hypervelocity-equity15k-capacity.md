# Hypervelocity $15,000 Maker-Capacity Review

Date: 2026-07-29

## Problem restatement

The operating baseline is now $15,000. The frozen source-follow short control
was previously replayed with $10,000, 70% isolated margin, 40x leverage, and a
trade-through maker-fill rule. Linear PnL scaling was not valid because a 50%
larger post-only order can change queue consumption and fills.

This review changes only initial equity and resulting order size. It does not
change events, session hours, source confidence, target, leverage, allocation,
fees, funding, liquidation logic, or runtime configuration.

## Fixed evidence

Both arms use the same 12 independently reset, gap-free Hyperliquid blocks,
pinned Hypertrader labels, 06:00-15:00 UTC half-open source window, minimum 0.70
source confidence, 60-second entry eligibility, 100-bps completed-5m signal
range ceiling, and public-trade-through fill evidence.

The $10,000 arm posts up to $280,000 notional. The $15,000 arm posts up to
$420,000 notional. Blocks remain independently reset because archive gaps make
a continuous execution path invalid.

Aggregate summary artifact:
`data/logs/research/hypervelocity_source_follow_equity15k_capacity_summary_20260729.json`
(SHA-256
`0bddd94ab9ce1247ef7856bb6dbcccdef0d43ff56233765ee481b5e3ba1bb319`).

## Result

| Metric | $10,000 control | $15,000 capacity | Delta |
|---|---:|---:|---:|
| Entry fills | 59 | 48 | -11 |
| Completed trades | 58 | 47 | -11 |
| Target completions | 55 | 44 | -11 |
| Liquidations | 3 | 3 | 0 |
| Open positions | 1 | 1 | 0 |
| Positive blocks | 10/12 | 9/12 | -1 |
| Aggregate reset-block PnL | +$17,577.90 | +$16,749.72 | -$828.18 |
| Median block PnL | +$2,346.81 | +$2,250.92 | -$95.89 |
| Worst block drawdown | -74.53% | -74.53% | 0.00 pp |

The larger arm retained only 95.29% of the smaller arm's aggregate dollar PnL
despite 50% more starting capital. Eleven target fills disappeared while all
three liquidation paths remained.

## Decision

Reject naive capital scaling of the frozen Hypervelocity short control. It is
not a credible route to the $100,000-$150,000 annual net objective at a $15,000
starting balance.

Retain it as a control for the broader strategy search. New candidates may use
different allocation, leverage, target, stops, trailing or partial exits,
maker/taker execution, timeframes, indicators, ML ranking, and regime routing.
Any combined system must use one shared $15,000 portfolio rather than summing
independent strategy accounts.

## Uncertainty and falsification

Confidence is high that capacity changed fills in these exact windows because
the event stream and all non-capital parameters are identical. Confidence is
low that the result generalizes to a different execution algorithm.

The capacity conclusion would be updated if split post-only orders, longer
eligibility, or an explicitly modeled taker fallback restores the missing fills
and improves untouched holdout net PnL after its additional friction. Such an
experiment would be a new execution candidate, not a reinterpretation of this
control.

The aggregate is not a continuous annual forecast. Summing independently reset
blocks is appropriate for the gap-separated comparison but cannot establish a
live compounded equity path.

# SPCX crossing composition: no supported entry filter

The fixed historical comparison does not justify adding a price-contribution
filter. High confidence in the reproduced descriptive counts; low confidence in
any forecast of relative profitability. Only four executed longs belong to the
lower-contribution group, all in the development partition. Their larger mean
return does not support reversing the filter either.

The two live entries that motivated the question were already observed before
this study. The group split was recorded in
`v89-spcx-independent-indicator-replay-20260908-v1.json` before inspecting these
historical group outcomes. The detailed protocol was frozen before this replay.
Neither fact makes the previously screened history untouched validation.

## Fixed comparison

Native Hyperliquid 15-minute candles and official hourly funding cover July 19
through September 7, 2026, exclusive. July 19–20 supply warm-up; the continuous
evaluation covers July 21–September 7 (48 days). The prior development/extension
boundary remains August 18. All three existing fee/slippage scenarios and the
unchanged bidirectional hourly band strategy are retained, including $500 maximum
notional, 10x leverage, clamped structural stops and a 24-hour maximum hold.

For each completed long recovery, price contribution is the signed close change
divided by the change in the close-minus-lower-band gap. The fixed groups are
`>= 0.5` and `< 0.5`. Fractions can be negative or greater than one; they are not
clamped. This is descriptive attribution of baseline trades, not a simulation
that suppresses one class of entries.

| Continuous, nominal costs | Price contribution >= 50% | Price contribution < 50% |
|---|---:|---:|
| Signals / executed longs | 21 / 20 | 5 / 4 |
| Winners / losers | 14 / 6 | 2 / 2 |
| Observed win rate | 70% | 50% |
| Net total | +$21.12 | +$10.61 |
| Mean net return on entry notional | +21.12 bps | +53.06 bps |
| Median net return | +36.31 bps | +59.02 bps |
| Executed longs after August 18 | 10 | 0 |
| Mean ATR / signal close | 88.46 bps | 147.46 bps |

The higher-contribution group has the higher observed win rate and lower observed
mean return. These are separate quantities. Both groups become net negative when
their largest winners are removed: excluding up to three winners gives -$6.74
and -$14.14, respectively. Removing only the largest winner from the four-trade
group gives -$6.99.

With 5.5 bps modeled entry/market-exit slippage and 0.9 bps fees, group totals are
+$15.40 and +$9.55. With the existing full-fee stress (9 bps fees and 5.5 bps
slippage), totals are -$0.82 and +$6.30. These cases use the prior simulator's
execution contract; they do not establish current liquidity or latency.

The lower-contribution trades occurred during larger prior 24-hour declines
(mean -674.04 bps versus -170.37 bps) and higher ATR. All four had negative prior
24-hour returns; 16 of 20 higher-contribution trades did. These simple causal
context measures are proxies, not the production regime detector's labels.
Sample size, time concentration and differing context prevent a reliable
attribution of relative returns to crossing composition.

There are no censored or same-bar ambiguous long exits in these cases. Excursions
use fully held 15-minute candles before the exit candle plus entry/exit fills.
They are lower bounds: exit-candle extremes are excluded because their ordering
relative to the exit is unknown.

The two unexecuted signals occurred September 1 at 13:45 UTC (higher contribution)
and September 4 at 20:45 UTC (lower contribution). Both fell inside an existing
long's lifetime. Changing which earlier entries are admitted could change later
eligibility, so subtracting group P&L is not a valid filter backtest.

## Validation and evidence

All three continuous cost cases reproduce every archived baseline field after
normalizing JSON tuple/list serialization. No numeric tolerance is used to hide
trade differences. Official funding assigns 1,200 events to the complete
4,800-candle grid without delay.

There are 48 passing offline tests in both the working tree and a fresh source
extraction. The annotation/accounting module covers all 76 statements and all 26
branches. Tests plus the real nine-case replay cover 192/193 statements and 59/60
branches across the two new scripts; only the direct-module entry guard is
unexecuted by the imported harness. The 5,010-member archive is hash-verified,
and its report exactly matches the working-tree report. Ruff, formatting,
project-file/function size, annotations and public docstrings pass.

Implementation revision: `51ce1a4`. Evidence directory in the primary repository:
`data/logs/research/bidirectional_cohort/v89_spcx_crossing_composition_20260908_v1`.
The journal pins input hashes, protocol, source archive, reports, test results,
coverage, runtime versions and this review. No live settings, deployment, orders
or processes were changed by the study.

## Disposition and next investigation

Defer any crossing-composition filter. Do not sweep the threshold or reinterpret
the four-trade result as validation of the opposite filter. A future proposal
needs an independently specified forward window with both groups represented,
realistic execution evidence, and a full chronological simulation of how changed
entry admission affects later positions. A successful independent replication
with adequate group counts and stable cost-adjusted effects would update this
decision; changed input hashes or baseline mismatches would invalidate this
report's technical reproduction claim.

The highest-value next investigation is current-run BTC/ETH/SOL/HYPE opportunity
attribution: bind source inputs, setup conditions and routing dispositions to
distinguish scarce qualifying setups from eligible but unexecuted signals. Review
prior journal decisions before proposing any parameter experiment. The locked
SNDK/Brent prospective experiment remains unread until its fixed end date.

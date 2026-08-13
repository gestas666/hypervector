# Flow-exhaustion development review

## Decision

The five-minute BTC/SOL aggressive-flow exhaustion reversion mechanism is
rejected after its single frozen development pass. This is a report-only result
and grants no execution authority.

Confidence is high that this exact mechanism failed the measured development
window: the replay produced valid causal evidence, zero liquidation, and zero
technical lifecycle rejection, yet failed every cadence and economic criterion.
Confidence is low that the result says anything about all possible order-book
strategies; the test covered one specifically preregistered conjunction.

## Evidence

| Metric | Nominal 13 bps | Stress 20 bps |
|---|---:|---:|
| Completed trades | 16 | 16 |
| Trades/day over 177 days | 0.0904 | 0.0904 |
| Net PnL from $15,000 | -$191.91 | -$272.07 |
| Profit factor | 0.284 | 0.180 |
| Wins/losses | 3/13 | 2/14 |
| Maximum drawdown | -1.28% | -1.81% |
| Liquidations | 0 | 0 |
| Impacted-lifecycle gaps | 0 | 0 |

Longs were 1/7 and lost `$150.57`; shorts were 2/6 and lost `$41.34`. BTC lost
`$89.33`, while SOL lost `$102.58`. The two SOL short targets were insufficient
to offset fourteen stops or maximum-hold outcomes across the portfolio.

The signal funnel evaluated 48,959 post-warmup bars per asset. BTC produced six
entries and SOL ten. Roughly 97% of evaluated bars failed the frozen shock
threshold; the remaining flow-reversal and book-replenishment conjunction
reduced cadence further. This attribution explains sparsity but does not justify
relaxing the thresholds after seeing outcomes.

## Data and implementation validation

- BTC and SOL each contain one missing five-minute bar at
  `2025-08-23T08:50:00Z`. Rolling history resets after the gap and re-earns all
  2,016 prior bars; no interpolation is used.
- Some final one-minute buckets contain zero public trades. Those rows are an
  explicit `final_flow_unavailable` blocker rather than malformed input or an
  inferred reversal.
- One-minute gaps outside a completed lifecycle do not invalidate unrelated
  trades. A lifecycle that crosses a missing minute is rejected explicitly.
- Funding uses exact Hyperliquid history rows. Fees, adverse slippage, isolated
  liquidation, pessimistic barrier ordering, one position per symbol, and
  shared-capital scaling are retained.
- The JSON and five Parquet sidecars are immutable and include SHA-256 evidence.

Focused verification at publication was 21 passing flow-exhaustion tests and a
clean Ruff check over the new modules and command surface. Broader repository
verification remains a separate completion requirement.

## Falsifier and next action

A separately preregistered mechanism could update the broader conclusion if it
shows adequate cadence and positive net expectancy under the same nominal and
stress costs. It cannot rehabilitate this exact mechanism by weakening the
observed shock, flow, or replenishment thresholds.

The next bounded experiment changes the unit of alpha from a single-asset event
to a paired portfolio residual. It will test point-in-time cointegration and
mean reversion across BTC, ETH, SOL, and HYPE with both legs, funding, turnover,
and shared-symbol conflicts represented explicitly. ML remains annotation-only.

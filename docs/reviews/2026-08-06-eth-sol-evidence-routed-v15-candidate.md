# ETH/SOL evidence-routed v15 candidate

Date: 2026-08-06 EDT / 2026-08-07 UTC

## 1. Systems decision

Freeze, but do not activate,
`multi_asset_bidirectional_eth_pullback_sol_range_candidate_v15` as the next
bounded shared-account hypothesis. It routes only two independently sourced,
bidirectional mechanisms:

- ETH precompression pullback at a $25 notional cap; and
- SOL range onset at a $75 notional cap.

BTC Hulk, canonical HYPE breakout, source-follow, and every cross-asset HYPE
breakout transfer remain observable but have no execution scope in this
candidate. The authorized v14 runtime, open SOL position, stop, and process are
unchanged. The candidate has no execution authority and is not staged.

## 2. Why this composition

The TUI's pooled all-live HYPE row combines unlike profile and exit contracts.
It is useful account history, but it is not current-contract evidence. The
current checkpoint separates the relevant observations:

| Mapping | Evidence | Result | Assessment |
|---|---|---|---|
| HYPE breakout / pooled live | 9 mixed-profile closes | +$1.27, PF 2.14 | Account history only |
| HYPE breakout / compatible deployed contract | 2 closes | 0W/2L, -$0.89, PF 0 | Negative, very sparse |
| HYPE one-blocker forward challenger | 2 resolved deployable paths | 1W/1L, -27.23 bps, PF 0.27 | Negative, short-only, one pending |
| HYPE breakout transfer / SOL | 854 development + 162 opened-final trades | PF 0.83 and 0.63 | Negative in both blocks |
| HYPE breakout transfer / ETH | 797 development + 154 opened-final trades | PF 0.84 and 0.82 | Negative in both blocks |
| ETH precompression pullback | 282 development + 56 opened-final trades | PF 1.11 and 1.12 | Positive but thin and selected |
| SOL range onset | 42 clean-block trades | long PF 2.96; short PF 4.58 | Positive but rare-winner dependent |

The prior three-mechanism BTC Hulk/HYPE breakout/ETH pullback shared-portfolio
replay was negative in development and the opened final block. Removing Hulk
and HYPE from candidate execution isolates the two mappings whose historical
blocks remain positive rather than asking one positive component to rescue two
contradictory or negative components.

Confidence is low. This is a falsifiable candidate-selection decision, not a
profitability claim.

## 3. Frozen entry, exit, and risk contracts

### ETH

- Entry clock: completed one-minute evaluation of a fresh completed five-minute
  breakout onset.
- Direction: completed-hour SMA10/SMA30 structural side; long and short remain
  enabled.
- Entry context: prior 15-minute BBWP minimum at or below 40 and a nonpositive
  directional candle body.
- Execution: taker IOC no more than 60 seconds after the decision.
- Exit: 60-bps venue-protective stop or fixed 12-hour maximum hold; no target.
- Size: $25 maximum notional, isolated 5x, approximately $5 margin at the cap.

### SOL

- Entry: range-onset provider's completed decision; long and short remain
  enabled.
- Execution: taker IOC no more than 60 seconds after the decision.
- Exit: 60-bps venue-protective stop or fixed 48-hour maximum hold; no target.
- Size: $75 maximum notional, isolated 5x, approximately $15 margin at the cap.

The two caps imply at most $100 simultaneous notional and approximately $20
isolated margin, or about 4% of a $500 account before venue variation. At the
caps, a 60-bps stop plus the existing 13-bps round-trip fee-and-slippage model
is approximately $0.18 for ETH and $0.55 for SOL before stop gaps and funding.
This is research-canary geometry, not the final aggressive allocation.

## 4. Expected cadence and what remains unknown

ETH produced 338 historical trades across 365 days, approximately 0.93 per day.
SOL produced 42 trades across 201 covered days, approximately 1.5 per week.
Their simple historical sum is approximately 1.14 opportunities per day before
occupancy, routing conflicts, feed gaps, and live arrival timing. This is not a
forward frequency guarantee.

The exact two-component shared-portfolio replay has not yet been published.
Live IOC fills, latency, stop gaps, funding, and the interaction of overlapping
ETH/SOL holds therefore remain unresolved. A candidate config alone does not
prove that the portfolio works.

## 5. Validation and falsifiers

Before any activation decision:

1. Replay exactly these two frozen contracts chronologically on one account,
   retaining every trade and modeled cost without tuning either component.
2. Verify one-position-per-coin, maximum-position, isolated-margin, stop, and
   entry-age behavior through the production config loader and collector tests.
3. Wait for the current v14 portfolio to become venue-flat and order-free.
4. Review the terminal SOL lifecycle and the pending HYPE challenger without
   changing their predeclared contracts.
5. If activation is later authorized, use a fresh verified prestart backup and
   treat every after-cost live close as journal evidence, including missed
   opportunities and execution friction.

The economic hypothesis is weakened by a joint replay with net PnL at or below
zero or PF at or below one in both chronological blocks, one trade dominating
the positive result, or live friction consuming the thin ETH surplus. It is
also weakened if fresh long and short outcomes do not both contribute over
time. These are reported trial results and review triggers, not implicit
automatic execution gates.

The implementation hypothesis is falsified by any provider/symbol mismatch,
single-sided declaration, stale entry, duplicate same-coin position, missing
venue stop, incorrect maximum hold, unexpected route outside ETH/SOL, profile
identity mismatch, or incomplete telemetry.

## 6. Current validation state

- Three v15 config/collector contract tests pass.
- Both enabled provider-symbol mappings declare long and short.
- The active v14 backend remains separate and unchanged.
- No order, position, stop, target, process, or execution scope was changed by
  creating this candidate.

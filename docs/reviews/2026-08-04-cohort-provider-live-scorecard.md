# Cohort provider live scorecard

**Observed:** 2026-08-04 03:59 EDT  
**Scope:** compatible-profile closed venue lifecycles plus current provisional
open-position context  
**Authority:** report only; no order, routing, sizing, pause, or exit authority

## Problem restatement

Portfolio totals and strategy-only totals could not distinguish the same
strategy across coins. Pair totals then still concealed long-versus-short
asymmetry. The required output is an exact, backend-authored performance sample
for every `strategy_id|symbol`, with optional complete side partitions and no
implicit balance or performance gate.

## Implemented evidence contract

- `trade_reflections.performance.by_provider_symbol` contains exact resolved
  trade economics for each strategy and coin.
- Each fully attributed pair includes `by_side.long` and/or `by_side.short`.
- The live strategy scorecard projects the pair total and side summaries.
- Rust rejects malformed economics, non-long/short identities, zero-trade side
  summaries, a claimed identifiable outcome without its summary, and side
  aggregates that do not reconcile to the pair total.
- Observer mode contains no execution outcomes.
- `performance_gate=false` and `balance_gate=false` are explicit.

## Current resolved sample

| Provider and coin | Side | W/L | Net PnL | Profit factor |
|---|---:|---:|---:|---:|
| Hulk / BTC | Long | 1/0 | +$0.133813 | N/A, no loss |
| HYPE breakout / HYPE | Long | 2/1 | +$0.772171 | 4.4485 |
| HYPE breakout / HYPE | Short | 1/0 | +$0.232488 | N/A, no loss |
| Source-follow / BTC | Long | 0/1 | -$0.124134 | 0.0000 |
| Source-follow / BTC | Short | 1/0 | +$0.135163 | N/A, no loss |
| Range-onset / ETH | Long | 0/1 | -$0.174380 | 0.0000 |

Aggregate compatible history is eight closed trades, five wins, three losses,
and `+$0.975121` net after recorded fees and funding. This is descriptive and
does not establish durable edge.

## Current open lifecycle

HYPE breakout is long `0.45` from `54.625`. The entry was recorded on a 5m
`BREAKOUT` onset with 1m and 15m `TREND_UP`, structural direction long, and
entry structure-support score `1.0`. Venue stop OID `509645916595` is at
`54.188`; isolated liquidation is `46.0239976608`. Open PnL remains provisional
and is excluded from the closed scorecard.

## Recommendation and uncertainty

Retain both directions and the current live sizing while this lifecycle and
subsequent signals accumulate. Do not infer that HYPE short is superior from
one trade, or that source-follow long is defective from one loss. The exact
split now makes later allocation revisions falsifiable without suppressing
trades during evidence collection.

Confidence is high that the recorded counts and economics match the current
backend ledger because every pair and side reconciles to the eight-trade total.
Confidence in comparative strategy or side edge is low because each cell has
only one to three trades. Additional resolved venue lifecycles that materially
change side PnL or profit factor will update this assessment directly.

## Validation

- `uv run pytest tests/ -q -m 'not network'`: `3,225 passed`, `4 deselected`.
- `cargo test -p hypervector-tui -q`: complete suite passed.
- Release build, Ruff, Rustfmt, whitespace, 500-line file, and 50-line Python
  function checks passed.
- A production-ledger checkpoint published four exact pair summaries, complete
  side partitions, `balance_gate=false`, one protected HYPE position, and zero
  faulted assets.

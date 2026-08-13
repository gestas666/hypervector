# Swing + Heikin-Ashi + Order-Block 15m Research Plan

**Status:** Frozen before outcome evaluation.

## Problem and scope

Test a causal, bidirectional 15-minute challenger on native Hyperliquid BTC,
ETH, SOL, and HYPE perpetual candles. The source Pine scripts are indicators,
not executable strategies: Swing Auto repeats breakout-state labels and both
scripts back-plot structures that become knowable only several bars later.

The experiment is report-only. It has no runtime adapter, TUI strategy tile,
order client, model authority, or execution authority.

## Frozen data and timing

- Inputs: `data/cache/{BTC,ETH,SOL,HYPE}_1m_365d.parquet`, limited to `hl` and
  explicit `hl_gap_fill`, plus authentic hourly Hyperliquid funding histories.
- Native decision bars: complete UTC-aligned 15-minute bars.
- Development: 2025-07-28 through 2026-01-28.
- Validation: 2026-01-28 through 2026-04-28.
- Pseudo-holdout: 2026-04-28 through 2026-07-28. This period is not globally
  sealed because other project research has inspected it.
- A decision made from a completed bar may execute only at the next raw
  15-minute open. Synthetic Heikin-Ashi prices are never executable prices.

## Signal reconstruction

1. Compute recursive Heikin-Ashi OHLC. Green means HA close above HA open; red
   means below; a doji retains an open position until another exit condition.
2. Confirm a swing pivot only after its complete right-hand window. The pivot
   may be drawn on its historical source bar for diagnostics, but it cannot
   affect a decision before confirmation.
3. BUY state is raw close above the latest confirmed pivot high and fast EMA
   above slow EMA. SELL is the symmetric condition below the confirmed low.
4. Long alignment is BUY plus green HA; short alignment is SELL plus red HA.
5. Compare state re-entry with fresh-alignment-onset entry.
6. Compare HA-color-flip exit with full-alignment-loss exit.
7. Simultaneous long and short entries are retained as conflicts, not guessed.

## Development search

The frozen base grid is:

- EMA pairs: 7/21, 9/21, 9/26, 12/26, 20/50, and source-default 50/200.
- Pivot right/left lengths: 3, 5, and 8.
- Entry semantics: state and onset.
- Exit semantics: HA flip and alignment loss.

Every cell is retained. Selection uses only development results and reports
per-coin plus three chronological subfold statistics, trade counts, long/short
attribution, profit factor, drawdown, costs, funding, and liquidations. Ranking
prefers stable net results across coins/folds; it is not an execution gate.

After selecting the development base shape, compare these order-block roles:

- control: no order-block dependency;
- agreement: the most recent causally confirmed, non-invalidated block must
  agree with the entry direction;
- structural stop: baseline entry, using the latest matching active block
  boundary when directionally valid.

Order-block periods are 3 and 5 follow-through candles; displacement thresholds
are 0%, 0.25%, and 0.50%. A block becomes available only after all required
follow-through candles complete. Bullish blocks invalidate on a raw close below
their low; bearish blocks invalidate above their high.

## Execution assumptions

- Initial equity: $15,000 per independent asset screen.
- Isolated margin: 10% of current equity; leverage: 5x, below every venue cap.
- Market entry/exit fee: 4.5 bps per side.
- Adverse market slippage: 2 bps per side.
- Authentic hourly funding is applied at matching settlement timestamps.
- Liquidation uses the project Hyperliquid isolated-margin approximation and
  takes precedence when a 15-minute bar also touches a structural stop.
- One position per coin, one-bar re-entry cooldown, no invented maker fill.

Nominal friction is therefore 13 bps round trip before funding. A stress replay
uses 20 bps round trip. One-bar delayed entry is also retained.

## Validation and decision

Freeze the development-selected base/order-block variant before validation.
Run nominal, stress-cost, and one-decision-bar-delay variants on validation and
pseudo-holdout. Report all outcomes even when sparse, losing, or liquidated.

A strategy-observer proposal is warranted only if both sides trade, economics
are positive after nominal costs, no liquidation occurs, results are not
dependent on one coin or one fold, and the sign survives either delayed entry
or stressed friction. These are recommendation criteria, not implicit trial
abort conditions under `SRS_HV1_NO_GATES`.

## Required tests and evidence

- HA recursion and doji behavior.
- Pivot confirmation timing and immunity to future data before confirmation.
- Repeated breakout state versus one-shot onset.
- Order-block detection availability, displacement, and invalidation.
- Entry/exit semantics for both directions.
- Next-bar execution and no HA-price fills.
- Exact source/funding identity, immutable JSON artifact, and complete cell
  retention.

## Confidence and falsifier

**Confidence: high that the translation can be made causal; low that it has an
edge before measurement.** The repeated labels in the screenshot are explained
by the source code, while future-confirmed back-plots are a material visual
failure mode. Any test showing a pivot/block affects a prior decision invalidates
the implementation. Negative or unstable post-cost validation rejects the
strategy configuration without invalidating the source indicators themselves.

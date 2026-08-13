# Hypervelocity Source Recipe C-Only Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Measure pinned Hypertrader Recipe C as an independent countertrend-long strategy under corrected maker freshness and authentic Hyperliquid execution evidence.

**Architecture:** Add a report-only source event family that selects only exact `fade_td_eu` events from the pinned B/C extractor. Preserve every Recipe C field and reuse the existing 60-second maker eligibility, 100-bps signal-range ceiling, and all portfolio/execution assumptions. Replay all three fill models from a fresh $10,000 portfolio rather than subtracting Recipe B from a shared path.

**Tech Stack:** Python 3.13, pandas, pytest, pinned Hypertrader labels, verified 0xArchive Hyperliquid L2/trades, authentic mark/oracle/funding context.

---

## Frozen contract

- Select only exact source `fade_td_eu` events: `TREND_DOWN` onset, EU 07:00-16:00 UTC, long, 24-hour maximum hold.
- Do not alter source confidence, session, onset, side, or hold logic.
- Use 60-second signal eligibility/maker TTL and the pre-existing 100-bps completed-5m range ceiling.
- Preserve one BTC position, 70% isolated allocation, 40x leverage, 8% target, venue fees, authentic funding, mark/oracle liquidation, and no stop.
- Run touch, book-through, and public-trade-through over development and fresh windows; retain all results.
- Runtime, TUI, faithful config, and ML observe-only authority remain unchanged.

## Task 1: Add exact C-only extraction with TDD

**Files:**
- Modify: `tests/test_hypervelocity_selective_recipe_replay_script.py`
- Modify: `src/hypervector/research/hypertrader_source_adapter.py`

1. Add a failing test proving B is excluded while every C field remains identical.
2. Implement the smallest typed wrapper over the exact pinned extractor.
3. Run focused tests and Ruff.

## Task 2: Add one report-only family with TDD

**Files:**
- Modify: `tests/test_hypertrader_recipe_maker_script.py`
- Modify: `scripts/hypervelocity_hypertrader_maker_replay.py`

1. Add failing parser, contract, and routing tests for `source-fade-only`.
2. Expose an explicit exact-source C-only event policy.
3. Preserve every existing candidate family byte-for-byte at the event-routing boundary.
4. Run focused tests and Ruff.

## Task 3: Execute and validate

1. Replay touch, book-through, and public-trade-through into new immutable artifacts.
2. Verify source/config hashes, lifecycle accounting, fees, funding, equity, drawdown, and fresh coverage.
3. Compare with C's shared-path contribution and the one-sided short leader.
4. Record confidence, limitations, and falsifiers. Keep runtime unchanged.

## Planned artifacts

- `data/logs/research/hypertrader_v2_source_fade_only_ttl60_range100_touch_replay_20260728.json`
- `data/logs/research/hypertrader_v2_source_fade_only_ttl60_range100_through_replay_20260728.json`
- `data/logs/research/hypertrader_v2_source_fade_only_ttl60_range100_trade_through_replay_20260728.json`

## Decision standard and risks

- Development profitability is final equity above $10,000 after modeled costs under each fill assumption; it is reported rather than used as an execution abort gate.
- Consistency requires positive C-only PnL under touch, through, and trade-through; otherwise the edge is fill-model-dependent.
- Drawdown and liquidation count remain first-class results even if final equity is positive.
- The fresh window currently has no Recipe C event, so no promotion can follow from this run alone.
- Private queue rank, hidden liquidity, and true local latency remain unobserved.

## Measured result

The dedicated C-only portfolio is positive under two fill assumptions and
slightly negative under one:

| Fill | Targets / liquidations | Final equity | Maximum drawdown |
|---|---:|---:|---:|
| Touch | 45 / 4 | $10,656.40 | -67.68% |
| Book-through | 43 / 4 | $9,710.86 | -69.14% |
| Public-trade-through | 25 / 2 | $10,229.80 | -54.26% |

This validates Recipe C as an independent, near-breakeven-to-positive long
module rather than the combined B/C loss. It does not meet the frozen
cross-model consistency standard and has substantial development drawdown.
Fresh Jul 27 contains no Recipe C event, so forward confidence remains low.

The transferred 100-bps signal-range ceiling filtered one C event at 107.39
bps. That ceiling was discovered on the trend-aligned short path, not on C.
A no-ceiling C-only control is therefore required to measure whether the
filter helps or harms rather than presuming it transfers across direction.

Artifact SHA-256 values:

- Touch: `e19718ca940e3b294ebd0c76435f9bc24503e08e8f94ed4ac1e8c15db5b75b62`
- Book-through: `446d5efaa402ddad47ad41f5158687c5afc6757934698dd4bbd22516d897d411`
- Public-trade-through: `34ac1af9a3521ca3d56f831dea19b66108070b1fe408f2ea09183d557503fba8`

Confidence is medium that C contains a small development edge and low that it
is externally durable. A filled forward C event, cross-model agreement, and a
material reduction in drawdown without post-hoc gates would increase it.

# Hypervelocity Source-Fade Freshness Replay Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Test the exact pinned Hypertrader countertrend long recipe with corrected 60-second maker freshness and the already-declared 100-bps signal-shock annotation.

**Architecture:** Use the existing `baseline` event family without code changes: source Recipe B is Asia `BREAKOUT/BK_UPWARD` long/4h and source Recipe C is EU `TREND_DOWN` onset long fade/24h. Change the prior baseline replay only from 300-second to 60-second signal eligibility/maker TTL and apply the explicit completed-5m range ceiling already measured in the trend-aligned experiment. Replay touch, book-through, and public-trade-through independently.

**Tech Stack:** Existing Python replay CLI, pinned Hypertrader labels, verified 0xArchive Hyperliquid L2/trades, authentic Hyperliquid mark/oracle/funding context.

---

## Frozen contract and evidence boundary

- Preserve exact pinned Recipe B and Recipe C directions, sessions, confidence rule, onset semantics, and 4h/24h maximum holds.
- Use 60 seconds for both signal eligibility and maker TTL.
- Use the already-declared 100-bps completed-5m high-low range ceiling; do not tune it for fade outcomes.
- Preserve one BTC position, 70% isolated allocation, 40x leverage, fixed 8% gross-margin target, maker behavior, venue fees, authentic funding, mark/oracle liquidation, and no stop.
- Run and retain touch, one-tick book-through, and public-trade-through results over the full development and fresh windows.
- Compare with the prior 300-second exact-source baseline and the profitable trend-aligned short leader.
- Runtime, TUI, faithful config, and ML observe-only authority remain unchanged.

## Execution tasks

1. Run `baseline`, 60-second eligibility, 100-bps range ceiling, and touch fill into a new immutable artifact.
2. Repeat with book-through and public-trade-through using identical input hashes.
3. Verify event/exclusion/lifecycle accounting, source hashes, funding, fees, equity, drawdown, and per-recipe outcomes.
4. Report which prior 300-second fills disappear and whether any liquidation remains.
5. Record the result here, in the source-fidelity audit, and in `HANDOFF.md`.
6. Keep the candidate report-only. A filled independent forward long is required before promotion regardless of development PnL.

## Planned artifacts

- `data/logs/research/hypertrader_v2_source_fade_ttl60_range100_touch_replay_20260728.json`
- `data/logs/research/hypertrader_v2_source_fade_ttl60_range100_through_replay_20260728.json`
- `data/logs/research/hypertrader_v2_source_fade_ttl60_range100_trade_through_replay_20260728.json`

## Risks and falsifiers

- The 100-bps ceiling was discovered on the trend-aligned development path and may not transfer to fades.
- Source Recipe C's July 11/11 display is selected development output, not forward evidence.
- A high target rate can remain economically negative when rare 40x liquidations dominate.
- Profit under only one fill assumption is execution-model-dependent.
- Non-positive equity, a remaining liquidation tail, or negative fade-long PnL across assumptions falsifies corrected freshness as a sufficient repair.

## Measured result

Corrected freshness materially improved the original 300-second B/C baseline,
but the combined recipe remained unprofitable under every fill assumption.

| Fill | Recipe C targets / liqs | Recipe C net trade PnL | Combined final equity | Max drawdown |
|---|---:|---:|---:|---:|
| Touch | 45 / 4 | +$505.30 | $7,330.26 | -67.68% |
| Book-through | 43 / 4 | -$427.96 | $6,655.03 | -69.14% |
| Public-trade-through | 25 / 2 | +$229.80 | $7,010.67 | -54.26% |

The separate Recipe B arm canceled one development intent and completed one
four-hour time exit, losing approximately $2,917-$3,219 depending on fill
assumption. The fresh Jul 27 event was Recipe C: its long-fade maker intent
canceled under all three fill assumptions. A later same-timestamp short-follow
control filled and reached its target, so this event was available but did not
validate the source fade direction.

Recipe C is therefore near breakeven across execution assumptions but not yet
proven profitable. Because the pinned upstream surface presents B and C as
independent frozen recipes, a dedicated C-only stateful replay is warranted.
It must be recomputed rather than inferred by subtracting Recipe B PnL because
removing B changes compounding, fill capacity, funding, and portfolio
availability.

Artifact SHA-256 values:

- Touch: `3e8ecaa94fc6e1e832f984c0b24adeafc0591adf383426e245506fa29fcc0a7f`
- Book-through: `b4bb0f9891b17db16d873603176e9f2784be7cad0abff55faa21c71c9dcb5b2d`
- Public-trade-through: `3d20dd34e40d1c27310da057e5036bb4dccacaa2ac1163fb1772204fa4310020`

Confidence is high that corrected freshness is insufficient for combined B/C.
Confidence that C alone has a small positive edge is low until the dedicated
stateful replay completes and remains consistent across fill assumptions.

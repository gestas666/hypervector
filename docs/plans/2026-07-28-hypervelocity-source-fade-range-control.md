# Hypervelocity Source Recipe C Range-Control Replay Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Determine whether the transferred 100-bps signal-shock ceiling helps or harms exact Recipe C.

**Architecture:** Replay the completed C-only candidate with the identical event stream, 60-second maker freshness, and portfolio/execution contract, but omit `--maximum-signal-range-bps`. Compare every lifecycle against the range100 artifacts under touch, book-through, and public-trade-through. No implementation change is required.

**Tech Stack:** Existing Python replay CLI, pinned Hypertrader labels, verified 0xArchive Hyperliquid L2/trades, authentic mark/oracle/funding context.

---

## Frozen contract

- Exact source Recipe C only: EU `TREND_DOWN` onset, long, 24-hour hold.
- Signal eligibility and maker TTL remain 60 seconds.
- Remove only the transferred completed-5m 100-bps range ceiling.
- Preserve 70% isolated allocation, BTC 40x, 8% target, one position, maker behavior, fees, funding, mark/oracle liquidation, and no stop.
- Run all three fill assumptions and retain all outcomes.
- Runtime, TUI, faithful config, and ML observe-only authority remain unchanged.

## Planned artifacts

- `data/logs/research/hypertrader_v2_source_fade_only_ttl60_touch_replay_20260728.json`
- `data/logs/research/hypertrader_v2_source_fade_only_ttl60_through_replay_20260728.json`
- `data/logs/research/hypertrader_v2_source_fade_only_ttl60_trade_through_replay_20260728.json`

## Decision standard and falsifiers

- Compare exact event status substitutions, final equity, drawdown, fees, funding, and liquidation count with range100.
- If the restored event worsens outcomes across assumptions, retain range100 as a development-derived annotation only.
- If it improves or leaves outcomes unchanged, reject range100 for C to avoid unsupported overfiltering.
- Either result remains development evidence; the fresh window has no C event.

## Measured result

The no-ceiling control improved exact Recipe C under every fill model. Starting
from $10,000, touch ended at $11,163.56, book-through at $10,173.02, and public
trade-through at $10,229.80. The corresponding range100 results were
$10,656.40, $9,710.86, and $10,229.80. The restored high-range event completed
at target under touch and through; it canceled under trade-through.

The transferred 100-bps ceiling is therefore rejected for Recipe C. This is
development evidence only: the fresh Jul 27 window contains no Recipe C event.
Runtime, TUI, faithful configuration, and ML observe-only authority remain
unchanged.

Artifact SHA-256 values:

- touch: `5c154bb6d2d467937325f791f99187944fd170c0402cda5f3e9d8dd8ebbf358b`
- through: `c4d214ca3e8b15b5912fe7df568c23f3ba6956b719c91a26893e2dead4c91ad8`
- trade-through: `403d821c8a36463f0c2407b6175fe2380aba58accad640d8bc3c12eaf3135b24`

# Hypervelocity Symmetric Trend-Onset Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Test whether adding a mirrored EU `TREND_UP` long onset to the profitable report-only EU `TREND_DOWN` short arm produces a selective, two-sided Hypervelocity candidate under authentic Hyperliquid execution evidence.

**Architecture:** Preserve the pinned Hypertrader Recipe B Asia breakout arm and the existing experimental trend-aligned Recipe C short arm. Add only the symmetric EU `TREND_UP` onset as a long event, then replay the resulting event pulses with the already-measured 60-second maker eligibility and 100-bps completed-5m signal-range ceiling under touch, book-through, and public-trade-through fills. Runtime, faithful configuration, TUI, and ML authority remain unchanged.

**Tech Stack:** Python 3.13, pandas, pytest, pinned Hypertrader labels, verified 0xArchive Hyperliquid L2/trades, authentic Hyperliquid mark/oracle/funding context.

---

## Frozen contract and evidence boundary

- Development window: 2026-04-28 through 2026-07-26 UTC.
- Fresh window currently available: 2026-07-27 UTC. It remains a very small forward check, not a promotion set.
- Pinned upstream revision: `ad15f2bdc949619be495a5f516babd08f7f52a90`.
- Preserve Recipe B exactly: confirmed `BREAKOUT/BK_UPWARD` onset, confidence at least 0.6, Asia 00:00-08:00 UTC, long, four-hour maximum hold.
- Preserve the existing experimental C correction: `TREND_DOWN` onset, EU 07:00-16:00 UTC, short, 24-hour maximum hold.
- Add one mirrored arm: `TREND_UP` onset, EU 07:00-16:00 UTC, long, 24-hour maximum hold.
- An onset is emitted only when `primary_code` changes into the state. Persistent trend bars cannot repeatedly submit entries.
- Use 60 seconds for both signal eligibility and maker TTL.
- Retain the 100-bps completed-5m high-low signal-range ceiling as an explicit development-derived shock control.
- Run touch, one-tick book-through, and public-trade-through fills. Retain every technically valid result.
- Preserve one BTC position, 70% isolated allocation, 40x leverage, fixed 8% gross-margin target, venue fees, authentic funding, mark/oracle liquidation, and no stop.
- Keep ML in observe-only mode. Do not change runtime, TUI, or `configs/hypervelocity_faithful.toml`.

## Task 1: Define symmetric source events with TDD

**Files:**
- Modify: `tests/test_hypervelocity_selective_recipe_replay_script.py`
- Modify: `src/hypervector/research/hypertrader_source_adapter.py`

1. Add a failing test with `BREAKOUT/BK_UPWARD`, `TREND_UP`, and `TREND_DOWN` transitions inside and outside their UTC sessions.
2. Require the extracted rows to preserve Recipe B and emit exactly `follow_tu_eu/long` and `follow_td_eu/short` for EU trend onsets.
3. Require decision availability exactly five minutes after the label timestamp and preserve the 4h/24h hold contracts.
4. Run the specific test and confirm it fails because the symmetric extractor is absent.
5. Implement the smallest typed extractor using the existing validation and onset helpers.
6. Run the focused adapter tests and Ruff.

## Task 2: Expose one report-only candidate family with TDD

**Files:**
- Modify: `tests/test_hypertrader_recipe_maker_script.py`
- Modify: `scripts/hypervelocity_hypertrader_maker_replay.py`

1. Add a failing parser/contract test for `symmetric-trend-aligned`.
2. Require the report contract to disclose the symmetric event policy, 60-second eligibility, selected fill rule, 100-bps range annotation, observe-only model authority, and `runtime_strategy_changed=false`.
3. Add a failing unit test proving the script selects the new extractor before signal-range annotation.
4. Implement the minimal candidate routing without altering existing baseline, margin-stop, trend-aligned, or TTL-grid results.
5. Run focused script/adapter tests and Ruff.

## Task 3: Replay all three fill assumptions

**Files:**
- Create: `data/logs/research/hypertrader_v2_symmetric_trend_ttl60_range100_touch_replay_20260728.json`
- Create: `data/logs/research/hypertrader_v2_symmetric_trend_ttl60_range100_through_replay_20260728.json`
- Create: `data/logs/research/hypertrader_v2_symmetric_trend_ttl60_range100_trade_through_replay_20260728.json`

1. Replay the exact development and fresh windows with `--entry-eligibility-seconds 60` and `--maximum-signal-range-bps 100`.
2. Run each fill rule independently against the same verified source labels, candles, archive bundles, mark/oracle context, and funding context.
3. Retain events, exclusions, submissions, fills, expirations, targets, liquidations, timeouts, funding, fees, final equity, maximum drawdown, and lifecycles.
4. Compare the symmetric candidate with the corresponding already-retained one-sided candidate under the same fill assumption.

## Task 4: Validate the mechanism and record the decision

**Files:**
- Modify: `docs/plans/2026-07-28-hypervelocity-symmetric-trend-onset.md`
- Modify: `docs/reviews/2026-07-28-source-fidelity-runtime-audit.md`
- Modify: `HANDOFF.md`

1. Verify event counts by recipe and side, filtered counts, lifecycle accounting, fee/funding arithmetic, artifact hashes, and source hashes.
2. Report long and short outcomes separately so one side cannot hide the other.
3. Run focused tests, task-scoped Ruff/format, full non-network Python tests, Rust TUI tests, diff hygiene, and file/function-size checks.
4. Keep the candidate report-only. Promotion requires a separately frozen forward window with both long and short opportunities and no material execution-model contradiction.

## Success criteria, risks, and falsifiers

- Development profitability requires final equity above $10,000 after modeled costs under each fill assumption; this is a result, not an execution gate.
- Evidence improves if the two-sided candidate stays profitable across touch, through, and trade-through and does not rely entirely on one side or one date cluster.
- The candidate is weakened by a losing long arm, materially worse drawdown than the one-sided control, profit isolated to one fill rule, or broad lifecycle substitution.
- The 100-bps shock ceiling was discovered on the development window and may overfit; an independent shock event below 100 bps that liquidates, or a profitable event above 100 bps, would update it.
- Public L2 cannot reconstruct private queue position, partial maker priority, hidden liquidity, or genuine local latency. Fresh shadow/live-paper comparison is required before promotion.
- The creator’s application may use different private entry timing than the public Hypertrader research recipes. Complete creator entry/no-entry logs would supersede this inference.

## Rollback

This experiment adds only a report-only extractor, script option, tests, documents, and immutable result artifacts. Removing those additions restores the prior research surface; runtime and configuration need no rollback because they are not modified.

## Measured result

Completed against the full 2,160-hour development archive and the fresh Jul 27
archive. The candidate emitted 154 development events: 76 added EU
`TREND_UP` longs, 76 EU `TREND_DOWN` shorts, and two source Recipe B longs.
One short event was explicitly excluded by the predeclared 100-bps signal-range
ceiling. Results:

| Fill assumption | Targets | Liquidations | Time exits | Final equity | Maximum drawdown |
|---|---:|---:|---:|---:|---:|
| Touch | 81 | 9 | 2 | $3,421.74 | -87.37% |
| Book-through | 78 | 8 | 2 | $4,749.41 | -87.15% |
| Public-trade-through | 47 | 6 | 2 | $2,885.95 | -84.39% |

Under public-trade-through, the added EU long arm produced 16 targets, six
full liquidations, and one 24-hour time exit. Together with the unchanged
Recipe B time exit, longs contributed approximately -$15,723.78 net trade
PnL; shorts contributed approximately +$8,609.73. The one-sided control under
the same strict assumption retained 20/20 targets, $25,600.17 final equity,
and -32.50% maximum drawdown.

The fresh Jul 27 window contained one additional long event, but its maker
intent canceled; the existing short completed its target. Fresh equity was
therefore unchanged at $10,476.87. This is not an independent two-sided test.

Artifact SHA-256 values:

- Touch: `690938cb6cbe1586b350530545da2fc68e48d2c30e7bc257c9b2a13d855ac107`
- Book-through: `27a308522219aaecb818f274fe7ea1b137cfc4cb92fa7f2cf250db518f124b97`
- Public-trade-through: `1816db610322b8e097570587510d2528497e8bb8b01ae8a18b1cff70e9c9203f`

The exact symmetric 24-hour long arm is rejected. Confidence is high that it
does not improve the one-sided research leader under the frozen replay
assumptions. External confidence remains medium because public replay cannot
observe private queue rank and the fresh set contains no filled long. Four of
the six strict-fill long liquidations occurred after four hours, while two
occurred within 70 minutes. A separately frozen four-hour long horizon is a
source-grounded follow-up, but it cannot be presumed sufficient.

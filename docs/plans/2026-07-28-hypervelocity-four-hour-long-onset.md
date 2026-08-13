# Hypervelocity Four-Hour Long-Onset Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Determine whether limiting the mirrored EU `TREND_UP` long arm to the source-grounded four-hour Recipe B horizon removes stale long liquidations while preserving the profitable EU short arm.

**Architecture:** Use the completed symmetric trend-onset candidate as the exact control and change only `follow_tu_eu.maximum_hold_seconds` from 86,400 to 14,400. Recipe B remains long/four-hour; `follow_td_eu` remains short/24-hour. Replay the new report-only event stream under touch, book-through, and public-trade-through against identical verified evidence.

**Tech Stack:** Python 3.13, pandas, pytest, pinned Hypertrader labels, verified 0xArchive Hyperliquid L2/trades, authentic mark/oracle/funding context.

---

## Frozen hypothesis and invariants

- Four of six strict-fill EU long liquidations in the 24-hour control occurred after four hours; two occurred within 70 minutes.
- The four-hour value is not optimized from those durations. It is copied from source Recipe B's declared maximum hold.
- Change only EU `TREND_UP` long maximum hold: 24h to 4h.
- Preserve source Recipe B, EU `TREND_DOWN` short 24h, onset-only event semantics, 60-second maker eligibility/TTL, and the explicit 100-bps completed-5m signal-range ceiling.
- Preserve one BTC position, 70% isolated allocation, 40x leverage, fixed 8% gross-margin target, maker entry/target behavior, venue fees, authentic funding, mark/oracle liquidation, and no stop.
- Retain all touch, book-through, and trade-through results. Runtime, TUI, faithful TOML, and ML observe-only authority remain unchanged.

## Task 1: Define the single hold-time change with TDD

**Files:**
- Modify: `tests/test_hypervelocity_selective_recipe_replay_script.py`
- Modify: `src/hypervector/research/hypertrader_source_adapter.py`

1. Add a failing test proving the new extractor preserves every symmetric event identity, side, timestamp, and confidence.
2. Require only `follow_tu_eu` to change from 86,400 to 14,400 seconds.
3. Confirm the test fails because the extractor is absent.
4. Implement the smallest typed wrapper over the symmetric extractor.
5. Run focused tests and Ruff.

## Task 2: Expose the immutable report family with TDD

**Files:**
- Modify: `tests/test_hypertrader_recipe_maker_script.py`
- Modify: `scripts/hypervelocity_hypertrader_maker_replay.py`

1. Add a failing parser/contract test for `symmetric-trend-aligned-long4h`.
2. Require an explicit event-policy identity and unchanged report-only/model/runtime fields.
3. Add a failing `_events` routing test proving range annotation observes the four-hour value.
4. Implement minimal routing without changing prior candidate outputs.
5. Run focused tests and Ruff.

## Task 3: Replay all fill assumptions

**Files:**
- Create: `data/logs/research/hypertrader_v2_symmetric_trend_long4h_ttl60_range100_touch_replay_20260728.json`
- Create: `data/logs/research/hypertrader_v2_symmetric_trend_long4h_ttl60_range100_through_replay_20260728.json`
- Create: `data/logs/research/hypertrader_v2_symmetric_trend_long4h_ttl60_range100_trade_through_replay_20260728.json`

1. Run the development and fresh windows under touch, book-through, and public-trade-through.
2. Retain every lifecycle, exclusion, fee, funding payment, liquidation, time exit, equity path, and drawdown.
3. Compare lifecycle identities and outcomes directly with the 24-hour symmetric control and one-sided short leader.
4. Report long and short outcomes separately.

## Task 4: Validate and decide

1. Verify hashes, source identity, candidate contract, event/lifecycle accounting, and arithmetic.
2. Run focused and full non-network tests, Rust TUI tests, Ruff/format, diff hygiene, and file/function limits.
3. Record results in this plan, the source-fidelity review, and `HANDOFF.md`.
4. Keep the candidate report-only regardless of development performance. A filled long in an independent forward window is required before any promotion decision.

## Risks and falsifiers

- A four-hour timeout can crystallize a loss shortly before recovery and may replace liquidation risk with repeated moderate losses.
- Two observed long liquidations occur well before four hours; the change cannot prevent them.
- Time-exit execution is taker-like and cannot prove private creator behavior.
- Profit isolated to strict trade-through would be fill-model-dependent and insufficient.
- Non-positive equity, materially worse drawdown, or negative long PnL under all fill assumptions falsifies four-hour expiry as a sufficient repair.

## Measured result

Completed against the same 154 development events and exact source/context
hashes as the 24-hour symmetric control.

| Fill assumption | Long targets / liqs / time exits | Final equity | Maximum drawdown |
|---|---:|---:|---:|
| Touch | 29 / 2 / 13 | $3,070.07 | -85.75% |
| Book-through | 28 / 2 / 12 | $4,862.66 | -85.06% |
| Public-trade-through | 13 / 2 / 5 | $6,207.82 | -64.82% |

The four-hour horizon reduced strict long liquidations from six to two and
improved strict final equity from $2,885.95 to $6,207.82. It did not create a
long edge: strict long net trade PnL worsened from approximately -$15,723.78
to -$17,055.40, while later shorts improved to approximately +$13,263.22.
The apparent portfolio improvement came from freeing the one-position book for
later short events. Touch ended below its 24-hour control, and every fill model
remained below the $10,000 start.

Fresh Jul 27 remained unchanged: the additional long maker intent canceled and
the short completed its target. The exact four-hour follow-up is rejected as a
sufficient repair, and further hold-duration tuning is closed to avoid fitting
the same six development losses.

Artifact SHA-256 values:

- Touch: `c05489be8ffb57aa3e70b4b461df4a4b84f8611fd319a569e39112175ce0aec5`
- Book-through: `3845a5b5ab96a7a8cdcb6a0ea5c526ac345b558a7e46c159548dcf5ad4073497`
- Public-trade-through: `fb218b2d33f5661f5320bad98799429f42c1b0ba9f42d8bcb1f1a194856b67a8`

Confidence is high that this exact source-grounded horizon is insufficient
under the frozen replay assumptions. Private queue behavior and the absence of
a filled fresh long limit external confidence to medium.

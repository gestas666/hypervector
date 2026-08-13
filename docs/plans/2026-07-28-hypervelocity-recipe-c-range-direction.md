# Hypervelocity Recipe C Range-Direction Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use test-driven development task-by-task.

**Goal:** Test whether completed-5m shock size causally chooses between
trend-following short and countertrend long at the same pinned Recipe C onset.

**Architecture:** Preserve the exact current-revision Recipe C event times and
all execution/risk assumptions. Use the already-frozen 100-bps completed-bar
range boundary as a direction split: follow `TREND_DOWN` below or at the
boundary, and fade long above it. Every event remains eligible; this is not an
entry filter. Replay touch, book-through, and public trade-through separately.

**Tech Stack:** Python 3.13, pandas, pytest, immutable Hyperliquid candles,
books, public trades, marks, oracle prices, and funding.

---

## Frozen contract

- Exact confirmed Recipe C `TREND_DOWN` onsets during 07:00-16:00 UTC.
- Completed 5m high-low range divided by the same bar open is causal at the
  existing five-minute decision time.
- Range at or below 100 bps selects short follow; range above 100 bps selects
  long fade. The boundary is not tuned again.
- Preserve 60-second maker TTL, one BTC position, 70% isolated allocation,
  40x leverage, 8% gross-margin target, 24-hour maximum hold, fees, funding,
  mark/oracle liquidation, and no stop.
- Research only: no runtime, TUI, faithful configuration, or ML authority
  change.

### Task 1: Define the direction transformation

**Files:**
- Modify: `tests/test_hypervelocity_selective_recipe_replay_script.py`
- Modify: `src/hypervector/research/hypertrader_source_adapter.py`

1. Write a failing test with one 100-bps event and one event above 100 bps.
2. Verify the failure is the missing transformation.
3. Implement a typed, non-mutating transformation that retains both events,
   records `signal_range_bps`, and changes only recipe ID and side.
4. Run the focused test and adapter suite.

### Task 2: Expose one report-only replay family

**Files:**
- Modify: `tests/test_hypertrader_recipe_maker_script.py`
- Modify: `scripts/hypervelocity_hypertrader_maker_replay.py`

1. Write failing parser, contract, and routing tests for
   `source-range-direction`.
2. Verify the candidate requires candle evidence and an explicit split.
3. Add the smallest routing change while keeping the script below 500 lines.
4. Run focused tests, Ruff, formatting, and file-size checks.

### Task 3: Execute the frozen comparison

1. Run touch, one-tick book-through, and public trade-through over the exact
   development and later forward windows.
2. Retain immutable artifacts and verify lifecycle accounting, hashes, fees,
   funding, liquidation, equity, drawdown, and 30-day chronology.
3. Compare against always-follow range100 and exact no-ceiling fade controls.
4. Reject the selector if its advantage is isolated to optimistic fills, if a
   direction arm has no resolved evidence, or if chronology remains dominated
   by one event.

### Task 4: Document and verify

1. Record result, confidence, risks, and falsifiers in the source-candidate
   review and `HANDOFF.md`.
2. Run all focused replay tests and `git diff --check`.
3. Keep runtime and the active shadow process unchanged.

## Measured result

The frozen candidate completed on the exact current-revision event population.
It improved the two optimistic fill assumptions and was identical to the
short-only control under public trade-through:

| Fill assumption | Short-only control | Range-direction | Difference | Long result |
|---|---:|---:|---:|---|
| Touch | $23,366.73 | $24,478.79 | +$1,112.06 | 1 target |
| One-tick through | $35,678.79 | $37,376.80 | +$1,698.01 | 1 target |
| Public trade-through | $25,600.17 | $25,600.17 | $0.00 | 1 cancellation |

Maximum drawdown was unchanged at -57.54%, -56.69%, and -32.50%. Every
fixed 30-day slice remained profitable under all three assumptions. Jul 27 and
Jul 28 each remained a short target under all fill assumptions; their completed
5m ranges were 26.47 and 20.45 bps.

The portfolio result does not validate a general direction selector. Of 25
events with a unanimous fade/follow preference across the three fill models,
the rule selected the preferred direction for only 12 (48%). Only one
consensus event exceeded 100 bps; it preferred fade and is the candidate's
sole resolved long under touch and through. Fade-preferred events otherwise
had a median range of 15.38 bps, versus 14.08 bps for follow-preferred events.

The short-only candidate therefore remains the development leader. The
high-shock fade is retained as an annotation-only hypothesis because it is
non-inferior in this replay, not as a validated long arm. A second independent
above-100-bps event that fills under public trade-through is the minimum useful
falsification point.

Artifact SHA-256:

- touch development/Jul 27:
  `9f3c1cd79f29d2535dc05391555e6a8da827fa31fb5c36d4f19783a2f6888e1b`;
- through development/Jul 27:
  `01552a31d0282d97e56b4c3e81786df9917b587896ccf93c85c75836a1ca22d3`;
- trade-through development/Jul 27:
  `e55428ccb2bc55866d5d42bb5408ca4d5634b8f2f9a837ac8e3a092a43f902e5`;
- Jul 28 touch/through/trade-through:
  `39e973f55ae52bf23ae34a046f0b2ab6306c5dbf9ab44cea07cdd12fecaf90d3`,
  `11ce7519bd181fafec7192c9d76428a6b627708b25d4f8604d57f2a9eb4877d2`,
  and
  `d6bcec47c962b774c347f862137adb5bf92291c47442e0636225047156250213`.

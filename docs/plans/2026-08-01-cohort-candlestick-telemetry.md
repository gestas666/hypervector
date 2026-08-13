# Shared Cohort Candlestick Telemetry Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the shared cohort's four Braille reference-price traces with genuine backend-authored Hyperliquid 1-minute candlestick charts for BTC, ETH, SOL, and HYPE.

**Architecture:** The existing poller already receives OHLCV frames for every symbol. It will retain a bounded tail of completed 1-minute bars in the poll result, while the backend telemetry emits an initial history and then only bars newer than the last emitted timestamp. The Rust projection will strictly validate and retain those candles, and Screen 3 will draw price-scaled wick/body panes without deriving or fabricating market data.

**Tech Stack:** Python 3.13, pandas, append-only JSONL telemetry, Rust, Serde, Ratatui 0.29, pytest, Cargo integration tests.

---

### Task 1: Lock the backend candle contract with failing tests

**Files:**
- Modify: `tests/test_multi_asset_intent_poller.py`
- Modify: `tests/test_multi_asset_cohort_telemetry.py`
- Modify: `tests/test_multi_asset_live_runner.py`

1. Assert that one poll returns a bounded, chronological set of completed 1-minute OHLCV bars for every enabled symbol.
2. Assert that telemetry emits the initial window once and suppresses duplicate bars on a later 15-second poll.
3. Assert that the runner forwards backend market bars without changing routing or execution.
4. Run the focused tests and confirm failure because `CohortIntentPoll` does not yet carry candle history.

### Task 2: Publish backend-authoritative completed candles

**Files:**
- Modify: `src/hypervector/live/multi_asset_intent_poller.py`
- Modify: `src/hypervector/live/multi_asset_cohort_telemetry.py`
- Modify: `src/hypervector/live/multi_asset_live_runner.py`

1. Add a typed immutable market-bar record with strict OHLCV and timestamp validation.
2. Extract at most 90 completed 1-minute bars from the same venue frames already used for live decisions.
3. Emit a `market_candles` ledger event containing only timestamps newer than the prior emission for each symbol.
4. Forward the bars through the runner's telemetry boundary before the account snapshot.
5. Run the focused Python tests to green.

### Task 3: Lock the Rust projection and visual contract with failing tests

**Files:**
- Modify: `crates/hypervector-tui/tests/bidirectional_cohort_view_test.rs`

1. Add backend candle fixtures for all four symbols.
2. Assert strict parsed candle history and real OHLC values.
3. Assert Screen 3 identifies backend 1-minute OHLCV, contains candle wick/body glyphs, and contains no Braille reference wording.
4. Add an old-ledger assertion that missing OHLCV is explicitly unavailable rather than inferred from marks.
5. Run the focused Rust test and confirm the new assertions fail.

### Task 4: Replace the cohort Braille charts

**Files:**
- Modify: `crates/hypervector-tui/src/backend_cohort.rs`
- Modify: `crates/hypervector-tui/src/cohort_chart.rs`

1. Parse and validate chronological `market_candles` events into a per-symbol bounded history.
2. Reject non-finite, non-positive, inverted, duplicate, or out-of-order candles.
3. Render four responsive candlestick panes with real price bounds, direction-colored wicks/bodies, oldest/latest time labels, current close, bar count, and first-to-last change.
4. Render `BACKEND OHLCV UNAVAILABLE` for legacy ledgers instead of converting reference prices into candles.
5. Run the focused Rust tests to green and visually inspect 120x36, 160x44, and 190x52 buffers.

### Task 5: Verify and document

**Files:**
- Modify: `skills/hypervector-cli/SKILL.md`
- Modify: `HANDOFF.md`
- Modify: `docs/guides/acceptance-visual-and-holistic.md`

1. Run focused Python and Rust tests.
2. Run the full Rust/TUI suite, strict Clippy, and Rust formatting.
3. Run the offline Python suite and task-scoped Ruff/format checks.
4. Run `git diff --check` and inspect the complete task diff for execution-path changes.
5. Record that existing ledgers remain readable but cannot display fabricated candles, and a restarted backend is required to publish the new OHLCV event.

## Acceptance and falsification

Confidence is high only if the ledger candle values match the poller's completed Hyperliquid frames exactly, repeated 15-second polls do not increase candle count, all four charts show visible bodies/wicks at the 120x36 floor, old ledgers say OHLCV is unavailable, and all tests remain green. The implementation is falsified by any open/in-progress bar, duplicate timestamp, TUI-derived OHLC, execution behavior change, or visual fallback to a close-only trace.

# Hypervelocity Strategy Candlestick Chart Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the provisional Screen 3 line plot with a responsive, backend-authoritative candlestick and volume view containing Hypervelocity regime and execution overlays.

**Architecture:** The Python backend adds missing candle-open, pending-maker-price, and active-target-price telemetry to its append-only regime/execution rows. The Rust TUI projects those fields into typed read-only models and renders a native Ratatui candle widget inspired by `cli-candlestick-chart`; it never opens a market connection, calculates a target, or creates a signal. Strategy levels outside the visible candle range are reported as edge badges and excluded from chart scaling.

**Tech Stack:** Python 3.13, pytest, Rust, Ratatui 0.29, Cargo integration tests.

---

### Task 1: Publish authoritative candle and strategy levels

**Files:**
- Modify: `tests/test_paper_session.py`
- Modify: `src/hypervector/paper/telemetry.py`
- Modify: `src/hypervector/paper/session.py`
- Modify: `src/hypervector/paper/hypervelocity_session_bridge.py`

1. Add failing assertions that every live `regime_observation` contains the measured candle `open` and `active_target_prices`.
2. Add a failing assertion that `entry_execution_observation` contains the pending maker limit price or `null`.
3. Run `uv run pytest tests/test_paper_session.py -q -m "not network"` and confirm the new assertions fail.
4. Add `open` to `bar_telemetry_payload` using only `record["open"]`.
5. Expose remaining active target command prices through `HypervelocitySessionBridge` and a session helper that handles both event and legacy shadow execution.
6. Add pending maker price to the backend-owned entry-execution payload.
7. Re-run the focused Python tests and confirm they pass.

Success criteria: values come from the completed venue candle or backend order state; absent orders produce empty/null telemetry rather than TUI derivation.

### Task 2: Extend the Rust read-only projection

**Files:**
- Modify: `crates/hypervector-tui/src/model.rs`
- Modify: `crates/hypervector-tui/src/backend_market.rs`
- Modify: `crates/hypervector-tui/src/backend_telemetry.rs`
- Modify: `crates/hypervector-tui/tests/backend_telemetry_test.rs`
- Modify: `crates/hypervector-tui/tests/regime_cockpit_test.rs`

1. Add failing Rust assertions for `RegimeSnapshot.open`, backend active target prices, and pending maker price.
2. Verify the targeted tests fail.
3. Add optional `open` for backward compatibility; missing historical telemetry remains explicitly unavailable.
4. Parse target-price arrays and pending-maker price into `BackendTelemetrySnapshot`.
5. Update fixtures without synthesizing candle open from prior close.
6. Re-run the focused Rust tests.

Success criteria: an old ledger parses safely but cannot render fabricated candles; a current ledger exposes exact backend levels.

### Task 3: Replace the provisional chart with a candle widget

**Files:**
- Replace: `crates/hypervector-tui/src/chart_view.rs`
- Modify: `crates/hypervector-tui/tests/regime_cockpit_test.rs`
- Modify: `crates/hypervector-tui/tests/liquidation_telemetry_test.rs`

1. Add failing render tests for candle bodies/wicks, volume, aligned regime ribbon, direct strategy-level labels, and the absence of the old HIGH/LOW/MARK legend.
2. Add a failing 80x24 render test and an old-ledger `OPEN DATA UNAVAILABLE` test.
3. Implement a bounded custom Ratatui widget using a maximum of the visible terminal capacity and at most 90 completed bars.
4. Scale the candle pane only from visible candle highs/lows.
5. Draw in-range backend levels directly: pending maker, entry, each target, and liquidation.
6. Report out-of-range levels as edge badges without changing the y-axis.
7. Add volume bars colored by candle direction and a one-row regime ribbon aligned with candles.
8. Show backend eligibility, 1m/5m/15m state, position direction, unrealized PnL, fees, and funding in a compact strategy strip.
9. Run the focused Rust render tests.

Success criteria: no giant legend, no overlapping high/low/mark traces, no scale flattening from distant liquidation, and no TUI-side trading calculation.

### Task 4: Verify, visually inspect, and document

**Files:**
- Modify: `skills/hypervector-cli/SKILL.md`
- Modify: `skills/hypervector-regime-detector/SKILL.md`
- Modify: `HANDOFF.md`

1. Document Screen 3 as backend OHLCV plus strategy-level telemetry.
2. Run `cargo fmt --all -- --check` and `cargo clippy -p hypervector-tui --all-targets -- -D warnings`.
3. Run `cargo test -p hypervector-tui`.
4. Run `uv run pytest tests/test_paper_session.py -q -m "not network"` and then the full offline suite.
5. Run `git diff --check` and inspect the complete diff for accidental strategy authority.
6. Confirm the user’s active shadow process was not stopped or reset; source changes require a later TUI/backend restart.

Success criteria: tests pass, the current shadow ledger is preserved, and visual acceptance remains explicitly provisional until the user sees the chart in their terminal.

Rollback: revert the additive telemetry fields and `chart_view.rs`; existing ledgers remain valid because all new Rust fields are optional or default-empty.

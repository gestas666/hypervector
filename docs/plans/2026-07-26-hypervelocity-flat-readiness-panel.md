# Hypervelocity Flat Readiness Panel Implementation Plan

> **For Codex:** Execute this plan test-first and keep all displayed execution state read-only.

**Goal:** Replace the unused flat-position space with an Entry Readiness / Market Pulse view sourced entirely from backend ledger telemetry, while preserving the active-position display.

**Architecture:** The Python shadow backend will publish explicit retry and cooldown state with each regime observation. The Rust ledger projection will combine those fields with backend order events and measured L2 telemetry. A dedicated flat-state renderer will display that projection and use only local frame ticks for a cosmetic freshness pulse; it will not calculate entry eligibility or submit orders.

**Tech Stack:** Python 3.13, pytest, Rust, Ratatui, Cargo tests.

---

## Task 1: Lock the backend-to-TUI telemetry contract

**Files:**
- Modify: `tests/test_paper_session.py`
- Modify: `src/hypervector/paper/session.py`
- Modify: `crates/hypervector-tui/tests/backend_telemetry_test.rs`
- Modify: `crates/hypervector-tui/src/backend_telemetry.rs`

1. Add a failing Python test asserting regime observations publish backend-owned retry and cooldown state.
2. Add a failing Rust test asserting pending maker state, latest regime metadata, retry state, and cooldown state are projected from ledger rows.
3. Implement the minimum additive telemetry fields and event projection.
4. Run the focused Python and Rust telemetry tests.

Success criteria: missing fields remain `N/A`; the TUI does not infer strategy eligibility; pending maker state is reconstructed only from `submit_entry`, `cancel_entry`, and filled entry events.

## Task 2: Add the flat-state readiness renderer

**Files:**
- Create: `crates/hypervector-tui/src/flat_readiness.rs`
- Modify: `crates/hypervector-tui/src/lib.rs`
- Modify: `crates/hypervector-tui/src/hypervelocity.rs`
- Modify: `crates/hypervector-tui/tests/regime_cockpit_test.rs`

1. Add a failing dashboard test for the flat view using a complete backend ledger fixture.
2. Add a regression assertion that an open position still renders the existing fee/PnL view and does not render the flat readiness body.
3. Implement a dedicated renderer with `N/A` handling and width-aware compact labels.
4. Run the focused cockpit test.

Success criteria: flat view shows direction, regime, maker state, retry state, cooldown, spread, book bias, L2 age, funding, and recent backend decision; open-position behavior is unchanged.

## Task 3: Add freshness-aware breathing without execution authority

**Files:**
- Modify: `crates/hypervector-tui/src/flat_readiness.rs`
- Modify: `crates/hypervector-tui/src/animation.rs`
- Modify: `crates/hypervector-tui/tests/regime_cockpit_test.rs`

1. Add failing tests for live and stale status labels.
2. Use `tick_count` only to vary the color of `SCANNING LIVE` while recent backend book telemetry is present.
3. Freeze animation and show `TELEMETRY STALE` when the connection is not connected or L2 age exceeds the named display freshness threshold.
4. Validate a narrow terminal render does not panic.

Success criteria: animation is cosmetic and cannot alter backend state; stale data is conspicuous; narrow terminals remain usable.

## Task 4: Verification and handoff

1. Run `uv run pytest tests/test_paper_session.py -q -m "not network"`.
2. Run `cargo test -p hypervector-tui`.
3. Run `uv run pytest tests/ -q -m "not network"`.
4. Run `cargo fmt --check` and inspect `git diff --check`.
5. Confirm no Hypervelocity launcher/backend/TUI process remains before giving the restart command.

Rollback: revert only the files listed above. The ledger additions are backward-compatible, and old ledgers render missing fields as `N/A`.

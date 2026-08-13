# Complete Live Research Cockpit Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deliver one immersive eight-screen TUI that projects backend-authored portfolio, strategy, candle, L2, position, execution, and research truth; exposes a safe staged next-run configuration workflow; and submits explicitly confirmed manual enter/close requests to the already-armed Python backend without putting venue credentials or an exchange client in Rust.

**Architecture:** Keep the Python cohort runner as the sole owner of venue reads, order submission, reconciliation, risk enforcement, journals, and configuration validation. Extend its cohort ledger with current five-level public L2 books and audited operator-command lifecycle rows. The Rust TUI remains a presentation and local request client: it reads strict ledger/checkpoint schemas, maintains selection/modal state, and atomically writes narrow command requests to a configured inbox only after confirmation. Observer and shadow modes show the complete interface but cannot submit order commands. Configuration changes are staged as a validated next-run patch and never mutate an armed engine in place.

**Tech Stack:** Python 3.13, strict JSONL ledgers, atomic JSON command files, Hyperliquid official SDK read/write boundaries, Rust, Serde, Ratatui 0.29, Pytest, Cargo tests, Clippy, Ruff.

---

### Task 1: Expand navigation and interaction state

**Files:**
- Modify: `crates/hypervector-tui/src/cohort_navigation.rs`
- Modify: `crates/hypervector-tui/src/app.rs`
- Modify: `crates/hypervector-tui/src/main.rs`
- Modify: `crates/hypervector-tui/src/cohort_view.rs`
- Modify: `crates/hypervector-tui/tests/cohort_navigation_test.rs`

Write failing tests for keys, Tab, and mouse selection across Portfolio, Setups, Charts, Depth, Trades, Journal, Control, and Config. Add dedicated cohort selection and modal state instead of reusing legacy regime/trade selectors. Render compact navigation and contextual footer help.

### Task 2: Make setup readiness selectable and inspectable

**Files:**
- Modify: `crates/hypervector-tui/src/cohort_router.rs`
- Create: `crates/hypervector-tui/src/cohort_setup_detail.rs`
- Modify: `crates/hypervector-tui/src/lib.rs`
- Modify: `crates/hypervector-tui/tests/bidirectional_cohort_view_test.rs`

Add a stateful highlighted readiness table with bounded scrolling. Enter opens a modal containing exact provider ID, symbol, side, decision and arrival times, reference price, action/reason, all regime states, confidence provenance, indicators, blockers, and raw condition counts. Missing backend values remain `N/A`.

### Task 3: Project current Hyperliquid L2 truth

**Files:**
- Modify: `src/hypervector/live/multi_asset_cohort_telemetry.py`
- Modify: `src/hypervector/live/multi_asset_observer_runner.py`
- Modify: `scripts/multi_asset_bidirectional_observe.py`
- Modify: `crates/hypervector-tui/src/backend_cohort.rs`
- Create: `crates/hypervector-tui/src/cohort_depth.rs`
- Modify: `tests/test_multi_asset_cohort_telemetry.py`
- Modify: `tests/test_multi_asset_observer_runner.py`
- Modify: `crates/hypervector-tui/tests/bidirectional_cohort_view_test.rs`

First test live projection of the latest five bids/asks already recorded in each asset ledger. Then add an injected public-book collector for disarmed observation so it uses no wallet or signer. Validate symbol, timestamps, positive sorted levels, spread, mid, depth ratio, and pressure. Render selectable coin ladders, freshness, cumulative depth, imbalance gauges, and an explicit unavailable/error state.

### Task 4: Separate portfolio, trades, and research workspaces

**Files:**
- Modify: `crates/hypervector-tui/src/cohort_dashboard.rs`
- Create: `crates/hypervector-tui/src/cohort_trades.rs`
- Create: `crates/hypervector-tui/src/cohort_research.rs`
- Modify: `crates/hypervector-tui/src/cohort_view.rs`
- Modify: `crates/hypervector-tui/tests/bidirectional_cohort_view_test.rs`

Keep Screen 1 focused on account health, four coin cards, readiness pulse, exposure, and current positions. Move selectable fills and detailed execution-quality evidence to Trades. Put causal 5/15/30/60-minute annotations, cadence, coverage, limitations, and audit health in Journal. Ensure observer mode never represents counterfactual paths as fills or PnL.

### Task 5: Add audited operator command transport

**Files:**
- Create: `src/hypervector/live/cohort_operator_commands.py`
- Modify: `src/hypervector/live/multi_asset_live_runner.py`
- Modify: `scripts/multi_asset_bidirectional_live.py`
- Create: `crates/hypervector-tui/src/cohort_operator.rs`
- Create: `crates/hypervector-tui/src/cohort_control.rs`
- Modify: `crates/hypervector-tui/src/cli_args.rs`
- Modify: `crates/hypervector-tui/src/main.rs`
- Modify: `tests/test_multi_asset_live_runner.py`
- Create: `tests/test_cohort_operator_commands.py`
- Modify: `crates/hypervector-tui/tests/bidirectional_cohort_view_test.rs`

Use atomic request files with schema version, unique request ID, current run ID, profile fingerprint, creation time, action, symbol, provider, and side. The backend atomically claims and validates requests, rejects stale/replayed/wrong-run/disarmed/invalid-capacity requests, and emits received/accepted/rejected/completed ledger rows. Manual enter bypasses only strategy prerequisites; it retains live-arm, one-position-per-coin, capacity, venue leverage/notional, and protective-stop enforcement. Manual close is reduce-only through the existing engine exit and suppresses same-cycle re-entry. Rust never imports an exchange SDK or reads a secret.

### Task 6: Restore a usable staged configuration screen

**Files:**
- Create: `src/hypervector/live/cohort_profile_stage.py`
- Modify: `src/hypervector/live/cohort_operator_commands.py`
- Modify: `crates/hypervector-tui/src/cohort_config.rs`
- Modify: `crates/hypervector-tui/src/app.rs`
- Modify: `tests/test_cohort_operator_commands.py`
- Modify: `crates/hypervector-tui/tests/bidirectional_cohort_view_test.rs`

Show backend facts separately from editable staged settings. Support selection and bounded changes for leverage, margin fraction, max notional, stop distance, max hold, maximum positions, provider priority/eligibility, and poll cadence. Save only through backend validation to a new runtime profile while disarmed, show an exact diff and `APPLY ON RESTART`, and reject hot mutation while armed. Show wallet/key presence as masked booleans only.

### Task 7: Acceptance, failure injection, and handoff

**Files:**
- Modify: `docs/guides/acceptance-visual-and-holistic.md`
- Modify: `docs/reviews/2026-08-02-measured-hypervelocity-tui-acceptance.md`
- Modify: `HANDOFF.md`

Run focused RED/GREEN tests throughout, then Ruff, formatting, Clippy, all Rust tests, and the non-network Python suite. Exercise stale L2, malformed command, replayed command, disarmed command, wrong run/profile, occupied coin, full capacity, rejected venue order, and backend restart. Inspect all eight screens at 100x28, 120x36, and a wide terminal against the active observer. Good enough means no fabricated field, no order path outside Python, every required control discoverable, every destructive action confirmed, and observer/checkpoint processes surviving TUI exit. Live remains fail-closed until a new explicit arm command.

**Primary references:**
- Hyperliquid exchange endpoint: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/exchange-endpoint
- Hyperliquid info/L2 endpoint: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint
- Hyperliquid order types and reduce-only behavior: https://hyperliquid.gitbook.io/hyperliquid-docs/trading/order-types
- Ratatui stateful table: https://ratatui.rs/examples/apps/table/
- Ratatui widget catalog: https://ratatui.rs/showcase/widgets/

**Claim confidence:** Medium. The design reuses existing backend boundaries and official venue/UI contracts. It would be falsified by any test showing the TUI can place without a matching armed backend, a command can replay or cross run identity, a displayed L2 value lacks a backend source, a config change mutates an armed process, or operator actions cannot be reconciled to exact ledger/venue evidence.

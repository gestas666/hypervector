# Shared Cohort TUI Modernization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use test-driven development to implement this plan task-by-task.

**Goal:** Modernize the read-only multi-asset cohort TUI so operational state,
exposure, protection, routing, execution quality, and faults remain clear from
120-column operator terminals through wide desktop layouts.

**Architecture:** Preserve the Python backend and append-only ledger as the
sole telemetry and execution authority. Extend only strict projection metadata
needed to remove hardcoded display assumptions, then split cohort rendering
into small screen-specific Rust modules. Responsive renderers select compact or
audit-detail columns based on terminal width; no screen synthesizes trades,
prices, signals, or risk decisions.

**Tech Stack:** Rust, Ratatui 0.29, Serde JSON, Chrono/chrono-tz, Cargo tests,
Python ledger fixtures, Ruff, Clippy.

**Status:** Implemented and visually inspected at 120x36, 160x44, and 190x52
while live execution remained unarmed. Final evidence: 2,645 offline Python
tests passed with four network tests deselected, all 89 Rust/TUI tests passed,
and strict all-target Clippy and Rust formatting passed.

---

### Task 1: Lock responsive visual acceptance with failing tests

**Files:**
- Modify: `crates/hypervector-tui/tests/bidirectional_cohort_view_test.rs`

1. Extract the existing cohort fixture into a reusable `cohort_app` helper.
2. Add a 120×36 dashboard test requiring equity, capacity, protection, sync,
   live-arm state, all four symbols, and read-only authority to remain visible.
3. Add wide-layout assertions for exact fill identity and full execution-quality
   columns.
4. Add router, chart, and configuration assertions at both acceptance widths.
5. Run the targeted test and confirm it fails because the current fixed-width
   tables truncate required feedback and the current chart has no axes.

### Task 2: Remove hardcoded portfolio capacity from the projection

**Files:**
- Modify: `crates/hypervector-tui/src/backend_cohort.rs`
- Test: `crates/hypervector-tui/tests/bidirectional_cohort_view_test.rs`

1. Parse `position_policy.maximum_concurrent_positions` from the backend
   configuration identity.
2. Reject zero or structurally inconsistent capacity.
3. Render open-position capacity using the parsed backend value rather than
   `/2`.
4. Run the parser and rendering test to green.

### Task 3: Build modern responsive chrome and dashboard widgets

**Files:**
- Modify: `crates/hypervector-tui/src/cohort_view.rs`
- Create: `crates/hypervector-tui/src/cohort_dashboard.rs`
- Create: `crates/hypervector-tui/src/cohort_widgets.rs`
- Modify: `crates/hypervector-tui/src/cohort_format.rs`
- Modify: `crates/hypervector-tui/src/lib.rs`

1. Replace the single overflowing header line with rounded two-line operator
   chrome: brand, connection, Eastern sync time, arm status, responsive tabs,
   symbols, and explicit read-only authority.
2. Add capital, exposure, and capacity KPI cards using truthful backend values
   and Ratatui gauges.
3. Add compact and wide position tables. Compact mode prioritizes state,
   position, mark/entry, PnL, liquidation distance, costs, protection, and
   faults; wide mode retains audit detail.
4. Render protection and fault cells with high-contrast safety styling without
   changing backend lifecycle state.
5. Add an explicit empty fill-journal panel rather than a blank table.

### Task 4: Modernize routing, charts, and configuration

**Files:**
- Create: `crates/hypervector-tui/src/cohort_router.rs`
- Create: `crates/hypervector-tui/src/cohort_chart.rs`
- Create: `crates/hypervector-tui/src/cohort_config.rs`
- Modify: `crates/hypervector-tui/src/cohort_view.rs`
- Modify: `crates/hypervector-tui/src/cohort_format.rs`

1. Add a recent-window routing summary rail and explicit empty action/withheld
   states.
2. Replace normalized sparklines with four Ratatui `Chart` widgets using
   Braille line traces, per-symbol colors, actual price bounds, latest value,
   sample count, and first-to-last change.
3. Keep chart wording honest: these are backend reference samples and may
   repeat between completed-candle updates.
4. Use responsive provider/configuration tables with human-readable provider
   aliases while preserving exact strategy IDs in wide mode.
5. Add a clear resize diagnostic below the 100×28 hard usability floor.

### Task 5: Holistic verification and operator record

**Files:**
- Modify: `HANDOFF.md`
- Modify: `docs/guides/acceptance-visual-and-holistic.md`

1. Run the cohort acceptance test and inspect rendered buffers at 120×36,
   160×44, and 190×52.
2. Run all Rust/TUI tests, strict Clippy, and Rust formatting.
3. Run the offline Python suite because the TUI parser shares backend ledger
   contracts.
4. Run task-scoped Ruff/formatting, backend status, and whitespace checks.
5. Record exact evidence, remaining uncertainty, and falsifiers. Do not arm
   live execution and do not commit unrelated dirty-worktree changes.

## Acceptance and falsification

The pass is accepted when every screen renders without panic at 120×36 and
190×52, all safety-critical fields remain visible at the compact width, wide
mode retains exact audit detail, stale/error/empty states are explicit, and the
TUI still has no execution path. It is falsified by backend/TUI value mismatch,
hidden arm or protection state, clipped coin rows, invented values, a chart
labeled as candles when it is reference sampling, or any order-authority code
entering the Rust crate.

# Regime Command Deck Range Lab Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Turn cohort Screen 9 into a selected-coin regime and range workstation whose visual cues remain traceable to causal backend telemetry.

**Architecture:** Preserve the Python backend as the sole classifier and ledger authority. Extend its range-provider evaluation with diagnostic-only canonical inputs, parse them through the existing strict Rust projection, and render a responsive selected-coin Range Lab alongside the four-coin state matrix and lifecycle evidence. The TUI derives presentation labels only; it does not generate regime states or execution decisions.

**Tech Stack:** Python/pandas regime telemetry, append-only JSONL, Rust/Ratatui, pytest, cargo test, cargo clippy.

---

### Task 1: Freeze the visible contract

**Files:**
- Modify: `crates/hypervector-tui/tests/bidirectional_cohort_view_test.rs`
- Modify: `crates/hypervector-tui/tests/cohort_navigation_test.rs`

1. Add a failing visual test requiring selected-coin identity, canonical range state, exact range causes or explicit unavailable labels, movement-strength semantics, component conflict, transition age, and backend freshness.
2. Add a failing navigation test requiring left/right selection on Screen 9.
3. Run the focused Rust tests and confirm failures are caused by the missing widgets/navigation.

### Task 2: Publish causal range anatomy

**Files:**
- Modify: `src/hypervector/regime/composite.py`
- Modify: `src/hypervector/live/sol_range_onset_decision_source.py`
- Modify: `tests/test_regime_classifier.py`
- Modify: `tests/test_regime_component_telemetry.py`

1. Add failing Python assertions for prefixed 1m/5m/15m strength, BBWP, EMA-gap, coiling, and canonical reason telemetry.
2. Verify the tests fail before implementation.
3. Add diagnostic columns without changing `primary_regime`, direction, eligibility, sizing, or routing.
4. Verify prefix invariance and exact state fingerprints remain unchanged.

### Task 3: Build the responsive Range Lab

**Files:**
- Create: `crates/hypervector-tui/src/cohort_regime_focus.rs`
- Create: `crates/hypervector-tui/src/cohort_regime_dynamics.rs`
- Modify: `crates/hypervector-tui/src/cohort_regime.rs`
- Modify: `crates/hypervector-tui/src/cohort_view.rs`
- Modify: `crates/hypervector-tui/src/main.rs`
- Modify: `crates/hypervector-tui/src/lib.rs`

1. Render the selected symbol with exact backend state and age, separate RANGE/NON-RANGE from movement strength, show cause evidence and thresholds, show component alignment/conflict, and retain open/closed causal reflections.
2. Make left/right move the shared coin selector on Screen 9 and expose the control in the footer.
3. Preserve explicit N/A output for ledgers produced before the new diagnostic fields.
4. Keep every module below the project line limit.

### Task 4: Verify compatibility and quality

**Files:**
- Modify: `skills/hypervector-cli/SKILL.md`
- Modify: `HANDOFF.md`

1. Run focused Python and Rust tests.
2. Run `cargo fmt --check`, the full `cargo test -p hypervector-tui`, and clippy with warnings denied.
3. Run relevant no-network Python tests for classifier, component telemetry, signal source, and cohort telemetry.
4. Render 120x36 and 165x46 test snapshots and inspect for clipping or misleading labels.
5. Confirm the live backend PID is unchanged and the updated TUI parses the current pre-extension ledger with explicit N/A diagnostics.


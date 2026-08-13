# Cohort Observer Research Dashboard Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace empty observer-only account panels on cohort Screen 1 with a strict backend-authored setup journal and causal forward-path scorecard while leaving the armed/live dashboard unchanged.

**Architecture:** Extend the Rust checkpoint projection with a validated union of readiness and provider-path evidence already serialized by the Python observer sidecar. When `analysis_mode=forward_observer`, the dashboard renders ten setup rows plus 5/15/30/60-minute descriptive path cells; every panel states that the evidence is counterfactual annotation, not orders, fills, PnL, or win probability. No classifier, threshold, strategy, or execution code changes.

**Tech Stack:** Rust, Serde, Ratatui, existing Python observer checkpoint JSON, Cargo tests and Clippy.

---

### Task 1: Freeze the checkpoint journal contract

**Files:**
- Modify: `crates/hypervector-tui/tests/cohort_checkpoint_test.rs`
- Modify: `crates/hypervector-tui/src/backend_cohort_checkpoint.rs`

**Step 1: Write the failing parser test**

Extend the observer fixture with readiness details and full path statistics.
Require a public row containing exact provider ID, symbol, latest side,
readiness fraction/reason/blockers, evaluation/fire counts, and 5/15/30/60
minute resolved/independent/mean/positive-rate fields. Add rejection coverage
for a non-finite or out-of-range probability and independent counts exceeding
resolved paths.

**Step 2: Run the parser test to verify RED**

Run:

```bash
cargo test -p hypervector-tui --test cohort_checkpoint_test \
  parses_observer_setup_evidence_without_execution_outcomes -- --exact
```

Expected: compilation fails because detailed observer journal rows do not yet
exist on `CohortCheckpointTelemetry`.

**Step 3: Implement the minimal strict projection**

Add typed `CohortObserverProviderEvidence` and `CohortObserverPathEvidence`
records. Parse a union of readiness keys and outcome keys, retaining missing
paths as unavailable rather than zero. Validate provider keys, readiness
fractions, finite rates/returns, and count invariants. Older checkpoints with
no detailed readiness map remain loadable with an empty journal.

**Step 4: Run the parser tests to verify GREEN**

Run:

```bash
cargo test -p hypervector-tui --test cohort_checkpoint_test
```

Expected: all checkpoint tests pass.

### Task 2: Render an observer-specific Screen 1

**Files:**
- Modify: `crates/hypervector-tui/tests/bidirectional_cohort_view_test.rs`
- Modify: `crates/hypervector-tui/src/cohort_dashboard.rs`
- Create only if the dashboard exceeds the project limit: `crates/hypervector-tui/src/cohort_observer_dashboard.rs`
- Modify if a module is created: `crates/hypervector-tui/src/lib.rs`

**Step 1: Write the failing 120x36 render test**

Require `SETUP JOURNAL`, all ten provider/coin rows, explicit latest blockers,
and a `CAUSAL FORWARD PATHS // ANNOTATIONS, NOT FILLS OR PNL` table with compact
5m/15m/30m/60m cells. Assert that observer Screen 1 does not show empty account,
position, or fill panels. Retain the existing disarmed and no-fake-PnL checks.

**Step 2: Run the render test to verify RED**

Run:

```bash
cargo test -p hypervector-tui --test bidirectional_cohort_view_test \
  observer_dashboard_projects_setup_and_path_journal -- --exact
```

Expected: the new journal labels and rows are absent.

**Step 3: Implement the observer renderer**

Branch only when the parsed checkpoint mode is `forward_observer`. Preserve
the rolling coverage strip, render readiness with backend aliases and exact
reasons, then render descriptive horizon cells such as
`R7/I2 +9.6 71%`. Use `N/A` for absent evidence and never convert missing
values to zero. The normal live dashboard path remains byte-for-byte
behaviorally unchanged.

**Step 4: Run the render tests to verify GREEN**

Run:

```bash
cargo test -p hypervector-tui --test bidirectional_cohort_view_test
```

Expected: all cohort render tests pass at the acceptance sizes.

### Task 3: Validate against the active observer

**Files:**
- Modify: `docs/guides/acceptance-visual-and-holistic.md`
- Modify: `docs/reviews/2026-08-02-measured-hypervelocity-tui-acceptance.md`

**Step 1: Run static and regression validation**

Run:

```bash
cargo fmt --all -- --check
cargo clippy -p hypervector-tui --all-targets -- -D warnings
cargo test -p hypervector-tui
uv run pytest tests/ -q -m "not network"
git diff --check
```

Expected: zero failures; report dependency/deprecation warnings separately.

**Step 2: Inspect the real 120x36 ledger render**

Attach without starting another backend:

```bash
uv run python scripts/multi_asset_bidirectional_canary_tui.py --mode monitor
```

Verify all ten setup rows, exact current run identity, complete technical
coverage, no direction conflicts, and readable horizon cells. Quit the display
and verify the observer plus checkpoint sidecar remain running.

**Step 3: Document limits and falsifiers**

Record that overlapping readiness paths are descriptive and that independent
counts—not raw resolved counts—bound the effective sample. Falsifiers are a
backend/checkpoint mismatch, a missing provider row, malformed statistics
accepted as valid, missing values shown as zero, any fill/PnL implication, or
an observer display affecting execution authority.

**Step 4: Commit only on explicit user request**

Do not commit or push this shared dirty worktree unless the user separately
authorizes it.

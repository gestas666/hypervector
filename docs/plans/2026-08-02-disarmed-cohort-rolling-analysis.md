# Disarmed Cohort Rolling Analysis Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Continuously publish bounded, read-only setup-process analysis for the disarmed multi-asset observer and render it honestly in the cohort TUI without inventing fills, PnL, or execution authority.

**Architecture:** Snapshot only complete prefixes of the observer decision ledger, reuse the existing causal observer audit, and atomically replace one latest checkpoint. Give observer checkpoints their own schema and Rust projection so setup cadence is never forced into the live execution/outcome shape. The unified observe launcher supervises this sidecar after a fresh backend identity and stops it before the backend, while the existing immutable stopped-run audit remains the final evidence artifact.

**Tech Stack:** Python 3.13, immutable JSONL, atomic JSON replacement, pytest, Rust/Ratatui/serde, Cargo tests.

---

## Constraints

- Apply `@hypervector-cli`, `@hypervector-regime-detector`, and the project charter.
- The sidecar has no credential, venue-client, order, sizing, pause, stop, tuning, or strategy-mutation imports.
- Observer analysis reports technical coverage, poll/evaluation cadence, intents, readiness, and blocker attribution only.
- Missing execution outcomes remain unavailable; they are not serialized or rendered as zero.
- The output is one bounded atomically replaced file; immutable final audits remain separate and strict.
- The active three-provider observer remains disarmed while implementation and tests run.

### Task 1: Define the observer checkpoint in tests

**Files:**

- Create: `tests/test_cohort_observer_checkpoint.py`
- Create: `tests/test_multi_asset_bidirectional_observer_checkpoint_script.py`

**Steps:**

1. Write a failing test that builds a checkpoint from a valid disarmed observer ledger and requires `execution_authority=none`, complete nine-pair coverage, readiness count, strategy-intent count, and no execution/PnL fields.
2. Write a failing test that appends an incomplete JSON tail, publishes twice, and requires explicit dropped-tail evidence plus a single atomically replaced destination.
3. Write a failing CLI-loop test requiring `--once` and explicit unavailable publication on incomplete startup evidence.
4. Run the focused tests and confirm RED because the observer checkpoint modules do not exist.

### Task 2: Implement bounded observer checkpoint publication

**Files:**

- Create: `src/hypervector/research/checkpoint_storage.py`
- Create: `src/hypervector/research/cohort_observer_checkpoint.py`
- Create: `scripts/multi_asset_bidirectional_observer_checkpoint.py`
- Modify: `src/hypervector/research/cohort_live_checkpoint.py`

**Steps:**

1. Extract the existing atomic JSON replacement into one typed public helper without changing live-checkpoint behavior.
2. Build the observer checkpoint from `audit_cohort_observer_run`, stable-prefix evidence, a non-liveness lifecycle label, and a report-only contract.
3. Add a bounded loop matching the live sidecar's retry/unavailable behavior but importing no execution modules.
4. Run focused tests and confirm GREEN; run existing live-checkpoint tests to prove parity.

### Task 3: Extend the strict TUI checkpoint projection

**Files:**

- Modify: `crates/hypervector-tui/src/backend_cohort_checkpoint.rs`
- Modify: `crates/hypervector-tui/src/cohort_checkpoint_widget.rs`
- Modify: `crates/hypervector-tui/tests/cohort_checkpoint_test.rs`
- Modify: `crates/hypervector-tui/tests/bidirectional_cohort_view_test.rs`

**Steps:**

1. Write a failing Rust parser test for the observer schema requiring setup-process lifecycle, coverage, evaluations, and intents while leaving closed trades and net PnL absent.
2. Write a failing render test requiring `FORWARD OBSERVER`, `EVAL`, `INTENTS`, and `NO OUTCOMES`, and rejecting `CLOSED 0` or `NET +$0.00`.
3. Implement mode-specific strict parsing and rendering while preserving the live checkpoint shape.
4. Run focused Rust tests and deterministic 120x36 visual acceptance.

### Task 4: Supervise the observer sidecar from the unified launcher

**Files:**

- Modify: `scripts/multi_asset_bidirectional_canary_tui.py`
- Modify: `tests/test_multi_asset_bidirectional_canary_tui_script.py`

**Steps:**

1. Change the existing observe-launch test to require an observer checkpoint command and TUI checkpoint argument; confirm RED.
2. Add an observer-specific command resolver and supervise it with the same start-after-identity, stop-before-backend ordering.
3. Publish one final observer checkpoint before the immutable final audit.
4. Preserve monitor-only behavior: it attaches to an existing latest checkpoint but starts no process.
5. Run focused launcher tests and confirm GREEN.

### Task 5: Verify and activate on the current disarmed run

**Files:**

- Modify: `skills/hypervector-cli/SKILL.md`
- Modify: `docs/reviews/2026-08-02-measured-hypervelocity-tui-acceptance.md`

**Steps:**

1. Run Python focused tests, all non-network Python tests, all TUI tests, Clippy, Ruff, formatting, and diff checks.
2. Start only the observer checkpoint sidecar against the already-running three-provider ledger.
3. Verify the checkpoint reports nine expected provider-symbol pairs, no routed actions, no execution authority, and no fabricated PnL.
4. Attach/read the TUI projection and verify the rolling-analysis line is current and observer-specific.
5. Update operator documentation from two/eight to three/nine provider coverage and record confidence/falsifiers.

## Acceptance falsifiers

- Observe mode imports or constructs a venue/order client.
- The observer checkpoint contains closed-trade, PnL, fee, funding, slippage, or markout values.
- A readiness percentage is labeled as probability or expected return.
- The TUI renders missing execution outcomes as zero.
- The sidecar starts before the fresh backend identity or survives backend shutdown.
- Repeated checkpoints create an unbounded history instead of replacing one latest file.
- The current backend loses `live_armed=false` or `execution_authority=none`.

## Execution decision

Execute locally in the current session. The shared dirty worktree makes a separate worktree inappropriate, and project instructions prohibit delegating to subagents without explicit user authorization. Defer commits until the user requests publication.

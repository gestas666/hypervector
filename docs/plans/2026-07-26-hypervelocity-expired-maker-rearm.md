# Hypervelocity Expired Maker Re-arm Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prevent an expired Hypervelocity maker entry from chasing price through the same uninterrupted directional regime while preserving fixed-target position management and same-trend re-entry after completed trades.

**Architecture:** Treat a maker submission as one entry attempt. When its TTL expires unfilled, record that direction as consumed and require a causal non-matching regime observation before another order may be submitted in that direction. Persist the consumed direction in the shadow ledger, mirror the rule in research replay, and expose the effective policy as backend telemetry.

**Tech Stack:** Python 3.13, pandas, pytest, TOML, Rust/Ratatui configuration projection.

---

### Task 1: Reproduce the maker-chase failure

**Files:**
- Modify: `tests/test_paper_session.py`
- Modify: `tests/test_hypervelocity_maker_replay.py`

1. Add a session test with a continuously falling short regime whose first post-only order expires without filling.
2. Assert that no replacement order is submitted while the short regime remains uninterrupted.
3. Assert that a `RANGE` observation re-arms a later short attempt.
4. Add the equivalent report-only maker replay test.
5. Run the focused tests and verify they fail because a replacement is currently submitted.

### Task 2: Persist the expired direction

**Files:**
- Modify: `tests/test_paper_resume.py`
- Modify: `src/hypervector/paper/resume.py`

1. Add a failing ledger-resume test for a TTL cancellation followed only by same-direction observations.
2. Add a second test proving a non-matching observation clears the consumed direction.
3. Extend `ShadowPortfolioResume` with the optional consumed direction.
4. Derive it causally from append-only order and regime events.
5. Run the focused resume tests to green.

### Task 3: Enforce and report the policy

**Files:**
- Modify: `src/hypervector/strategies/hypervelocity_contract.py`
- Modify: `src/hypervector/strategies/hypervelocity_profile.py`
- Modify: `configs/hypervelocity_faithful.toml`
- Modify: `src/hypervector/paper/session.py`
- Modify: `crates/hypervector-tui/src/config_view.rs`
- Modify: `tests/test_hypervelocity_profile.py`
- Modify: `tests/test_paper_session.py`

1. Add immutable `entry_ttl_seconds = 300.0` and `expired_entry_rearm_policy = "regime_reset"` contract values.
2. Validate and expose both values from the TOML profile.
3. Initialize session re-arm state from durable resume state.
4. Block only resubmission of the expired direction; clear the block on `RANGE`, `TRANSITION`, the opposite direction, or another directionless state.
5. Leave open-position target behavior and post-close cooldown unchanged.
6. Include the policy in session telemetry and the read-only TUI configuration menu.

### Task 4: Keep research replay behavior identical

**Files:**
- Modify: `src/hypervector/research/maker_replay.py`
- Modify: `tests/test_hypervelocity_maker_replay.py`

1. Track an expired direction in replay state.
2. Re-arm only after the desired direction differs.
3. Verify the replay does not repeatedly submit during one uninterrupted trend.

### Task 5: Validate the observed incident and regression surface

**Files:**
- No production files beyond Tasks 1-4.

1. Replay the recorded 2026-07-26 short lifecycle and verify the replacements at `$64,328`, `$64,326`, and `$64,265` are suppressed after the first `$64,368` attempt expires.
2. Run `uv run pytest tests/test_paper_session.py tests/test_paper_resume.py tests/test_hypervelocity_profile.py tests/test_hypervelocity_maker_replay.py -q`.
3. Run `uv run pytest tests/ -q -m "not network"`.
4. Run `cargo test -p hypervector-tui`.
5. Report replay deltas without claiming positive expectancy from one incident.

### Deferred: DAFE trend-damage layer

The local `reference/pine-scripts/trend_state.pine` damage score reacts after opposing price evidence appears. It does not explain or prevent the observed fill, which resulted from repeated TTL repricing during a still-bearish impulse. Keep DAFE damage annotation-only until a causal Hyperliquid replay demonstrates incremental out-of-sample value.

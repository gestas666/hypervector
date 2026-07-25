# Hypervelocity One-Way Bidirectional Runtime Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Run one BTC Hypervelocity shadow backend that may enter long or short by regime while enforcing at most one open position and consuming a validated faithful TOML profile.

**Architecture:** A typed profile loader validates the immutable contract and runtime policy from `configs/hypervelocity_faithful.toml`. A dedicated CLI command loads that profile, starts one existing paper engine, and selects the eligible direction only while flat; an open position ignores regime reversal until its fixed target closes. Backend telemetry stamps the effective profile so the read-only TUI can audit it.

**Tech Stack:** Python 3.13, `tomllib`, pandas, argparse, pytest, Ruff, Rust TUI telemetry tests.

---

### Task 1: Validate the faithful runtime profile

**Files:**
- Modify: `configs/hypervelocity_faithful.toml`
- Modify: `configs/default.toml`
- Create: `src/hypervector/strategies/hypervelocity_profile.py`
- Create: `tests/test_hypervelocity_profile.py`

**Steps:**
1. Write failing tests for valid one-way/bidirectional settings and rejection of two-position, hedge, reversal-while-open, mutable risk, execution, or ML-gating values.
2. Run the tests and confirm failure because the loader does not exist.
3. Implement a typed TOML loader with actionable validation errors.
4. Run the tests and confirm PASS.

### Task 2: Implement one-position bidirectional state transitions

**Files:**
- Modify: `src/hypervector/strategies/hypervelocity.py`
- Modify: `src/hypervector/paper/session.py`
- Test: `tests/test_hypervelocity.py`
- Test: `tests/test_paper_session.py`

**Steps:**
1. Write failing tests proving flat→long, long ignores down regime until TP, flat-after-TP→short, and position count never exceeds one.
2. Add a single-pass latest direction decision and profile-aware session state.
3. Stamp position mode, max positions, direction mode, switching, and reversal policy in `session_start`.
4. Run focused tests and confirm PASS.

### Task 3: Add the config-driven shadow command

**Files:**
- Modify: `src/hypervector/cli.py`
- Modify: `src/hypervector/paper/runner.py`
- Modify: `skills/hypervector-cli/SKILL.md`
- Test: `tests/test_paper_cli.py`
- Test: `tests/test_cli_status.py`

**Steps:**
1. Write a failing CLI test for `hypervelocity-shadow-run --config` and config-derived runtime arguments.
2. Implement the dedicated reportable/no-submit command using one backend process.
3. Confirm help, status inventory, run identity, and stop behavior under tests.

### Task 4: Verify and publish

**Files:**
- Modify: `HANDOFF.md`

**Steps:**
1. Run focused tests, full offline Python tests, Rust tests, Ruff, formatting, and diff checks.
2. Run a bounded real Hyperliquid shadow smoke and confirm one run ID, one-way telemetry, and zero submit attempts.
3. Document evidence and remaining TUI raw-L2 limitation.
4. Commit, fast-forward `main`, push, delete the feature branch, and verify a clean synchronized worktree.

# TUI Telemetry Correction and Shadow Reset Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Correct Hypervelocity TUI regime, leverage, and net-return projections, then safely reset the unified shadow portfolio and trade log with an audit backup.

**Architecture:** The TUI remains a read-only projection. Regime distribution comes from backend `regime_observation` rows when available, session identity supplies the leverage fallback, and trade return uses cumulative backend accounting divided by actual allocated margin. A Python reset operation obtains the existing per-root runtime lock, backs up shadow state, and clears only decisions and backend text logs.

**Tech Stack:** Rust, serde, Ratatui, Python 3.13, argparse, pytest, Cargo test.

---

### Task 1: Correct regime projection

**Files:**
- Modify: `crates/hypervector-tui/src/data_loader.rs`
- Modify: `crates/hypervector-tui/src/backend_telemetry.rs`
- Modify: `crates/hypervector-tui/src/ui/mod.rs`
- Test: `crates/hypervector-tui/tests/backend_telemetry_test.rs`
- Test: `crates/hypervector-tui/tests/regime_cockpit_test.rs`

**Steps:**
1. Write failing tests proving `TREND_UP` maps to bull and backend regime observations are retained.
2. Run Cargo tests and confirm the observed RANGE fallback failure.
3. Add canonical mappings and make the distribution prefer backend regime history.
4. Run Cargo tests and confirm PASS.

### Task 2: Correct leverage and trade return projection

**Files:**
- Modify: `crates/hypervector-tui/src/backend_telemetry.rs`
- Test: `crates/hypervector-tui/tests/backend_telemetry_test.rs`

**Steps:**
1. Add the exact observed trade ledger as a failing regression test.
2. Confirm it reports 0x, excludes the entry fee, and uses equity percentage.
3. Fall back to session leverage, measure net realized change from before entry, and divide by actual margin.
4. Confirm the projected result is 40x, `$479.41`, and about `6.85%`.

### Task 3: Add backed-up shadow reset

**Files:**
- Create: `src/hypervector/shadow_reset.py`
- Modify: `src/hypervector/cli.py`
- Create: `tests/test_shadow_reset.py`
- Modify: `tests/test_cli_status.py`

**Steps:**
1. Write failing tests for dry-run, required confirmation, backup, targeted clearing, and cache preservation.
2. Implement reset under the existing singleton runtime lock.
3. Expose `hypervelocity-shadow-reset --yes` and report backup paths.
4. Run focused tests and Ruff.

### Task 4: Verify, reset, and publish

**Files:**
- Modify: `HANDOFF.md`
- Modify: `skills/hypervector-cli/SKILL.md`

**Steps:**
1. Run complete Python and Rust suites plus Ruff and diff checks.
2. Confirm no backend process and acquire the runtime lock.
3. Run the confirmed reset against `data/ops/hypervelocity_visual`.
4. Verify decisions/logs are empty and the timestamped backup contains the prior run.
5. Commit and push `main`; leave a clean worktree.

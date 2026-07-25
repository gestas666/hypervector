# Unified Hypervelocity TUI Launcher Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Provide one CLI command that supervises the Hypervelocity shadow backend and launches the read-only TUI in the same terminal.

**Architecture:** The Python CLI remains the process supervisor and execution owner. It starts the existing no-submit backend with output redirected to a durable log, waits for a new backend session ledger row, then runs the Rust TUI in the foreground; TUI exit or interruption terminates and reaps only the backend child started by the launcher.

**Tech Stack:** Python 3.13, `subprocess`, argparse, pytest, Rust/Ratatui.

---

### Task 1: Define and test the supervisor lifecycle

**Files:**
- Create: `src/hypervector/tui_launcher.py`
- Create: `tests/test_tui_launcher.py`

**Steps:**
1. Write failing tests for command construction, readiness ordering, backend early failure, and graceful child shutdown.
2. Run the focused tests and confirm failure because the launcher does not exist.
3. Implement the smallest typed supervisor that satisfies those behaviors.
4. Run focused tests and Ruff.

### Task 2: Expose one CLI command

**Files:**
- Modify: `src/hypervector/cli.py`
- Modify: `tests/test_cli_status.py`

**Steps:**
1. Write a failing test that `hypervelocity-tui` is discoverable.
2. Add config, refresh, and startup-timeout arguments and delegate to the supervisor.
3. Verify help output and a bounded fake lifecycle test.

### Task 3: Document and verify

**Files:**
- Modify: `skills/hypervector-cli/SKILL.md`
- Modify: `HANDOFF.md`

**Steps:**
1. Replace the two-terminal operator procedure with the unified command.
2. Run all offline Python tests, Rust tests, Ruff, TOML parsing, and diff checks.
3. Run a real PTY smoke, quit the TUI, and confirm the child backend stopped cleanly.
4. Commit and push `main`, leaving a clean worktree.

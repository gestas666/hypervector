# Cohort Monitor Nonblocking Startup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use test-driven-development to implement this plan task-by-task.

**Goal:** Start the read-only cohort TUI immediately when its checkpoint is stale, refresh telemetry in parallel, and terminate the entire owned checkpoint process tree when the TUI exits.

**Architecture:** Keep the existing fail-closed profile and run-identity checks, but remove the stale-checkpoint readiness barrier from monitor rendering. Start the checkpoint writer in a dedicated process session so the supervisor can signal the writer and its isolated research worker together. Preserve the checkpoint publisher's existing initial-sync and evidence-integrity behavior.

**Tech Stack:** Python 3.13, `subprocess`, POSIX process groups, pytest.

---

### Task 1: Reproduce nonblocking startup

**Files:**
- Modify: `tests/test_cohort_tui_checkpoint_readiness.py`
- Modify: `tests/test_multi_asset_bidirectional_canary_tui_script.py`

**Step 1: Write the failing test**

Assert that a stale checkpoint starts the owned writer, enters the Rust TUI without calling the checkpoint readiness wait, and stops the writer after the TUI returns.

**Step 2: Verify the test fails**

Run:

```bash
uv run pytest tests/test_cohort_tui_checkpoint_readiness.py tests/test_multi_asset_bidirectional_canary_tui_script.py -q
```

Expected: the nonblocking-start assertion fails because `_run_monitor` currently invokes `_wait_for_monitor_checkpoint` before `subprocess.run(launch.tui_command)`.

### Task 2: Implement nonblocking monitor rendering

**Files:**
- Modify: `scripts/multi_asset_bidirectional_canary_tui.py`

**Step 1: Implement the minimal change**

Remove monitor-mode waiting on a newly started stale-checkpoint writer. Retain exact active/staged/accounting identity validation and the existing writer singleton check.

**Step 2: Verify focused behavior**

Run the tests from Task 1. Expected: PASS.

### Task 3: Reproduce and fix descendant cleanup

**Files:**
- Modify: `tests/test_multi_asset_bidirectional_canary_tui_script.py`
- Modify: `scripts/multi_asset_bidirectional_canary_tui.py`

**Step 1: Write failing tests**

Assert that checkpoint writers start in a new process session and that normal/forced shutdown sends `SIGTERM`/`SIGKILL` to the owned process group.

**Step 2: Verify tests fail**

Run the focused script test. Expected: failure because the current launcher starts no isolated session and signals only the checkpoint parent.

**Step 3: Implement the minimal process-tree cleanup**

Start the checkpoint writer with `start_new_session=True`. Signal the session's process group on normal and forced shutdown, tolerating only the race where the group has already exited.

**Step 4: Verify focused behavior**

Run the focused tests. Expected: PASS with no leaked fake process state.

### Task 4: Validate the integrated startup path

**Files:**
- Verify only; no additional source changes unless a test identifies a defect.

**Step 1: Run regression tests**

```bash
uv run pytest tests/test_cohort_tui_checkpoint_readiness.py tests/test_canary_supervisor.py tests/test_checkpoint_initial_sync_order.py tests/test_multi_asset_bidirectional_canary_tui_script.py tests/test_multi_asset_bidirectional_live_checkpoint_script.py -q
```

**Step 2: Run the Rust TUI suite**

```bash
cargo test -p hypervector-tui
```

**Step 3: Run a controlled monitor launch**

Launch the exact v61 monitor command in a PTY, verify that the Rust TUI process appears before checkpoint refresh completion, send `q`, and verify no owned checkpoint or research-import descendants remain.

**Step 4: Inspect the final diff**

Confirm changes are limited to this plan, the monitor supervisor, and its focused tests. Do not commit or stage unrelated work from the existing dirty worktree.

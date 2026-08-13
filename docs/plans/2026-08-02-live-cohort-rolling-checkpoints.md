# Live Cohort Rolling Checkpoints Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Status:** Implemented and fully verified while disarmed on 2026-08-02.

**Goal:** Continuously publish bounded, read-only technical and statistical checkpoints for the active multi-asset canary and surface an honest lifecycle state to operators without changing execution behavior.

**Architecture:** A stable-prefix ledger reader will snapshot only complete JSONL records while a live writer may be appending. A separate checkpoint builder will reuse the existing stopped-run audit, add explicit cohort-versus-asset lifecycle reconciliation, and atomically replace one bounded `latest` JSON artifact. The unified TUI supervisor will own this analysis sidecar only after the backend publishes a fresh armed identity, stop it before backend shutdown, and retain the existing immutable final post-stop audit.

**Tech Stack:** Python 3.13, immutable JSONL ledgers, atomic JSON replacement, pytest, existing Hypervector live cohort audit and Rust TUI.

---

## Constraints and evidence contract

- Follow `@hypervector-cli`, `@hypervector-regime-detector`, and `@ml4-trading` live-system guidance.
- The sidecar is read-only: it has no venue client, credentials, configuration mutation, order submission, pause, stop, sizing, or tuning authority.
- Statistical outcomes remain advisory under `SRS_HV1_NO_GATES`; they do not become implicit performance gates.
- Technical integrity and execution safety remain fail-closed in the existing backend.
- Rolling snapshots may drop one incomplete trailing JSONL fragment and must report that fact; final immutable audits remain strict and reject incomplete source files.
- The rolling artifact is bounded and atomically replaced. It must not duplicate full ledgers on every interval.
- Cohort heartbeat state and per-asset terminal states are distinct facts and must be reconciled explicitly.
- No live execution is armed while implementing or verifying this observer.
- This is a shared dirty worktree. Preserve unrelated changes and defer commits until the user explicitly requests publication.

### Task 1: Make active-ledger snapshots stable-prefix aware

**Files:**

- Modify: `src/hypervector/research/live_ledger_snapshot.py`
- Create: `tests/test_live_ledger_snapshot.py`

**Steps:**

1. Write failing tests for complete input, strict rejection of an incomplete tail, and rolling-mode truncation to the last newline with explicit byte evidence.
2. Run the focused test and confirm RED.
3. Implement the minimum stable-prefix reader without silently changing the strict default.
4. Run the focused test and confirm GREEN.

### Task 2: Build a lifecycle-aware bounded checkpoint

**Files:**

- Create: `src/hypervector/research/cohort_live_checkpoint.py`
- Create: `tests/test_cohort_live_checkpoint.py`

**Steps:**

1. Write failing tests for a consistent running cohort, all assets stopped behind a stale running heartbeat, mixed asset states, and atomic bounded output.
2. Reuse `audit_multi_asset_live_run` for technical/economic evidence and add a checkpoint-only advisory contract.
3. Snapshot all ledgers from complete prefixes and atomically replace one `latest_checkpoint.json`.
4. Verify that source byte counts, dropped-tail evidence, and lifecycle classifications remain explicit.

### Task 3: Run the checkpoint as a supervised read-only sidecar

**Files:**

- Create: `scripts/multi_asset_bidirectional_live_checkpoint.py`
- Modify: `scripts/multi_asset_bidirectional_canary_tui.py`
- Modify: `tests/test_multi_asset_bidirectional_canary_tui_script.py`
- Create: `tests/test_multi_asset_bidirectional_live_checkpoint_script.py`

**Steps:**

1. Write failing supervisor tests requiring the sidecar to start after fresh backend identity, stop before backend shutdown, and never appear in monitor-only mode.
2. Add a `--once` mode for deterministic verification and a bounded polling loop for supervised live use.
3. Keep sidecar failure observable but non-authoritative over strategy performance; retain the immutable post-stop audit.
4. Run focused script and supervisor tests.

### Task 4: Surface operator status and verify holistically

**Files:**

- Modify: TUI cohort backend/view files only as required for checkpoint status.
- Modify: `HANDOFF.md`
- Modify: `skills/hypervector-cli/SKILL.md`
- Modify: `docs/plans/2026-08-01-bidirectional-shared-live-cohort.md`

**Steps:**

1. Show checkpoint freshness, lifecycle reconciliation, coverage state, and provider readiness without implying that proximity guarantees an entry.
2. Document recovery, final-audit strictness, and the distinction between technical defects and unresolved statistical evidence.
3. Run focused tests, full non-network Python tests, Rust tests, Clippy, formatting, Ruff, status, diff, and structural checks.

## Acceptance falsifiers

- The observer imports or constructs an execution client.
- A performance or trade-count result pauses, blocks, retunes, or mutates the live strategy.
- A partial final JSONL row crashes the rolling observer or is silently accepted by the final audit.
- Repeated checkpoints grow without bound by copying complete ledgers into a history directory.
- The TUI reports `RUNNING` solely from an old cohort heartbeat when every asset is `STOPPED`.
- A checkpoint can overwrite an immutable stopped-run audit.
- The supervisor starts the observer before verifying the backend's fresh armed run identity.

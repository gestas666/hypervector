# V85 SPCX Transient Availability Repair Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prevent a single recoverable SPCX public-data transport failure from making a still-fresh, internally consistent observer checkpoint disappear from V85 monitoring, while retaining fail-closed behavior for stale, stopped, faulted, or mixed-publication state.

**Architecture:** Keep the observer's durable `degraded_transient` lifecycle evidence unchanged. Change only the live journal adapter's consumption rule: a degraded checkpoint may be read while its last successful observation remains inside the existing 30-second freshness bound. Cursor/journal identity and publication-order checks remain mandatory, and no missing decision is synthesized.

**Tech Stack:** Python 3.13, pytest, pandas, existing atomic observer status and append-only decision journal.

---

### Task 1: Reproduce the acceptance flicker at the adapter boundary

**Files:**
- Modify: `tests/test_hip3_fresh15_journal_provider.py`
- Test: `tests/test_hip3_fresh15_journal_provider.py`

1. Add a test whose observer lifecycle is `degraded_transient`, whose last successful `observed_at_ms` is fresh, and whose cursor/journal boundary is coherent.
2. Assert that the already-published completed-bar decision remains readable and attributable.
3. Run `uv run pytest tests/test_hip3_fresh15_journal_provider.py -q` and confirm the new test fails because `observer_runtime_degraded_transient` is raised.

### Task 2: Preserve fail-closed boundaries while accepting fresh degraded state

**Files:**
- Modify: `src/hypervector/live/hip3_fresh15_journal_provider.py`
- Modify: `tests/test_hip3_fresh15_journal_provider.py`

1. Update the runtime lifecycle check so `running` and `degraded_transient` continue to the existing timestamp and mixed-publication validation.
2. Add a second test proving that a degraded checkpoint older than 30 seconds still fails with `observer_status_stale`.
3. Retain rejection for `stopped` and `fault`, and retain exact cursor/journal identity checks.
4. Run the focused provider tests until green.

### Task 3: Verify the live availability and acceptance interaction

**Files:**
- Test: `tests/test_multi_asset_provider_availability.py`
- Test: `tests/test_v79_poststart_acceptance.py`

1. Run the provider-availability tests to ensure true observer unavailability still becomes an explicit non-action evaluation.
2. Run the V85 post-start acceptance tests to ensure nine monitored routes and eight executable routes remain exact.
3. Run `uv run pytest tests/test_hip3_breakout_shadow_observer_lifecycle.py tests/test_hip3_index_observer_supervisor_freshness.py tests/test_multi_asset_provider_availability.py tests/test_v79_poststart_acceptance.py -q`.

### Task 4: Validate repository and runtime boundaries

**Files:**
- Verify only; no live process mutation.

1. Run the project non-network test suite relevant to the changed Python boundary.
2. Run `cargo test -p hypervector-tui` because the TUI consumes the affected checkpoint projection.
3. Confirm the existing V85 process was not stopped, restarted, or signaled.
4. Record that the loaded live process cannot adopt this Python change until its next operator-controlled restart.

### Task 5: Address the separate cadence-design defect

**Files:**
- Create a separate preregistration and implementation plan only after the transport repair passes.

1. Keep V85 strategy parameters unchanged; this transport fix must not create entries or change signal eligibility.
2. Define the requested portfolio cadence as an explicit usefulness objective rather than an implicit technical launch gate.
3. Evaluate a separately identified V86 strategy candidate with point-in-time partitions, 13-bps minimum round-trip friction, concentration checks, and no live authority.
4. Reject the candidate if any sealed out-of-sample partition is negative after costs or if positive results depend on the largest winner.

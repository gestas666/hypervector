# Hypervelocity Peak Observer Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Collect durable, causal, venue-matched counterfactual evidence for the frozen +7%/55% peak-protection candidate without changing orders, positions, sizing, exits, or live authority.

**Architecture:** Add a pure state machine that samples authentic Hyperliquid marks at the source monitor's five-second cadence and prices a hypothetical stop only from fresh adverse BBO. The backend ledger persists full observer state only at lifecycle changes, and the runtime profile exposes the observer separately from the execution portfolio fingerprint. `HypervelocitySessionBridge` feeds the observer after actual fills and before actual mark liquidation, but observer output can only append report-only rows.

**Tech Stack:** Python 3.13, dataclasses, append-only JSONL ledger, pytest, TOML runtime profile.

---

### Task 1: Freeze the report-only contract

**Files:**
- Create: `src/hypervector/paper/peak_protection_observer.py`
- Test: `tests/test_peak_protection_observer.py`

**Step 1: Write the failing configuration tests**

Test that `PeakObserverConfig` accepts only `off|observe`, validates the frozen candidate constants, and reports `execution_authority="none"`.

**Step 2: Run the tests to verify RED**

Run: `uv run pytest tests/test_peak_protection_observer.py -q`

Expected: FAIL because the observer module does not exist.

**Step 3: Implement the minimal configuration and state types**

Create typed dataclasses for configuration, active state, and emitted state-change events. Reject non-finite values and any execution authority other than `none`.

**Step 4: Run the tests to verify GREEN**

Run: `uv run pytest tests/test_peak_protection_observer.py -q`

Expected: PASS.

### Task 2: Implement causal peak and trigger semantics

**Files:**
- Modify: `src/hypervector/paper/peak_protection_observer.py`
- Modify: `tests/test_peak_protection_observer.py`

**Step 1: Write failing lifecycle tests**

Cover long and short activation, 55% lock translation, five-second sampling, 60-second ratchet cooldown, 0.05% minimum stop movement, no widening, stale/unpriced trigger, fresh adverse-BBO hypothetical exit, and actual-position end.

**Step 2: Run the tests to verify RED**

Run: `uv run pytest tests/test_peak_protection_observer.py -q`

Expected: FAIL on missing lifecycle behavior.

**Step 3: Implement the minimal pure observer**

Return ledger-ready state-change payloads. Never import an execution client, construct an `OrderCommand`, mutate the portfolio, or claim a fill when book evidence is stale.

**Step 4: Run the tests to verify GREEN**

Run: `uv run pytest tests/test_peak_protection_observer.py -q`

Expected: PASS.

### Task 3: Persist and restore observer state

**Files:**
- Modify: `src/hypervector/paper/peak_protection_observer.py`
- Modify: `tests/test_peak_protection_observer.py`

**Step 1: Write failing restart tests**

Test exact restoration from the latest matching candidate row, rejection of malformed rows, and `coverage_complete_since_entry=false` when observation begins during an already-open position.

**Step 2: Run the tests to verify RED**

Run: `uv run pytest tests/test_peak_protection_observer.py -q`

Expected: FAIL on missing persistence behavior.

**Step 3: Implement streaming ledger restoration**

Read only matching run/candidate rows and restore the last complete state. Emit no success-shaped fallback for malformed matching state.

**Step 4: Run the tests to verify GREEN**

Run: `uv run pytest tests/test_peak_protection_observer.py -q`

Expected: PASS.

### Task 4: Add validated profile configuration without changing execution identity

**Files:**
- Modify: `configs/hypervelocity_faithful.toml`
- Modify: `src/hypervector/strategies/hypervelocity_profile.py`
- Modify: `tests/test_hypervelocity_profile.py`
- Modify: `tests/test_paper_session.py`

**Step 1: Write failing profile and fingerprint tests**

Assert the exact +7%/55%/0.05%/60s/5s values, `mode="observe"`, and that changing observer mode does not enter `_portfolio_spec` or alter its fingerprint.

**Step 2: Run the tests to verify RED**

Run: `uv run pytest tests/test_hypervelocity_profile.py tests/test_paper_session.py -q`

Expected: FAIL because the profile has no observer section.

**Step 3: Parse the research-only section**

Add `PeakObserverConfig` to `HypervelocityProfile` and expose it in session telemetry outside `portfolio_spec`.

**Step 4: Run the tests to verify GREEN**

Run: `uv run pytest tests/test_hypervelocity_profile.py tests/test_paper_session.py -q`

Expected: PASS.

### Task 5: Integrate the observer into the backend ledger bridge

**Files:**
- Modify: `src/hypervector/paper/hypervelocity_session_bridge.py`
- Modify: `src/hypervector/paper/session.py`
- Test: `tests/test_hypervelocity_peak_observer_bridge.py`

**Step 1: Write failing integration tests**

Assert that entry fills start observation, mark changes append only state transitions, stale BBO cannot create a priced hypothetical exit, observer rows carry `submitted=false` and `place_attempted=false`, and the actual controller result is identical with observer on or off.

**Step 2: Run the tests to verify RED**

Run: `uv run pytest tests/test_hypervelocity_peak_observer_bridge.py -q`

Expected: FAIL because the bridge does not feed an observer.

**Step 3: Add one-way telemetry integration**

Load restart state at bridge attachment, sync after controller fills, observe marks before actual liquidation, and append returned payloads through `append_paper_decision` only.

**Step 4: Run the tests to verify GREEN**

Run: `uv run pytest tests/test_hypervelocity_peak_observer_bridge.py -q`

Expected: PASS.

### Task 6: Verify safety and forward-readiness

**Files:**
- Modify: `HANDOFF.md`
- Modify: `docs/reviews/2026-07-29-hypervelocity-peak-protection-evidence.md`

**Step 1: Run focused Python verification**

Run: `uv run pytest tests/test_peak_protection_observer.py tests/test_hypervelocity_peak_observer_bridge.py tests/test_hypervelocity_profile.py tests/test_hypervelocity_shadow_friction.py tests/test_hypervelocity_event_runtime.py tests/test_paper_session.py -q`

Expected: PASS.

**Step 2: Run static checks**

Run: `uv run ruff check src/hypervector/paper/peak_protection_observer.py src/hypervector/paper/hypervelocity_session_bridge.py src/hypervector/paper/session.py src/hypervector/strategies/hypervelocity_profile.py tests/test_peak_protection_observer.py tests/test_hypervelocity_peak_observer_bridge.py`

Run: `uv run ruff format --check` on the same Python files.

Expected: PASS.

**Step 3: Confirm the active backend was not restarted**

Compare its PID/start time before and after implementation and confirm no observer rows appear until the next deliberate restart.

**Step 4: Document falsification criteria**

Reject the candidate if fresh counterfactual exits reduce net outcome versus the actual 8% control or fail to reduce adverse reversal loss across independent observation windows. Report all results; do not convert performance into an implicit trial gate.

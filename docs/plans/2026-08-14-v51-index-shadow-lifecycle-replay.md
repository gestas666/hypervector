# v51 Index Shadow Lifecycle Replay Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build an execution-incapable, immutable replay of the prospective v51 `xyz:SP500` and `xyz:SPCX` v3 signals using the exact v51 stop, maximum-hold, completed-bar profit-lock, sizing, and source-bound friction contracts.

**Architecture:** Extend the existing generic HIP-3 lifecycle simulator only at narrow typed seams, preserving its default structural-stop and signal-exit behavior. Add a separate v51 orchestration layer that freezes active profile identity, obtains exact 15-minute signal candles plus completed 1-minute profit-lock candles, verifies journal/book/mark/funding/friction inputs before and after evaluation, and publishes authority-none reports atomically. The adapter must never import an execution factory, create a signing client, alter the live profile, or treat prospective paper results as live fills.

**Tech Stack:** Python 3.12, pandas, dataclasses, pytest, Ruff, existing Hypervector HIP-3 input/replay/reporting modules, `cohort_profit_lock_policy`.

---

### Task 1: Freeze the exact v51 exit contract in failing tests

**Files:**
- Modify: `tests/test_hip3_shadow_lifecycle_replay.py`
- Reference: `configs/multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51.toml`
- Reference: `src/hypervector/cohort_profit_lock_policy.py`

**Step 1: Write the failing fixed-stop test**

Add a lifecycle fixture whose structural stop is 120 bps away and assert a v51 configuration records an 80-bps execution stop instead.

**Step 2: Run the fixed-stop test and verify RED**

Run: `uv run pytest -q tests/test_hip3_shadow_lifecycle_replay.py -k fixed_execution_stop`

Expected: FAIL because `Hip3ShadowLifecycleConfig` has no fixed execution-stop contract.

**Step 3: Write the failing no-signal-exit test**

Add an early EMA/signal exit and assert that a v51 configuration ignores it while the existing generic configuration still exits on it.

**Step 4: Run the signal-exit test and verify RED**

Run: `uv run pytest -q tests/test_hip3_shadow_lifecycle_replay.py -k signal_exit`

Expected: FAIL because signal exits cannot yet be disabled.

**Step 5: Write failing profit-lock causality tests**

Assert all of the following independently:

- completed pre-entry 1-minute bars cannot arm or trigger the lock;
- a post-entry completed bar at +100 bps arms the lock;
- after arming, a completed bar below the +40-bps floor exits;
- after arming, an 80-bps peak giveback exits;
- an uncompleted 1-minute bar cannot trigger an exit;
- the earliest causal event among stop, profit lock, and 24-hour maximum hold wins.

**Step 6: Run the profit-lock tests and verify RED**

Run: `uv run pytest -q tests/test_hip3_shadow_lifecycle_replay.py -k profit_lock`

Expected: FAIL because the replay has no completed-bar profit-lock input or exit reason.

### Task 2: Implement the minimal typed replay seams

**Files:**
- Modify: `src/hypervector/research/hip3_shadow_lifecycle_models.py`
- Modify: `src/hypervector/research/hip3_shadow_lifecycle_inputs.py`
- Modify: `src/hypervector/research/hip3_shadow_lifecycle_replay.py`
- Modify: `src/hypervector/research/hip3_shadow_lifecycle_reporting.py`
- Test: `tests/test_hip3_shadow_lifecycle_replay.py`

**Step 1: Add backwards-compatible configuration fields**

Append optional fields to `Hip3ShadowLifecycleConfig` for a fixed execution stop, signal-exit enablement, and an optional `ProfitLockPolicy`. Validate finite positive stop distance and reject contradictory/incomplete policies. Existing constructors must retain their current behavior.

**Step 2: Add completed 1-minute bars as an explicit optional input**

Require timestamped, completed, unique, monotonic 1-minute OHLC rows when a profit-lock policy is configured. Reject absent coverage, duplicates, partial terminal bars, and rows whose causal publication time is after the requested cutoff.

**Step 3: Reuse the production profit-lock evaluator**

Call `evaluate_profit_lock_path` from `src/hypervector/cohort_profit_lock_policy.py`; do not duplicate the lock equations. Convert only causally completed post-entry bars into the evaluator input.

**Step 4: Select the earliest valid exit event**

Construct stop, optional signal, optional completed-bar profit-lock, and maximum-hold candidates, then select the earliest timestamp. Record `profit_lock` as a distinct exit reason and retain the exact trigger bar/time.

**Step 5: Run focused tests and verify GREEN**

Run: `uv run pytest -q tests/test_hip3_shadow_lifecycle_replay.py tests/test_hip3_shadow_lifecycle_sources.py`

Expected: PASS with existing generic replay behavior unchanged.

**Step 6: Check standards**

Run: `uv run ruff check src/hypervector/research/hip3_shadow_lifecycle_*.py tests/test_hip3_shadow_lifecycle_*.py`

Run: `uv run ruff format --check src/hypervector/research/hip3_shadow_lifecycle_*.py tests/test_hip3_shadow_lifecycle_*.py`

Expected: PASS; all touched files remain at most 500 lines and functions at most 50 lines. Extract a helper module rather than exceeding either limit.

### Task 3: Bind source-backed v51 friction and sizing

**Files:**
- Create: `src/hypervector/research/v51_index_lifecycle_contract.py`
- Create: `tests/test_v51_index_lifecycle_contract.py`
- Reference: `data/logs/research/bidirectional_cohort/v50_execution_friction_stress_20260813_v1.json`
- Reference: `data/logs/research/bidirectional_cohort/v51_growth_sizing_stress_20260813_v1.json`
- Reference: `configs/multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51.toml`

**Step 1: Write failing identity and evidence tests**

Require exact v51 profile ID/fingerprint/config hash, exact v3 provider/profile IDs, exact symbol, 10% margin fraction, 10x leverage, fixed 80-bps stop, 24-hour hold, and 100/40/80 completed-bar lock. Reject a v50 profile identity even when its route economics are reused as input evidence.

**Step 2: Write failing friction provenance tests**

Require exact route-symbol friction rows, component semantics, source file hash, and sample scope. Preserve the SP500 same-provider SPCX exit proxy label instead of misrepresenting it as exact SP500 evidence. Reject missing, negative, inverted, stale, or aliased evidence.

**Step 3: Run tests and verify RED**

Run: `uv run pytest -q tests/test_v51_index_lifecycle_contract.py`

Expected: FAIL because no v51 contract loader exists.

**Step 4: Implement the minimal immutable contract loader**

Return a typed authority-none contract containing only verified values. Do not infer performance from the stop-wave artifact and do not double-count visible depth already consumed by exact order-book fills; explicitly classify which friction components remain modeled.

**Step 5: Run tests and verify GREEN**

Run: `uv run pytest -q tests/test_v51_index_lifecycle_contract.py`

Expected: PASS.

### Task 4: Add the execution-incapable v51 orchestration command

**Files:**
- Create: `src/hypervector/research/v51_index_shadow_lifecycle.py`
- Create: `scripts/v51_index_shadow_lifecycle_replay.py`
- Create: `tests/test_v51_index_shadow_lifecycle.py`
- Create: `tests/test_v51_index_shadow_lifecycle_script.py`

**Step 1: Write failing command-contract tests**

Prove that the command:

- accepts only `xyz:SP500` or `xyz:SPCX` and their exact v3 identities;
- requires the active v51 config and exact fingerprint;
- binds the live prospective journal and exact per-asset book ledger;
- retrieves completed 15-minute signal candles and completed 1-minute profit-lock candles through unsigned public fetch boundaries;
- requires exact mark/funding coverage and source-bound friction;
- rejects pre-existing output, changing input prefixes, generator changes, identity mismatch, and incomplete rows;
- returns `qualification_authority: none`, has no signer/order client, and cannot route intents.

**Step 2: Run command tests and verify RED**

Run: `uv run pytest -q tests/test_v51_index_shadow_lifecycle.py tests/test_v51_index_shadow_lifecycle_script.py`

Expected: FAIL because the v51 adapter and script do not exist.

**Step 3: Implement the minimal command**

Reuse the generic HIP-3 input, mark, funding, depth-fill, reporting, and atomic publication helpers. Keep orchestration and validation in new modules rather than expanding any existing file beyond 500 lines.

**Step 4: Run command tests and verify GREEN**

Run: `uv run pytest -q tests/test_v51_index_shadow_lifecycle.py tests/test_v51_index_shadow_lifecycle_script.py`

Expected: PASS without network access.

### Task 5: Run one bounded immutable replay per asset

**Files:**
- Create: `data/logs/research/v51_sp500_shadow_lifecycle_<cutoff>_v1.json`
- Create: `data/logs/research/v51_spcx_shadow_lifecycle_<cutoff>_v1.json`
- Create or revise: `docs/research-journal/v51-index-live-translation-current-run-v3.json`

**Step 1: Preflight the frozen cutoff**

Record exact observed cutoff, active run/profile/fingerprint, current config hash, journal/book prefix hashes, mark/funding/candle coverage, and both symbols' notional. Abort if any identity or source changed.

**Step 2: Run SP500 once**

Use its exact prospective v3 journal and book ledger. Do not silently rerun after any failure; diagnose and report the failure first.

**Step 3: Run SPCX once**

Use its exact prospective v3 journal and book ledger under the same cutoff and source contract. Do not pool outcomes across symbols.

**Step 4: Independently verify the immutable reports**

Rehash every input and generator file; recompute lifecycle arithmetic, fees, funding, modeled friction, exit precedence, completeness, per-side counts, largest-winner sensitivity, and authority-none status.

**Step 5: Journal only evidence-backed conclusions**

Report completed and censored lifecycles separately. Prospective shadow results are diagnostic and must not be labeled actual live fills or used to mutate v51. Any live-change proposal requires the separate 15-field approval contract and explicit human authorization.

### Task 6: Final verification and handoff

**Files:**
- Verify all files from Tasks 1-5

**Step 1: Run focused regression suites**

Run: `uv run pytest -q tests/test_hip3_shadow_lifecycle_replay.py tests/test_hip3_shadow_lifecycle_sources.py tests/test_v51_index_lifecycle_contract.py tests/test_v51_index_shadow_lifecycle.py tests/test_v51_index_shadow_lifecycle_script.py -m 'not network'`

Expected: PASS.

**Step 2: Run static checks**

Run: `uv run ruff check <exact touched Python paths>`

Run: `uv run ruff format --check <exact touched Python paths>`

Run: `git diff --check -- <exact touched paths>`

Expected: PASS with no file over 500 lines and no function over 50 lines.

**Step 3: Reconcile live isolation**

Confirm the active v51 backend PID/run/profile/fingerprint are unchanged by the research work, all replay reports say authority none, and no execution factory imports the adapter.

**Step 4: Prepare an explicit release manifest without broad staging**

Because the shared worktree contains unrelated user/agent changes, do not use `git add -A`, `git add .`, or commit until an exact reviewed path manifest is approved. Preserve all unrelated changes.

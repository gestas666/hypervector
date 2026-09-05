# BTC Subminute Sell-Flow Absorption Diagnostic Implementation Plan

> **For Codex:** Execute this plan task-by-task with test-driven development. Live strategy, risk, and configuration changes are outside this plan.

**Goal:** Determine whether a preregistered BTC long-only ten-second sell-flow absorption event has stable after-cost value across fixed historical partitions, without changing V58 or granting execution authority.

**Architecture:** Add bounded, read-only DuckDB input extraction for exact Hyperliquid L2 snapshots and public trades; derive one causal ten-second event family with a one-hour cooldown; replay fixed $5,000 visible-depth entries and the unchanged V58 BTC 60/60/24h exit contract under nominal and stress assumptions; publish immutable complete evidence. Keep input extraction, signal logic, replay, and reporting in separate modules under 500 lines each.

**Tech Stack:** Python 3.13, DuckDB, pandas, existing Hypervector visible-depth/funding helpers, pytest, Ruff, immutable JSON and Parquet evidence.

---

### Task 1: Freeze the hypothesis and evidence boundary

**Files:**
- Create: `docs/research-journal/v58-btc-subminute-sell-flow-absorption-preregistration-20260821-v1.json`

**Step 1: Record the outcome-blind development profiling**

Record the fixed ten-second feature definitions, the static $5.5 million sell-notional threshold, all other thresholds, the 128 one-hour-cooled development events, month distribution, archive identities, and the explicit statement that no candidate forward return was inspected.

**Step 2: Freeze the result contract**

Record the fixed partitions, control arm, visible-depth entry timing, 60/60/24h V58-compatible exit, fee/funding assumptions, stop-trigger proxies, acceptance criteria, rejection rule, and `execution_authority=none`.

**Step 3: Validate the preregistration**

Run: `jq -e '.' docs/research-journal/v58-btc-subminute-sell-flow-absorption-preregistration-20260821-v1.json`

Expected: exit 0.

### Task 2: Test bounded causal input extraction

**Files:**
- Create: `tests/test_btc_subminute_absorption_inputs.py`
- Create: `src/hypervector/research/btc_subminute_absorption_inputs.py`

**Step 1: Write the failing input tests**

Cover trade-ID deduplication, ten-second boundary semantics, first/minimum/last bid depth, terminal imbalance, spread maximum, strictly prior 60-minute anchor, archive-gap rejection, source-identity stability, and read-only database handling.

**Step 2: Run the tests to verify RED**

Run: `uv run pytest tests/test_btc_subminute_absorption_inputs.py -q`

Expected: collection failure because the input module does not exist.

**Step 3: Implement the minimal bounded extractor**

Query explicit half-open time windows, deduplicate trades by `(symbol, trade_id)`, return causal ten-second features, and fail explicitly on schema, coverage, or identity drift.

**Step 4: Run the focused tests to verify GREEN**

Run: `uv run pytest tests/test_btc_subminute_absorption_inputs.py -q`

Expected: all focused tests pass.

### Task 3: Test the frozen signal and control

**Files:**
- Create: `tests/test_btc_subminute_absorption_signals.py`
- Create: `src/hypervector/research/btc_subminute_absorption_signals.py`

**Step 1: Write the failing signal tests**

Cover every frozen threshold at its boundary, long-only direction, one-hour greedy cooldown, prefix invariance, gap resets, the extreme-sell/uptrend control, deterministic event identity, and invalid inputs.

**Step 2: Run the tests to verify RED**

Run: `uv run pytest tests/test_btc_subminute_absorption_signals.py -q`

Expected: collection failure because the signal module does not exist.

**Step 3: Implement the minimal signal builder**

Apply the preregistered conjunction exactly once and emit complete blocker attribution without grids, threshold searches, or outcome-dependent branches.

**Step 4: Run the focused tests to verify GREEN**

Run: `uv run pytest tests/test_btc_subminute_absorption_signals.py -q`

Expected: all focused tests pass.

### Task 4: Test exact-entry and fixed-exit replay

**Files:**
- Create: `tests/test_btc_subminute_absorption_replay.py`
- Create: `src/hypervector/research/btc_subminute_absorption_replay.py`

**Step 1: Write the failing replay tests**

Cover next-book latency, visible-depth capacity, target-before-stop, stop-before-target, conservative same-timestamp precedence, one-position occupancy, funding sign, maker/taker fees, 24-hour fallback, incomplete paths, nominal and stress scenarios, and no execution authority.

**Step 2: Run the tests to verify RED**

Run: `uv run pytest tests/test_btc_subminute_absorption_replay.py -q`

Expected: collection failure because the replay module does not exist.

**Step 3: Implement the minimal replay**

Use the next visible book after the frozen latency for entry, exact depth VWAP for the $5,000 notional, fixed 60-bps target and stop, exact hourly funding, and complete disclosure that historical midpoint/public-trade stop proxies are not Hyperliquid mark price.

**Step 4: Run the focused tests to verify GREEN**

Run: `uv run pytest tests/test_btc_subminute_absorption_replay.py -q`

Expected: all focused tests pass.

### Task 5: Execute and publish the frozen experiment

**Files:**
- Create: `tests/test_btc_subminute_absorption_reporting.py`
- Create: `src/hypervector/research/btc_subminute_absorption_reporting.py`
- Create: `scripts/v58_btc_subminute_absorption.py`
- Create: `docs/research-journal/v58-btc-subminute-sell-flow-absorption-result-20260821-v1.json`
- Create: immutable report/trade bundle under `data/logs/research/`

**Step 1: Write failing reporting tests**

Require all arms, partitions, and scenarios; complete blockers; side and month attribution; largest-winner removal; source/generator evidence; immutable output; and explicit live isolation fields.

**Step 2: Run the reporting tests to verify RED**

Run: `uv run pytest tests/test_btc_subminute_absorption_reporting.py -q`

Expected: failures for the missing reporting and command APIs.

**Step 3: Implement and run the immutable evaluator**

Evaluate every preregistered arm and scenario. Publish losing, sparse, or high-drawdown outcomes rather than aborting them; only technical integrity failures abort publication.

**Step 4: Apply the preregistered disposition**

Reject the exact candidate if any support criterion fails. A passing historical result remains report-only and requires prospective parity, shared-portfolio interaction, a verified flat transition boundary, and explicit human approval before any live proposal.

### Task 6: Verify without touching live execution

**Files:**
- Verify: all files created by Tasks 1-5
- Verify: the active V58 process, profile, position lifecycle, and protective orders

**Step 1: Run focused and adjacent tests**

Run: `uv run pytest tests/test_btc_subminute_absorption_*.py tests/test_cohort_eligible_exact_depth_forward.py tests/test_market_cipher_data.py -q`

Run: `uv run ruff check src/hypervector/research/btc_subminute_absorption_*.py scripts/v58_btc_subminute_absorption.py tests/test_btc_subminute_absorption_*.py`

Expected: exit 0 for both.

**Step 2: Verify evidence and code limits**

Validate every JSON file with `jq -e`, verify recorded hashes and bytes, require each touched source/test file below 500 lines, and require each function below 50 lines.

**Step 3: Reconcile live isolation**

Confirm V58 retains the same backend/config identity unless independently changed by the operator, the open SP500 lifecycle remains venue-protected or is authoritatively reconciled closed, and every new artifact reports `execution_authority=none`, `runtime_strategy_changed=false`, and `orders_attempted=false`.

No commit step is included because the current scope explicitly prohibits commit, push, or worktree cleanup.

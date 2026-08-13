# Source-Follow Live Canary Audit Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a report-only audit that turns one armed BTC source-follow run plus its independently recorded Hyperliquid tape into durable, comparable decision, lifecycle, candle-parity, and feed-quality evidence.

**Architecture:** A pure research module will normalize one selected event-sourced live run, validate its backend-authored OHLCV and non-executable history contract, and query DuckDB for independently recorded public trades and L2 continuity. A thin script will write one immutable JSON report. The audit will report every mismatch and sparse result without changing execution, strategy, model, or promotion authority.

**Tech Stack:** Python 3.13, DuckDB, pandas, pytest, immutable JSON evidence helpers.

---

### Task 1: Lock the event-sourced run contract

**Files:**
- Create: `tests/test_source_follow_live_audit.py`
- Create: `src/hypervector/research/source_follow_live_audit.py`

**Step 1: Write the failing run-selection test**

Create a fixture containing two run IDs and assert that `audit_source_follow_live_run` selects the explicit run, or the latest identified run when no ID is supplied. Assert that missing runs, missing configuration identity, malformed OHLCV, and mixed profiles raise actionable errors.

**Step 2: Run the test to verify it fails**

Run:

```bash
uv run pytest tests/test_source_follow_live_audit.py -q
```

Expected: collection fails because `source_follow_live_audit` does not exist.

**Step 3: Implement the minimum run normalization**

Add typed dataclasses for a selected live run and ledger candle. Parse nested `payload` objects without mutating them. Require positive finite OHLC, nonnegative volume, aligned UTC five-minute timestamps, one configuration identity, and a single profile/run fingerprint.

**Step 4: Run the focused test**

Expected: run-selection and validation tests pass.

### Task 2: Prove history cannot be execution evidence

**Files:**
- Modify: `tests/test_source_follow_live_audit.py`
- Modify: `src/hypervector/research/source_follow_live_audit.py`

**Step 1: Write failing history-authority tests**

Assert that the report counts all `regime_history` rows and separately reports any row where `entry_allowed`, `regime_admitted`, `long_entry`, or `short_entry` is true, or where `decision_action` differs from `history_only`. Do not suppress the row or abort the report.

**Step 2: Run and observe the expected failure**

Expected: missing history audit fields.

**Step 3: Implement history and executable-decision summaries**

Report history count, authority violations, OHLCV validity, regime distribution, executable-decision distribution, onset count, eligible signal count, direction counts, and exclusion-reason counts. Retain zero-count and poor-result outcomes.

**Step 4: Run the focused test**

Expected: history and decision summaries pass.

### Task 3: Audit lifecycle facts without inventing state

**Files:**
- Modify: `tests/test_source_follow_live_audit.py`
- Modify: `src/hypervector/research/source_follow_live_audit.py`

**Step 1: Write failing lifecycle tests**

Use ledger fixtures with flat, pending, open, filled, and fault states. Assert counts for order intents, acknowledgements, fills, closes, funding rows, and faults, plus exact latest venue state, account value, withdrawable value, open order IDs, and position size. Missing state must remain unavailable rather than becoming flat.

**Step 2: Verify the tests fail for missing lifecycle output**

**Step 3: Implement lifecycle summarization**

Read only persisted venue/backend facts. Do not calculate an order, target, liquidation price, PnL, or synthetic state.

**Step 4: Run the focused test**

Expected: lifecycle tests pass.

### Task 4: Compare backend candles with independently recorded trade bars

**Files:**
- Modify: `tests/test_source_follow_live_audit.py`
- Modify: `src/hypervector/research/source_follow_live_audit.py`

**Step 1: Write failing DuckDB parity tests**

Build a temporary database with the live-event schema, one exact five-minute bar, one mismatched bar, and one uncovered ledger bar. Assert that the report keeps all three and separately reports covered, exact, mismatched, and uncovered counts plus per-field maximum absolute differences.

**Step 2: Verify red**

Expected: parity output is absent.

**Step 3: Implement measured parity**

Aggregate `replay_live_public_trades` into five-minute OHLCV using venue timestamps and trade IDs. Join by exact UTC bar open. Treat missing recorded evidence as uncovered, not a market mismatch. Preserve representative mismatches with a bounded sample.

**Step 4: Run the focused test**

Expected: exact, mismatched, and uncovered classifications pass.

### Task 5: Separate complete recorder windows from partial bars

**Files:**
- Modify: `tests/test_source_follow_live_audit.py`
- Modify: `src/hypervector/research/source_follow_live_audit.py`

**Step 1: Write failing L2-continuity tests**

Create one bar with L2 evidence within six seconds of both boundaries and no internal gap over six seconds, plus one partial bar. Assert that only the continuous bar receives `continuous_l2=true`. Add negative receive lag and explicit stream-gap fixtures and assert they remain visible.

**Step 2: Verify red**

**Step 3: Implement L2 quality aggregation**

For each five-minute bar report snapshot count, first/last boundary distance, maximum exchange-time gap, negative receive-lag count, and explicit stream-gap count. Use a named six-second diagnostic threshold. It is a quality annotation, not an execution or strategy gate.

**Step 4: Run the focused test**

Expected: complete and partial evidence remain distinct.

### Task 6: Add the immutable operator command

**Files:**
- Create: `scripts/hypervelocity_source_live_canary_audit.py`
- Create: `tests/test_source_follow_live_canary_audit_script.py`
- Modify: `skills/hypervector-cli/SKILL.md`

**Step 1: Write the failing script-contract test**

Assert required ledger/database/output arguments, optional run ID, `report_only=true`, `execution_authority=none`, and `runtime_strategy_changed=false`. Assert an existing output is rejected and no live credential or adapter import exists.

**Step 2: Verify red**

**Step 3: Implement the thin script**

Load the JSONL ledger, call the pure audit module, attach SHA-256 file evidence, and publish with `write_immutable_json`. Exit nonzero only for technical invalidity; poor strategy or data-quality results remain reported trial evidence.

**Step 4: Document the exact command**

Add:

```bash
uv run python scripts/hypervelocity_source_live_canary_audit.py \
  --decisions data/live/hypervelocity_source_follow/decisions.jsonl \
  --database data/research/market.duckdb \
  --out data/logs/research/source_follow_live_canary_<UTC>.json
```

**Step 5: Run script tests**

Expected: pass with no network calls.

### Task 7: Generate and inspect the first real report

**Files:**
- Create at runtime: `data/logs/research/source_follow_live_canary_<UTC>.json`

**Step 1: Import the latest immutable recorder parts**

```bash
uv run python -m hypervector --data-root data research-db-live-event-import --symbol BTC
```

**Step 2: Run the audit for the active run**

Use a timestamped output path and do not overwrite prior evidence.

**Step 3: Validate the result**

Confirm the active run ID, 90 non-executable history rows, all fresh decisions, exact current venue state, explicit uncovered/partial bars, and no invented market values.

**Step 4: Run verification**

```bash
uv run ruff check src/hypervector/research/source_follow_live_audit.py \
  scripts/hypervelocity_source_live_canary_audit.py \
  tests/test_source_follow_live_audit.py \
  tests/test_source_follow_live_canary_audit_script.py
uv run pytest tests/test_source_follow_live_audit.py \
  tests/test_source_follow_live_canary_audit_script.py -q
uv run pytest tests/ -q -m "not network"
git diff --check
```

Expected: all commands exit zero; warnings remain reported separately.

### Task 8: Use evidence to select the next hypothesis

**Files:**
- Update: `docs/reviews/2026-07-31-bidirectional-canary-source-fidelity.md`

**Step 1: Record the audit findings**

Add run identity, observation window, signal/fill counts, continuous-tape coverage, candle parity, lifecycle state, limitations, confidence, and falsifiers.

**Step 2: Decide without over-gating**

Keep the current recipe frozen unless a measured discrepancy identifies a specific regime, timing, direction, re-entry, or fill hypothesis. If no qualifying trade exists, continue collecting rather than interpreting flat time as profitability evidence.


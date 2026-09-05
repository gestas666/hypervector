# BTC Deribit Option-Flow Long Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build and rigorously falsify one report-only BTC long strategy driven by causal Deribit OTM option directional flow, without changing V58 live execution.

**Architecture:** Acquire immutable official Deribit public option trades and instrument metadata, join them to immutable Hyperliquid BTC minute candles and funding, and construct a completed-hour call-versus-put directional imbalance using only information available before each decision. Run one frozen live-shaped strategy through development, purged out-of-sample, cost, delay, concentration, bootstrap, and shared-V58 competition checks; publish an append-only disposition and allow only future-only report capture after a historical pass.

**Tech Stack:** Python 3.12, `requests`, `pandas`, Parquet, gzip JSON, pytest, Ruff, existing Hypervector immutable storage and replay utilities.

---

### Task 1: Verify the frozen research contract

**Files:**
- Verify: `docs/research-journal/v58-btc-deribit-option-flow-source-qualification-20260822-v1.json`
- Verify: `docs/research-journal/v58-btc-deribit-option-flow-long-preregistration-20260822-v1.json`
- Test: `tests/test_v58_btc_deribit_option_flow_preregistration.py`

**Step 1: Write the failing contract test**

Test exact schema, hypothesis, execution authority, source bounds, exclusion policy, feature formula, causal rolling-window exclusion, partitions, costs, acceptance gates, and frozen source-qualification SHA-256.

**Step 2: Run the test and verify RED**

Run: `uv run pytest tests/test_v58_btc_deribit_option_flow_preregistration.py -q`

Expected: FAIL because the contract test does not yet exist or because an intentionally asserted required field is not yet guarded.

**Step 3: Add only the missing contract assertion or field**

Do not change any economic parameter after candidate outcomes are opened.

**Step 4: Run the test and verify GREEN**

Run: `uv run pytest tests/test_v58_btc_deribit_option_flow_preregistration.py -q`

Expected: PASS.

### Task 2: Implement bounded Deribit option-trade acquisition

**Files:**
- Create: `src/hypervector/research/deribit_option_trade_acquisition.py`
- Create: `tests/test_deribit_option_trade_acquisition.py`

**Step 1: Write failing schema tests**

Cover valid ordinary trades, missing or malformed IDs, non-unique IDs, invalid timestamps/directions/amounts/prices/IV, optional block and combo identifiers, and exact instrument metadata fields. Use dependency-injected HTTP responses; tests make no network calls.

**Step 2: Run schema tests and verify RED**

Run: `uv run pytest tests/test_deribit_option_trade_acquisition.py -q`

Expected: FAIL with missing module or symbol.

**Step 3: Implement minimal typed models and parsers**

Public functions require complete type hints and docstrings. Reject malformed source data with actionable page/window context; do not silently default required values.

**Step 4: Run schema tests and verify GREEN**

Run: `uv run pytest tests/test_deribit_option_trade_acquisition.py -q`

Expected: PASS.

**Step 5: Write failing pagination tests**

Demonstrate that an untruncated UTC-day response is accepted, `has_more=true` recursively bisects the half-open time range, overlapping boundary trades deduplicate only by identical `trade_id`, conflicting duplicates fail, and a one-millisecond truncated range fails closed.

**Step 6: Implement deterministic recursive acquisition**

Use `https://history.deribit.com/api/v2/public/get_last_trades_by_currency_and_time`, `count=10000`, `kind=option`, `include_old=true`, and ascending order. Bound recursion and requests; never interpolate response content into a URL or log secret material.

**Step 7: Run acquisition tests and verify GREEN**

Run: `uv run pytest tests/test_deribit_option_trade_acquisition.py -q`

Expected: PASS.

### Task 3: Publish immutable source bundles

**Files:**
- Modify: `src/hypervector/research/deribit_option_trade_acquisition.py`
- Create: `scripts/v58_btc_deribit_option_flow_acquire.py`
- Create: `tests/test_v58_btc_deribit_option_flow_acquire_script.py`

**Step 1: Write failing storage and command tests**

Require atomic new-directory publication, gzip raw page evidence, normalized Parquet, manifest file evidence, acquisition bounds, page/window identities, preregistration SHA-256, no candidate outcomes, no execution authority, and refusal to overwrite an existing bundle.

**Step 2: Run tests and verify RED**

Run: `uv run pytest tests/test_deribit_option_trade_acquisition.py tests/test_v58_btc_deribit_option_flow_acquire_script.py -q`

Expected: FAIL on missing storage and command behavior.

**Step 3: Implement minimal immutable publication and guarded command**

Reuse `hypervector.data.oxa_storage` helpers rather than creating new atomic-write or hashing utilities. Keep every code file below 500 lines and every function below 50 lines.

**Step 4: Run tests and verify GREEN**

Run: `uv run pytest tests/test_deribit_option_trade_acquisition.py tests/test_v58_btc_deribit_option_flow_acquire_script.py -q`

Expected: PASS.

### Task 4: Acquire and register source-only evidence

**Files:**
- Generate: `data/cache/vendor/deribit/BTC_OPTIONS/20250401T000000Z_20260801T000000Z_directional_flow_v1/`
- Generate: `data/cache/vendor/0xarchive/hyperliquid/BTC/20250401T000000000000Z_20260801T000000000000Z_candles_1m/`
- Generate: `data/cache/vendor/hyperliquid/BTC/20250401T000000000000Z_20260801T000000000000Z_funding/`
- Create: `docs/research-journal/v58-btc-deribit-option-flow-input-registration-20260822-v1.json`

**Step 1: Run the source-only Deribit command**

Run the guarded command with the frozen preregistration and exact UTC bounds. Do not load Hyperliquid returns in this command.

Expected: immutable raw and normalized option-source bundle with no candidate signals or outcomes.

**Step 2: Acquire Hyperliquid minute candles and funding**

Run the existing `oxa-candle-fetch` and `hl-funding-fetch` workflows with exact bounds. Measure cadence before any repair; reject a leading, conflicting, or greater-than-30-minute gap.

**Step 3: Register source identities**

Record paths, SHA-256, bytes, rows, timestamp bounds, duplicate counts, exclusions, gaps, retrieval times, generator hashes, and source limitations. Verify the registration itself contains no signal counts, forward returns, or trade outcomes.

### Task 5: Build the causal option-flow feature

**Files:**
- Create: `src/hypervector/research/btc_option_directional_flow.py`
- Create: `tests/test_btc_option_directional_flow.py`

**Step 1: Write failing delta and sign tests**

Test Black-Scholes call and put absolute delta, the frozen `(0.02, 0.375]` moneyness range, `[1, 21]` day maturity, contract-size weighting, and all four taker-direction/call-put bullish signs.

**Step 2: Run and verify RED**

Run: `uv run pytest tests/test_btc_option_directional_flow.py -q`

Expected: FAIL with missing module or behavior.

**Step 3: Implement minimal feature primitives**

Reject invalid values explicitly. Exclude registered block, RFQ, and combo trades before aggregation.

**Step 4: Run and verify GREEN**

Run: `uv run pytest tests/test_btc_option_directional_flow.py -q`

Expected: PASS.

**Step 5: Write failing causality tests**

Prove the current hour cannot enter its own 2160-hour quantiles, fewer than 1440 prior hours cannot signal, fewer than 20 eligible trades produce missing evidence, a signal becomes available only 60 seconds after the completed hour, and onset requires the prior eligible hour to be below the contemporaneous causal threshold.

**Step 6: Implement hourly aggregation and causal thresholds**

Do not fit or inspect alternative windows, quantiles, moneyness, maturity, or activity thresholds.

**Step 7: Run and verify GREEN**

Run: `uv run pytest tests/test_btc_option_directional_flow.py -q`

Expected: PASS.

### Task 6: Implement live-shaped economic replay

**Files:**
- Create: `src/hypervector/research/btc_option_flow_replay.py`
- Create: `tests/test_btc_option_flow_replay.py`

**Step 1: Write failing lifecycle tests**

Cover next-minute entry, 100-bps stop, 200-bps target, conservative stop-first intraminute collision, opposing-flow exit, 24-hour fallback, no overlapping position, reset-before-reentry, exact funding, fees, leverage, margin, liquidation, and partition assignment by entry time.

**Step 2: Run and verify RED**

Run: `uv run pytest tests/test_btc_option_flow_replay.py -q`

Expected: FAIL with missing module or behavior.

**Step 3: Implement the minimal replay**

Reuse existing V58 replay primitives where semantics match exactly; do not copy more than ten lines of existing logic.

**Step 4: Run and verify GREEN**

Run: `uv run pytest tests/test_btc_option_flow_replay.py -q`

Expected: PASS.

### Task 7: Orchestrate the frozen experiment and acceptance

**Files:**
- Create: `src/hypervector/research/btc_option_flow_experiment.py`
- Create: `scripts/v58_btc_deribit_option_flow_experiment.py`
- Create: `tests/test_btc_option_flow_experiment.py`
- Create: `tests/test_v58_btc_deribit_option_flow_experiment_script.py`

**Step 1: Write failing matrix and acceptance tests**

Require all four arms, three cost/delay scenarios, five development folds, two purged OOS partitions, largest-winner removal, 90% trade bootstrap, liquidation/insolvency checks, baseline comparisons, and fail-closed source/generator identity checks.

**Step 2: Run and verify RED**

Run: `uv run pytest tests/test_btc_option_flow_experiment.py tests/test_v58_btc_deribit_option_flow_experiment_script.py -q`

Expected: FAIL with missing orchestration behavior.

**Step 3: Implement reporting and immutable publication**

The command must refuse overwrite, refuse identity drift, expose no execution authority, and publish an outcome JSON only after all registered evidence is verified.

**Step 4: Run and verify GREEN**

Run: `uv run pytest tests/test_btc_option_flow_experiment.py tests/test_v58_btc_deribit_option_flow_experiment_script.py -q`

Expected: PASS.

### Task 8: Execute, disposition, and reconcile live state

**Files:**
- Generate: `docs/research-journal/v58-btc-deribit-option-flow-historical-result-20260822-v1.json`
- Create: `docs/research-journal/v58-btc-deribit-option-flow-disposition-20260822-v1.json`
- Modify only if append contract permits: the active hypothesis ledger referenced by the V58 checkpoint writer

**Step 1: Run the frozen experiment exactly once**

Do not rerun nearby parameters after outcomes open.

**Step 2: Independently reproduce the result**

Verify source hashes, generator hashes, row counts, trades, PnL arithmetic, costs, funding, partitions, controls, and every acceptance predicate.

**Step 3: Publish the disposition**

Reject permanently if any frozen gate fails. If every historical gate passes, authorize only report-only prospective capture; do not modify V58 live configuration.

**Step 4: Run focused and broad verification**

Run:

```bash
uv run pytest tests/test_v58_btc_deribit_option_flow_preregistration.py tests/test_deribit_option_trade_acquisition.py tests/test_v58_btc_deribit_option_flow_acquire_script.py tests/test_btc_option_directional_flow.py tests/test_btc_option_flow_replay.py tests/test_btc_option_flow_experiment.py tests/test_v58_btc_deribit_option_flow_experiment_script.py -q
uv run ruff check src/hypervector/research/deribit_option_trade_acquisition.py src/hypervector/research/btc_option_directional_flow.py src/hypervector/research/btc_option_flow_replay.py src/hypervector/research/btc_option_flow_experiment.py scripts/v58_btc_deribit_option_flow_acquire.py scripts/v58_btc_deribit_option_flow_experiment.py tests/test_v58_btc_deribit_option_flow_preregistration.py tests/test_deribit_option_trade_acquisition.py tests/test_v58_btc_deribit_option_flow_acquire_script.py tests/test_btc_option_directional_flow.py tests/test_btc_option_flow_replay.py tests/test_btc_option_flow_experiment.py tests/test_v58_btc_deribit_option_flow_experiment_script.py
uv run pytest tests/ -q -m "not network"
cargo test -p hypervector-tui
git diff --check
```

Expected: focused tests and lint pass; broad Python and Rust suites pass or any unrelated pre-existing failure is explicitly isolated with evidence.

**Step 5: Reconcile the live cohort without mutation**

Confirm heartbeat freshness, runtime fingerprint, positions, protective orders, fills, fees, funding, faults, and BTC route telemetry. Do not restart the cohort around an open position.


# HIP-3 Swing/HA Bidirectional Transfer Screen Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Test whether the literal Swing Auto plus Heikin-Ashi long/short mechanism transfers to `xyz:SP500` and `xyz:SPCX` under venue-matched funding and measured HIP-3 execution friction, without changing live authority.

**Architecture:** Build causal 15-minute midpoint OHLC from the verified 0xArchive L2 database, attach official hourly Hyperliquid funding, and reset indicator state across observable archive gaps. Select one bounded configuration on development only, report validation under nominal and stress friction, and keep the final chronological holdout sealed. Official recent candles validate whether the midpoint proxy is an acceptable price-path approximation.

**Tech Stack:** Python 3.13, DuckDB, pandas, existing Swing/HA signal and shared-portfolio simulators, immutable JSON/Parquet evidence.

---

### Task 1: Causal HIP-3 midpoint bars

**Files:**
- Create: `src/hypervector/research/hip3_midpoint_bars.py`
- Test: `tests/test_hip3_midpoint_bars.py`

**Step 1: Write the failing tests**

Cover exact namespaced-symbol validation, first/mid/high/low/last aggregation into 15-minute bars, observable gap markers, archive provenance requirements, and read-only database access.

**Step 2: Run tests and verify RED**

Run: `uv run pytest tests/test_hip3_midpoint_bars.py -q`

Expected: collection/import failure because the module does not exist.

**Step 3: Implement the minimum bar builder**

Use `time_bucket(INTERVAL '15 minutes', ts_utc)`, `arg_min`/`arg_max`, and exact symbol predicates over `replay_book_snapshots`. Retain sample counts, first-boundary delay, end-boundary age, and `gap_before_bars`; do not interpolate missing prices.

**Step 4: Run tests and verify GREEN**

Run: `uv run pytest tests/test_hip3_midpoint_bars.py -q`

Expected: all tests pass without network access.

### Task 2: Authentic funding and proxy validation

**Files:**
- Create: `src/hypervector/research/hip3_transfer_sources.py`
- Test: `tests/test_hip3_transfer_sources.py`

**Step 1: Write the failing tests**

Cover attachment of every official hourly funding event, accumulation across observable data gaps, no funding before the first bar, and recent official-candle comparison metrics: matched rows, absolute OHLC error quantiles, return correlation, and direction agreement.

**Step 2: Run tests and verify RED**

Run: `uv run pytest tests/test_hip3_transfer_sources.py -q`

Expected: collection/import failure because the module does not exist.

**Step 3: Implement the minimum source logic**

Accept already-fetched frames so tests remain offline. Attach each settlement to the first bar at or after its timestamp, report delayed assignments explicitly, and reject funding coverage gaps. Compare proxy and official candles only on identical timestamps.

**Step 4: Run tests and verify GREEN**

Run: `uv run pytest tests/test_hip3_transfer_sources.py -q`

Expected: all tests pass without network access.

### Task 3: Gap-aware literal Swing/HA signals

**Files:**
- Create: `src/hypervector/research/hip3_swing_signals.py`
- Test: `tests/test_hip3_swing_signals.py`

**Step 1: Write the failing tests**

Prove that the existing Heikin-Ashi chart-domain rule is used, long and short states remain symmetric, entries execute only after completed-bar decisions, pending entries do not bridge stale gaps, and signal warm-up restarts after each gap.

**Step 2: Run tests and verify RED**

Run: `uv run pytest tests/test_hip3_swing_signals.py -q`

Expected: collection/import failure because the module does not exist.

**Step 3: Implement the minimum signal adapter**

Call `build_swing_ha_chart_signals` independently per contiguous segment, concatenate in time order, block entries during causal warm-up, and publish gap-exit diagnostics. Preserve the shared simulator's next-bar-open execution rather than adding a second artificial delay.

**Step 4: Run tests and verify GREEN**

Run: `uv run pytest tests/test_hip3_swing_signals.py -q`

Expected: all tests pass.

### Task 4: Bounded development and sealed validation experiment

**Files:**
- Create: `src/hypervector/research/hip3_swing_transfer.py`
- Test: `tests/test_hip3_swing_transfer.py`

**Step 1: Write the failing tests**

Cover a chronological 60/20/20 split, three development folds, complete trial accounting, bidirectional selection preference without implicit abort gates, sealed holdout exclusion, and nominal/stress execution configurations derived from explicit fee and visible-cost evidence.

**Step 2: Run tests and verify RED**

Run: `uv run pytest tests/test_hip3_swing_transfer.py -q`

Expected: collection/import failure because the module does not exist.

**Step 3: Implement the minimum experiment**

Evaluate the frozen 72-cell base grid and 13-cell order-block challenger grid on development only. Use approximately `$75` notional for current-canary parity, effective taker fees from the evidence artifact, p90 visible cost plus a declared latency allowance for nominal friction, and p99 plus a larger allowance for stress. Report all results even when poor.

**Step 4: Run tests and verify GREEN**

Run: `uv run pytest tests/test_hip3_swing_transfer.py -q`

Expected: all tests pass.

### Task 5: Reproducible report-only command

**Files:**
- Create: `scripts/hip3_swing_ha_transfer.py`
- Test: `tests/test_hip3_swing_ha_transfer_script.py`

**Step 1: Write the failing CLI test**

Inject local fixture sources and assert immutable JSON/Parquet outputs contain source hashes, 85 searched trials, exact fee/slippage inputs, long/short results, proxy-validation evidence, `execution_authority=none`, `place_attempted=false`, and an unopened holdout declaration.

**Step 2: Run tests and verify RED**

Run: `uv run pytest tests/test_hip3_swing_ha_transfer_script.py -q`

Expected: failure because the command does not exist.

**Step 3: Implement the command**

Fetch public official funding and recent candles through existing read-only helpers, build bars from `data/research/hip3_market.duckdb`, execute the bounded experiment, and publish immutable evidence. Never construct a signing or exchange client.

**Step 4: Run focused and integration verification**

Run:

```bash
uv run pytest tests/test_hip3_midpoint_bars.py tests/test_hip3_transfer_sources.py tests/test_hip3_swing_signals.py tests/test_hip3_swing_transfer.py tests/test_hip3_swing_ha_transfer_script.py -q
uv run python scripts/hip3_swing_ha_transfer.py --database data/research/hip3_market.duckdb --symbol xyz:SP500 --symbol xyz:SPCX
```

Expected: tests pass; immutable report and trade sidecar are written; live ledger and live config hashes remain unchanged.

### Task 6: Evidence review and journal revision

**Files:**
- Create: `docs/research-journal/hip3-swing-ha-transfer-v1.json`
- Modify: `HANDOFF.md`

**Step 1: Audit the report**

Check trial count, source hashes, chronological windows, funding completeness, proxy error, both-side trade counts, PF, drawdown, fees, and sensitivity outcomes. Compare SP500 with SPCX; do not infer alpha from liquidity or correlation alone.

**Step 2: Record the falsifiable decision**

Document whether validation supports further forward observation, which result would overturn that conclusion, and that the final 20% remains sealed. No automatic live promotion is permitted.

**Step 3: Run project verification**

Run:

```bash
uv run pytest tests/ -q -m "not network"
cargo test -p hypervector-tui
uv run python -m hypervector status
```

Expected: relevant tests pass. Any unrelated repository-wide collection failure must be reported with its exact missing module or failing test rather than hidden.


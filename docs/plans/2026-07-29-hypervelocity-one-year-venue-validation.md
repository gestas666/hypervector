# Hypervelocity One-Year Venue Validation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Test the frozen Hypervelocity source-follow and regime hypotheses on one continuous year of causal, venue-matched Hyperliquid evidence without changing shadow execution authority.

**Architecture:** Extend the existing immutable hourly 0xArchive BTC L2/public-trade archive backward to 2025-07-28, verify every bundle, and incrementally materialize it in the canonical DuckDB research database. Generate strict-current and legacy source labels from canonical public-trade bars, acquire authentic mark/oracle and funding context, then replay a predeclared candidate set with identical execution assumptions. Treat the added history as a retrospective robustness challenge, not pristine forward evidence; the running no-submit shadow ledger remains the final forward stream.

**Tech Stack:** Python 3.13, DuckDB, pandas, Parquet, 0xArchive Hyperliquid REST history, official Hyperliquid funding, pytest, Ruff.

---

## Frozen experiment contract

- Venue and symbol: Hyperliquid core BTC perpetual only.
- Outer interval: `[2025-07-28T00:00:00Z, 2026-07-28T00:00:00Z)`.
- Execution: one position, post-only maker entry, public trade-through admission,
  60-second eligibility, 70% isolated margin, 40x leverage, 8% gross-margin
  target, 24-hour maximum hold, no stop.
- Friction: measured maker/taker fees, official funding, causal mark-based
  liquidation, adverse BBO liquidation execution.
- Signal range policy: completed 5-minute source bar no greater than 100 bps.
- Source revisions: current strict `ad15f2bdc949619be495a5f516babd08f7f52a90`
  and legacy `96014462c8f3911abff1babc925448893d65676d`.
- Primary fidelity candidate: current strict `TREND_DOWN` onset short, 24/7.
- Frozen session challengers: 06:00-15:00, 07:00-16:00, and 08:00-17:00
  UTC, evaluated separately. Do not search another clock boundary.
- Legacy revision is an annotation challenger because it reproduced more
  creator screenshots; it is not automatically preferred.
- Fill sensitivities are deferred until a trade-through survivor exists.
- Runtime, TUI, target, allocation, and ML authority remain unchanged.
- Performance never aborts a trial. It is recorded as the trial result in
  accordance with `SRS_HV1_NO_GATES`.

## Decision rules frozen before expanded outcomes

1. The 24/7 candidate is economically viable only if aggregate final equity is
   above initial equity and every fixed chronological 90-day slice has positive
   net PnL. Drawdown, liquidation count, fees, funding, and target rate remain
   reported diagnostics rather than hidden abort conditions.
2. The session hypothesis survives only if all three neighboring windows have
   positive aggregate PnL, at least two of three are positive in every fixed
   90-day slice, and their improvement is not produced by one shared trade.
3. Current versus legacy is decided by the same complete chronology. More
   creator matches cannot compensate for negative expectancy or a worse
   liquidation tail.
4. No result from the added history is called untouched holdout evidence: the
   candidate family was selected using the later 90-day interval. Only new
   shadow/live observations are forward evidence.
5. Outcome ML is eligible only with at least 200 resolved fills, at least 25
   minority outcomes, and at least five expanding outcome-time-purged folds
   containing both classes. Otherwise ML remains observe-only and the measured
   insufficiency is reported.
6. An ML survivor must beat a class-prior baseline on mean fold log loss and
   ROC AUC, avoid a worst-fold reversal below 0.45 AUC, and improve replay
   expectancy under a threshold frozen before final-fold evaluation. These are
   research promotion rules, not runtime execution gates.

### Task 1: Complete and audit the immutable archive

**Files:**
- Existing runner: `scripts/oxa_backfill.py`
- Existing audit: `scripts/oxa_archive_audit.py`
- Output: `data/logs/research/oxa_btc_l2_trades_1y_extension_20260729.jsonl`
- Create: `data/logs/research/oxa_btc_l2_trades_1y_audit_20260729.json`

1. Poll the existing backfill process and verify that it exits zero.
2. Confirm the terminal JSON row reports `ok=true` and the expected task count.
3. Run the archive audit over the full one-year outer interval.
4. Require 8,760 book bundles and 8,760 trade bundles, complete half-open
   coverage, advancing observed timestamps, and valid checksums.
5. Run the audit twice and verify the immutable output prevents accidental
   overwrite rather than silently replacing evidence.

Command:

```bash
uv run python scripts/oxa_archive_audit.py \
  --symbol BTC \
  --start 2025-07-28T00:00:00Z \
  --end 2026-07-28T00:00:00Z \
  --data-root data \
  --depth 20 \
  --out data/logs/research/oxa_btc_l2_trades_1y_audit_20260729.json
```

Expected: exit `0`, `checksums_verified=true`, zero missing hourly windows. Any
gap or invalid checksum stops ingestion as a technical failure.

### Task 2: Extend the canonical research database

**Files:**
- Existing implementation: `src/hypervector/data/research_database.py`
- Existing CLI: `src/hypervector/cli_oxa.py`
- Existing tests: `tests/test_research_database.py`
- Database: `data/research/market.duckdb`

1. Run the focused database tests before ingestion.
2. Build the full one-year interval; existing rows must be reused idempotently.
3. Query `research-db-status` and retain counts and time bounds.
4. Re-run the identical build and require zero newly inserted duplicate rows.
5. Compare random hourly raw-manifest counts with DuckDB canonical counts and
   preserve the known participant-fill to public-trade normalization rule.

Commands:

```bash
uv run pytest tests/test_research_database.py -q
uv run python -m hypervector --data-root data research-db-build \
  --symbol BTC --start 2025-07-28T00:00:00Z --end 2026-07-28T00:00:00Z \
  --depth 20 --database data/research/market.duckdb
uv run python -m hypervector --data-root data research-db-status \
  --database data/research/market.duckdb
```

Expected: tests pass, checksums are verified before insertion, and the second
build is idempotent.

### Task 3: Acquire causal price and funding context

**Files:**
- Existing price client: `src/hypervector/data/oxa_prices.py`
- Existing funding client: `src/hypervector/data/hl_funding_archive.py`
- Tests: `tests/test_oxa_prices.py`, `tests/test_hl_funding_archive.py`

1. Run focused price/funding tests.
2. Fetch the missing pre-window price history in a bounded immutable bundle.
3. Fetch the matching official Hyperliquid hourly funding interval.
4. Verify first/last timestamps, maximum gaps, backward-as-of semantics,
   checksums, and absence of future joins.
5. Build a context coverage report before any strategy replay.

Expected: complete causal context or an explicit technical failure. Do not
substitute candle close for missing mark/oracle values silently.

### Task 4: Generate pinned current and legacy labels

**Files:**
- Existing generator: `scripts/hypervelocity_hypertrader_labels.py`
- Current source: `data/cache/vendor/hypertrader/regime-ad15f2bd/backend`
- Legacy source: `data/cache/vendor/hypertrader/regime-96014462/backend`
- Tests: `tests/test_hypertrader_revision_labels.py`

1. Run the revision/source-hash tests.
2. Generate current labels from canonical DuckDB 5-minute public-trade bars.
3. Generate legacy labels from the identical bars and outer interval.
4. Verify 105,120 contiguous 5-minute rows per revision, five-minute causal
   availability, source hashes, distributions, and event counts.
5. Re-run into alternate temporary paths and require deterministic hashes.

Expected: source-pinned deterministic labels with no Binance input and no
future-dependent fields.

### Task 5: Replay the frozen candidate matrix

**Files:**
- Existing runner: `scripts/hypervelocity_hypertrader_maker_replay.py`
- Candidate definitions: `src/hypervector/research/hypertrader_source_adapter.py`
- Tests: `tests/test_hypertrader_recipe_direction_candidates.py`
- Tests: `tests/test_hypertrader_recipe_maker_script.py`

1. Write a failing test only if the one-year runner needs a new bounded-output
   or slice-report capability; do not add a new entry rule.
2. Run task-scoped tests and observe any failure before implementation.
3. Add only the minimum report/slicing capability required for the frozen
   matrix, with explicit types and immutable output.
4. Run current 24/7 and all three current session candidates.
5. Run the identical legacy matrix.
6. Report per-candidate aggregate and fixed 90-day slice metrics: events,
   submissions, fills, cancellations, targets, liquidations, fees, funding,
   net PnL, final equity, maximum drawdown, hold time, and fill latency.
7. Apply the frozen decision rules without tuning the candidate definitions.

Expected: every trial runs to completion unless a technical input failure
occurs. Negative economics are retained, not hidden or converted into a gate.

### Task 6: Evaluate structural and ML challengers conditionally

**Files:**
- Existing features: `src/hypervector/research/hypervelocity_metalabel.py`
- Existing model harness: `src/hypervector/ml/hypervelocity_challenger.py`
- Existing report harness: `src/hypervector/research/hypervelocity_metalabel_report.py`
- Tests: `tests/test_hypervelocity_challenger.py`
- Tests: `tests/test_hypervelocity_metalabel.py`

1. Count resolved outcomes and minority examples before fitting anything.
2. If the frozen eligibility minimum is not met, publish the counts and stop
   the ML branch without manufacturing labels.
3. If eligible, write tests for outcome-time purging and month-forward folds.
4. Fit fixed regularized logistic regression and shallow LightGBM challengers.
5. Keep GMM/HMM/Wasserstein outputs annotation-only; they may describe regime
   state but cannot become execution authority in this task.
6. Apply the frozen fold and replay screens and record every trial.

Expected: an honest observe-only model comparison or an explicit insufficient-
sample report. No model promotion occurs here.

### Task 7: Verify, document, and decide runtime disposition

**Files:**
- Modify: `docs/reviews/2026-07-29-hypervelocity-24h-source-follow.md`
- Modify: `docs/infra-data-layout.md`
- Modify: `HANDOFF.md`

1. Record archive/database/context/label/replay artifact hashes.
2. Update the review with full-year aggregate and slice results, confidence,
   failure modes, and falsifiers.
3. Run task-scoped Ruff and pytest.
4. Run `uv run pytest tests/ -q -m "not network"`.
5. Run `cargo test -p hypervector-tui` because telemetry must remain compatible.
6. Run `uv run python -m hypervector status` and verify paper remains no-submit
   and live remains fail-closed.
7. Change the faithful shadow config only if a candidate satisfies the frozen
   rules and the user approves promotion. Otherwise leave it unchanged.
8. Do not commit or push unless explicitly requested.

Good enough means a reproducible full-year report with complete causal
evidence, no silent data substitutions, every predeclared trial retained, and
an explicit promote/reject/insufficient-evidence decision. Profitability on one
retrospectively selected aggregate alone is not enough.

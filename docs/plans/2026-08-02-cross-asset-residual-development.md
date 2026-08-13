# Cross-Asset Residual Development Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Run one frozen, report-only development screen of causal five-minute cross-asset residual mean reversion with both-leg costs, funding, and explicit portfolio conflicts.

**Architecture:** Build point-in-time daily OLS hedge estimates from trailing completed five-minute log prices, annotate residual stationarity diagnostics without using future observations, and emit threshold-crossing entries in both spread directions. Replay each declared pair as one atomic two-leg position using next-minute opens, adverse fixed friction on every leg, hourly Hyperliquid funding, a residual stop/exit, maximum hold, and no execution authority. Persist every pair, including zero-trade and losing results, in one immutable artifact.

**Tech Stack:** Python 3.13, pandas, NumPy, existing Hyperliquid OHLCV/funding cache, pytest, Ruff.

---

### Task 1: Freeze the research contract

**Files:**
- Create: `src/hypervector/research/cross_asset_residual_models.py`
- Test: `tests/test_cross_asset_residual_models.py`

1. Write failing tests for the six declared unordered pairs, positive window and threshold constraints, both-leg friction, and `execution_authority="none"`.
2. Run `uv run pytest tests/test_cross_asset_residual_models.py -q` and verify failure because the module is absent.
3. Implement typed immutable configuration and trade/report records.
4. Re-run the focused test and require PASS.

### Task 2: Build causal daily residual states

**Files:**
- Create: `src/hypervector/research/cross_asset_residual_signal.py`
- Test: `tests/test_cross_asset_residual_signal.py`

1. Write failing tests proving hedge parameters for a decision day use only earlier completed bars, a future append cannot change prior rows, both positive and negative entry onsets are emitted, and invalid/missing bars fail explicitly.
2. Run the focused test and verify RED.
3. Implement trailing OLS on log prices, a lag-one residual mean-reversion coefficient and diagnostic t-statistic, trailing residual z-score, and onset-only entry events.
4. Re-run the focused test and require PASS.

### Task 3: Replay one atomic two-leg position

**Files:**
- Create: `src/hypervector/research/cross_asset_residual_replay.py`
- Test: `tests/test_cross_asset_residual_replay.py`

1. Write failing tests for next-minute entry, equal gross-dollar leg allocation adjusted by absolute hedge ratio, four execution sides per round trip, signed funding on both legs, residual mean exit, residual stop, maximum hold, asset conflict rejection, and forced end close.
2. Run the focused test and verify RED.
3. Implement the minimal state machine with one pair position at a time, no liquidation claim, explicit fixed-friction limitation, and mark-to-market drawdown.
4. Re-run the focused test and require PASS.

### Task 4: Add the immutable development runner

**Files:**
- Create: `scripts/cross_asset_residual_development.py`
- Test: `tests/test_cross_asset_residual_development_script.py`

1. Write a failing parser/fixture test that requires all six pair cells, exact half-open timestamps, source hashes, complete cost/funding fields, and report-only authority.
2. Run the focused test and verify RED.
3. Load the four exact Hyperliquid one-minute caches and funding series, form completed five-minute closes, evaluate the frozen development interval, and atomically write JSON plus Parquet trade rows.
4. Re-run the focused test and require PASS.

### Task 5: Execute one frozen development pass and review

**Files:**
- Create: `docs/reviews/2026-08-02-cross-asset-residual-development.md`
- Create: `data/logs/research/cross_asset_residual_development_v1.json`
- Create: `data/logs/research/cross_asset_residual_development_v1.trades.parquet`

1. Run `uv run python scripts/cross_asset_residual_development.py` once.
2. Check artifact hashes, all six pair cells, trade and direction attribution, cost/funding totals, maximum drawdown, and no look-ahead diagnostics.
3. Record every outcome and limitation. Do not open validation or pseudo-holdout unless a separately frozen candidate is later selected.
4. Run task-scoped pytest, Ruff, `git diff --check`, and the repository non-network suite before any completion claim.


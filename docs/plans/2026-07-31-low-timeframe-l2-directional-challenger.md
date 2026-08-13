# Low-Timeframe L2 Directional Challenger Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build and evaluate an independent BTC/SOL five-minute directional
strategy that uses causal price, public-trade-flow, and L2 microstructure
features, remains report-only, and is ranked by net profit factor after venue
friction rather than fidelity to Hypervelocity or Hypertrader.

**Architecture:** Construct one point-in-time row at each completed five-minute
bar, with every feature bounded at the decision timestamp. Generate symmetric
long and short triple-barrier outcomes from subsequent public trades, train a
regularized logistic baseline and shallow LightGBM with purged chronological
folds, and turn only out-of-sample predictions into one-position-per-symbol
trials. Preserve all thresholds and failed trials; exact public-L2/trade replay
is a later validation layer rather than being approximated by bar fills.

**Tech Stack:** Python 3.13, DuckDB, pandas, NumPy, scikit-learn, LightGBM,
pytest, Ruff, Hyperliquid public L2/trade archive.

---

## Frozen experiment contract

- Symbols: BTC and SOL, evaluated independently before any shared portfolio.
- Decision cadence: one decision after each completed 5m bar.
- Feature authority: information with exchange timestamps strictly before or
  equal to the completed-bar boundary; no forward-filled future snapshots.
- Candidate sides: both long and short rows at each eligible timestamp, with
  direction-normalized features.
- Outcome horizon: 12 completed 5m bars, or 60 minutes.
- Bar-screen barriers: 25 bps favorable and 18 bps adverse from the next-bar
  open. If both barriers occur in one bar, record `ambiguous_stop_first` and
  score the adverse barrier first. These values are development hypotheses,
  not execution defaults.
- Costs: 1.5 bps maker entry plus 4.5 bps taker exit. Slippage remains zero in
  the screening layer and must be measured in the exact event replay.
- Candidate models: expanding base rate, L2 regularized logistic, and shallow
  LightGBM. No additional model families are added after seeing validation.
- Probability thresholds: 0.55, 0.60, 0.65, and 0.70, all retained. Threshold
  ranking is development-only; validation and pseudo-holdout remain untouched.
- Collision rule: choose the side with higher probability only when it clears
  the threshold; ties mean no trade.
- Position rule: one open position per symbol; signals while occupied expire.
- Evidence role: report-only, `execution_authority=none`, `place_attempted=false`.
- Success is not an abort gate. Every trial is emitted with trade count, net
  PnL in bps, PF, win/loss counts, maximum drawdown in bps, fees, and monthly
  dispersion. PF at or below one is a valid negative result.

### Task 1: Point-in-time dataset contract

**Files:**

- Create: `src/hypervector/research/low_tf_l2_dataset.py`
- Create: `tests/test_low_tf_l2_dataset.py`

**Step 1: Write failing contract tests**

Test that a minimal 5m bar, trade, and book fixture produces one decision row
whose `available_at_utc` is exactly bar-open plus five minutes, whose last book
timestamp does not exceed availability, and whose features include:

```python
EXPECTED_FEATURES = {
    "return_1_bps",
    "return_3_bps",
    "return_12_bps",
    "realized_vol_12_bps",
    "range_bps",
    "volume_z_36",
    "trade_flow_imbalance",
    "trade_count_z_36",
    "imbalance_5_last",
    "imbalance_5_mean_60s",
    "imbalance_5_delta_60s",
    "imbalance_10_last",
    "spread_bps_last",
    "micro_price_delta_bps",
    "log_depth_10",
}
```

Also require fail-closed errors for unordered bars, duplicate bar timestamps,
future book rows, and missing history.

**Step 2: Run the tests and confirm RED**

Run:

```bash
uv run pytest tests/test_low_tf_l2_dataset.py -q
```

Expected: import failure because the module does not exist.

**Step 3: Implement the typed dataset surface**

Add `LowTimeframeDatasetConfig`, `LowTimeframeDataset`, and
`build_low_timeframe_dataset(...)`. Every public type and function has a
docstring and explicit types. Keep DuckDB access outside the pure feature
builder so fixtures require no network or database.

**Step 4: Run tests and static checks**

```bash
uv run pytest tests/test_low_tf_l2_dataset.py -q
uv run ruff check src/hypervector/research/low_tf_l2_dataset.py tests/test_low_tf_l2_dataset.py
```

Expected: all pass. Do not commit from the shared dirty worktree.

### Task 2: Triple-barrier labels without same-bar optimism

**Files:**

- Create: `src/hypervector/research/low_tf_barriers.py`
- Create: `tests/test_low_tf_barriers.py`

**Step 1: Write failing tests**

Cover long and short target-first, stop-first, timeout, missing next-open,
truncated horizon, and a candle touching both barriers. Require the ambiguous
case to resolve stop-first and retain `ambiguous=True`.

**Step 2: Confirm RED**

```bash
uv run pytest tests/test_low_tf_barriers.py -q
```

**Step 3: Implement the labeler**

Add immutable `DirectionalBarrierSpec` and `DirectionalBarrierOutcome` types
plus `label_directional_barriers(...)`. Record signal, entry, and outcome
timestamps so purge logic can remove overlapping labels.

**Step 4: Verify**

```bash
uv run pytest tests/test_low_tf_barriers.py -q
uv run ruff check src/hypervector/research/low_tf_barriers.py tests/test_low_tf_barriers.py
```

Expected: all pass. Do not commit from the shared dirty worktree.

### Task 3: Purged model challengers

**Files:**

- Create: `src/hypervector/ml/low_tf_directional_challenger.py`
- Create: `tests/test_low_tf_directional_challenger.py`
- Reuse: `src/hypervector/ml/hypervelocity_challenger.py`

**Step 1: Write failing tests**

Require expanding chronological folds whose training outcomes end before the
test embargo, deterministic predictions, both label classes in each scored
fold, and output rows containing signal side, probability, model identity, and
fold identity. Split on unique signal timestamps before expanding back to
side-specific rows, so long and short labels from one market instant cannot be
divided across train and test. Include a test proving shuffled input is
rejected.

**Step 2: Confirm RED**

```bash
uv run pytest tests/test_low_tf_directional_challenger.py -q
```

**Step 3: Implement the fixed candidate set**

Reuse `purged_walk_forward_folds` on one outcome envelope per unique signal
timestamp, then expand each fold to both side rows. Reuse `_logistic_pipeline`
and shallow `_lightgbm_params`. Do not install models. Return predictions and
diagnostics in memory; persistence belongs to the CLI boundary.

**Step 4: Verify**

```bash
uv run pytest tests/test_low_tf_directional_challenger.py -q
uv run ruff check src/hypervector/ml/low_tf_directional_challenger.py tests/test_low_tf_directional_challenger.py
```

Expected: all pass. Do not commit from the shared dirty worktree.

### Task 4: Friction-aware signal screen

**Files:**

- Create: `src/hypervector/research/low_tf_strategy_screen.py`
- Create: `tests/test_low_tf_strategy_screen.py`

**Step 1: Write failing tests**

Test one-position arbitration, expired signals while occupied, probability
ties, maker/taker fees, timeout marking, monthly attribution, and PF when there
are no losses. Require report identity fields that explicitly deny execution
authority.

**Step 2: Confirm RED**

```bash
uv run pytest tests/test_low_tf_strategy_screen.py -q
```

**Step 3: Implement screening**

Screen every fixed model/threshold combination. Use unit notional so risk
sizing cannot manufacture edge. Net trade bps equals signed price return minus
the frozen six-bps round-trip fee. Preserve ambiguous and timed-out outcomes
as separate attribution counters.

**Step 4: Verify**

```bash
uv run pytest tests/test_low_tf_strategy_screen.py -q
uv run ruff check src/hypervector/research/low_tf_strategy_screen.py tests/test_low_tf_strategy_screen.py
```

Expected: all pass. Do not commit from the shared dirty worktree.

### Task 5: Report-only DuckDB command

**Files:**

- Create: `scripts/low_tf_l2_directional_challenger.py`
- Create: `tests/test_low_tf_l2_directional_challenger_script.py`
- Modify: `skills/hypervector-cli/SKILL.md`

**Step 1: Write failing CLI tests**

Require explicit `--symbol`, `--database`, `--start`, `--end`, `--segment`,
and `--out`. Require refusal to overwrite an artifact, rejection of a database
with missing tables, and an output contract with `report_only=true`,
`execution_authority=none`, and every declared model/threshold trial.

**Step 2: Confirm RED**

```bash
uv run pytest tests/test_low_tf_l2_directional_challenger_script.py -q
```

**Step 3: Implement sequential extraction and reporting**

Query only the requested symbol/window. Aggregate book and trade features in
DuckDB before conversion to pandas. Persist one immutable JSON report plus a
Parquet prediction sidecar, both with SHA-256 input identities. Never expose a
live flag or construct an execution client.

**Step 4: Verify**

```bash
uv run pytest tests/test_low_tf_l2_directional_challenger_script.py -q
uv run ruff check scripts/low_tf_l2_directional_challenger.py tests/test_low_tf_l2_directional_challenger_script.py
```

Expected: all pass. Do not commit from the shared dirty worktree.

### Task 6: Frozen chronological evaluation

**Files:**

- Create: `data/logs/research/low_tf_l2_directional_<symbol>_<segment>_v1.json`
- Create: `data/logs/research/low_tf_l2_directional_<symbol>_<segment>_v1.parquet`
- Create: `docs/reviews/2026-08-01-low-timeframe-l2-directional-challenger.md`

**Step 1: Generate development evidence**

Use the first 60% of each symbol's common candle/L2/trade coverage. Run BTC and
SOL separately and retain every model/threshold result.

**Step 2: Freeze development ranking**

Select one model/threshold per symbol solely from development net PF, with
trade count and drawdown reported as uncertainty rather than hidden gates.

**Step 3: Generate validation and pseudo-holdout evidence**

Use the next 20% and final 20% unchanged. Do not retune after either segment.

**Step 4: Publish the comparison**

Report PF, trades, net bps, maximum drawdown, win/loss mix, ambiguous-bar count,
fees, and monthly dispersion. Explicitly state that bar evidence does not prove
private maker fills or slippage.

### Task 7: Exact event replay for the frozen winner

**Files:**

- Create: `src/hypervector/research/low_tf_event_replay.py`
- Create: `tests/test_low_tf_event_replay.py`
- Create: `scripts/low_tf_event_replay.py`

**Step 1: Write failing finite-depth tests**

Cover post-only entry, public trade-through, queue-ahead consumption, partial
fills, taker exit depth walking, funding, mark liquidation, archive gaps, and
one-position state restoration.

**Step 2: Implement by composing existing execution primitives**

Reuse the source-follow event matcher and portfolio accounting. Do not copy
more than ten lines of existing lifecycle logic.

**Step 3: Replay only the frozen validation candidates**

Preserve bar-versus-event fill conversion, measured slippage, fees, funding,
liquidations, and all rejected entries.

**Step 4: Verify and decide forward observation**

If event replay is economically positive, start a no-submit observer beside
the current baseline. If it is negative, retain the result and return to the
fixed candidate list rather than changing the holdout definition.

## Validation boundary

This plan does not authorize stopping or restarting the current BTC canary,
placing an order, or installing model authority. A profitable bar screen is
insufficient for promotion. A candidate becomes live-relevant only after its
unchanged event replay and forward observer preserve positive net PF with no
accounting or data-quality fault.

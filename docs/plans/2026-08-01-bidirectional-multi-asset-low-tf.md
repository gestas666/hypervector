# Bidirectional Multi-Asset Low-Timeframe Implementation Plan

> **For Codex:** Use the project `hypervector-cli` and
> `hypervector-regime-detector` skills plus test-driven development. Execute each
> task in order; do not arm live execution from this plan.

**Goal:** Select a genuine long-and-short 5m strategy cohort for BTC, ETH, SOL,
and HYPE using one year of venue-matched data, realistic costs, chronological
validation, and one shared $15,000 research portfolio.

**Architecture:** Build pure completed-bar feature and signal modules, retain
every declared trial in DuckDB/JSON evidence, and execute signals only through a
next-bar, friction-aware replay. Keep source-derived rules, new mechanical
hypotheses, and asset extrapolations explicitly separate. Evaluate each
asset/side first, then combine frozen survivors through one shared-capital event
stream. `xyz:SP500` remains a separate HIP-3 qualification track because its
oracle, session behavior, and available history differ from native crypto perps.

**Tech Stack:** Python 3.13, pandas, NumPy, DuckDB, pytest, Ruff, existing
Hypervector indicator, funding, liquidation, and shared-portfolio components.

---

## Frozen experiment contract

### Inputs and timing

- Native assets: `BTC`, `ETH`, `SOL`, `HYPE`.
- Source bars: immutable Hyperliquid 1m caches, aggregated to complete 5m bars.
- Decision clock: completed 5m bar; entry at the following 5m open.
- Context clock: completed 15m bar available only after its close.
- Warmup: retained outside each scored segment and excluded from results.
- Development: `[2025-07-28, 2026-01-28)`.
- Validation: `[2026-01-28, 2026-04-28)`.
- Pseudo-holdout: `[2026-04-28, 2026-07-28)`.
- Research cadence objective: one to three qualified shared-portfolio entries per
  day. This is diagnostic only; the engine must not manufacture trades.

### Execution and portfolio assumptions

- Starting research equity: `$15,000` shared by all assets and signal families.
- Isolated margin, one position per asset, at most two simultaneous positions.
- Base risk budget: `0.50%` of current equity per trade; total open risk at most
  `1.00%`. Leverage controls margin efficiency, not the dollar risk budget.
- Initial research leverage: `5x` for every asset, below the current documented
  venue maxima. Venue metadata must be re-read before any canary.
- Nominal all-in round-trip friction: `13 bps`.
- Stress all-in round-trip friction: `20 bps`.
- Funding is settled from the available venue series and reported separately.
- Intrabar ordering uses the underlying 1m path. Same-1m-bar stop/target
  ambiguity resolves adversely and is counted.
- Liquidation is evaluated before stop and target. No trial may omit
  liquidation, fees, slippage, funding, or forced-end closure.
- Paper/research authority only. Live arming remains a separate explicit action.

### Candidate cohort

1. `range_reclaim_v1`
   - Source-backed core: an established range is breached, price closes back
     inside, and the range midpoint is the primary resolution target.
   - Mechanical hypotheses: prior 240-bar high/low zones, minimum 100 bps range,
     10 bps long sweep and 15 bps short sweep, no more than five completed closes
     outside, 24-bar maximum hold.
   - Stop variants declared before replay: close outside the reclaimed zone; or
     wick extreme plus one 5m ATR fraction. No arbitrary 15 bps stop.

2. `trend_expansion_v1`
   - Source-backed core: completed 15m 21/55 EMA direction and slope, with 5m
     BBWP expansion confirming a volatility breakout.
   - Mechanical hypotheses: prior 120-bar boundary; 8 bps long and 12 bps short
     clearance; prior BBWP at or below 20; current BBWP above its 5-bar signal and
     rising; 48-bar maximum hold.
   - Exit variants: 5m RSI/EMA opposite cross, or 5m 21/55 loss of alignment,
     each protected by a structure/ATR stop.

3. `pmarp_exhaustion_v1`
   - Source-backed core: PMARP 20/80 extremes and high BBWP identify a possible
     mean-reversion state.
   - Mechanical hypotheses: PMARP extreme plus completed reversal cross and a
     minimum 60 bps distance to the 5m 21 EMA; 12-bar maximum hold.
   - This is the lowest-priority challenger. It receives the same ledger and is
     not promoted merely for increasing cadence.

Simple 5m moving-average crossover is a negative control, not a candidate.

### Trial limits and reporting

- Three signal families, two sides, four assets, and two declared exit variants.
- Thresholds above are fixed for the first development run. One bounded
  sensitivity pass may test `±20%` for the mechanical thresholds.
- No new thresholds after validation begins. Every attempted cell remains in the
  trial ledger, including zero-trade and insolvent outcomes.
- Report per asset, side, family, segment, and month: signals, filled trades,
  cadence, gross/net bps, dollar PnL, win rate, payoff ratio, profit factor,
  maximum drawdown, MAE/MFE, holding time, fees, slippage, funding,
  liquidations, ambiguity count, and capacity conflicts.
- Also report buy-and-hold and flat-cash references; neither grants strategy
  authority.

## Task 1: Freeze and validate the data contract

**Files:**

- Create: `src/hypervector/research/low_tf_multi_asset_contract.py`
- Create: `tests/test_low_tf_multi_asset_contract.py`

**Steps:**

1. Write failing tests for supported assets, date boundaries, 5m/15m completed
   aggregation, warmup exclusion, immutable input hashes, and asset-specific
   venue leverage metadata.
2. Implement typed frozen contract objects and actionable validation errors.
3. Assert an appended future bar cannot change any earlier 5m/15m value.
4. Run the focused tests and Ruff.

## Task 2: Build causal feature frames

**Files:**

- Create: `src/hypervector/research/low_tf_multi_asset_features.py`
- Create: `tests/test_low_tf_multi_asset_features.py`

**Steps:**

1. Write golden-vector tests for prior-window range zones, EMA 21/55 direction
   and slope, BBWP 20/240 plus 5-bar signal, RSI 14 plus EMA 7, PMARP 21/350,
   ATR, and completed 15m context alignment.
2. Ensure structural windows use `[t-lookback, t-1]`; current-bar high/low must
   not define the boundary being broken.
3. Implement by reusing existing indicators. Do not create duplicate EMA, RSI,
   BBWP, PMARP, or ATR math.
4. Test warmup unknowns, missing bars, duplicate bars, and append invariance.

## Task 3: Emit auditable long and short signals

**Files:**

- Create: `src/hypervector/research/low_tf_multi_asset_signals.py`
- Create: `tests/test_low_tf_multi_asset_signals.py`

**Steps:**

1. Write failing fixtures for both sides of every candidate and for each vetoing
   condition in isolation.
2. Emit decision time, symbol, family, side, variant, source-backed facts,
   hypothesis facts, stop anchor, target anchor, and reason.
3. Preserve simultaneous/contradictory signals for the portfolio layer to rank;
   do not silently filter them.
4. Prove signals at time `t` are unchanged when future bars are appended.

## Task 4: Replay against the 1m path with full friction

**Files:**

- Create: `src/hypervector/research/low_tf_multi_asset_replay.py`
- Create: `src/hypervector/research/low_tf_multi_asset_models.py`
- Create: `tests/test_low_tf_multi_asset_replay.py`

**Steps:**

1. Write lifecycle tests for next-open entry, gaps, stop/target ordering,
   same-1m ambiguity, funding, liquidation, max hold, and end-of-data closure.
2. Implement risk-based quantity from stop distance and current shared equity.
3. Apply 13 bps nominal and 20 bps stress as total round-trip friction without
   double counting.
4. Assert the accounting identity and exact quantity reconciliation for every
   test trade.

## Task 5: Run declared chronological evidence

**Files:**

- Create: `scripts/low_tf_multi_asset_screen.py`
- Create: `tests/test_low_tf_multi_asset_screen_script.py`
- Create: `data/logs/research/low_tf_multi_asset_<segment>_v1.json`

**Steps:**

1. Record every development cell in DuckDB and immutable JSON.
2. Run the single bounded threshold sensitivity pass on development only.
3. Freeze one variant per family/side before validation.
4. Run validation unchanged, then pseudo-holdout unchanged.
5. Run cost, one-bar delay, and stop-distance perturbations without retuning.

## Task 6: Build the shared-capital comparison

**Files:**

- Create: `src/hypervector/research/low_tf_multi_asset_portfolio.py`
- Create: `tests/test_low_tf_multi_asset_portfolio.py`
- Create: `docs/reviews/2026-08-01-bidirectional-multi-asset-low-tf.md`

**Steps:**

1. Merge frozen asset signals into one ordered event stream.
2. Enforce one position per asset, two positions total, and shared risk/equity.
3. Rank same-time candidates deterministically using development-frozen utility,
   then symbol; report every rejected conflict.
4. Publish per-side, per-asset, per-family, monthly, and total portfolio results
   with confidence limits and explicit failure modes.

## Task 7: Qualify `xyz:SP500` separately

**Files:**

- Create: `docs/reviews/2026-08-01-xyz-sp500-data-qualification.md`

**Steps:**

1. Record current HIP-3 metadata, oracle provenance, trading hours, funding,
   leverage tiers, inception, and available candle/trade history.
2. Verify sufficient chronological coverage and gap behavior before reusing any
   candidate.
3. Report it separately; do not pool it with crypto merely to improve totals.

## Task 8: Prepare shadow/TUI and canary only after selection

**Files:** Determined by the selected frozen survivor.

**Steps:**

1. Add a fail-closed backend controller and telemetry projection; the TUI remains
   a read-only representation of backend state.
2. Show strategy family, symbol, side, 5m decision facts, 15m context, stop,
   target, liquidation, fees, funding, shared risk, and rejection reasons.
3. Verify restart/reconciliation, kill switch, stale data, order ambiguity, and
   rollback behavior in shadow.
4. Arm a live canary only on a new explicit `--enabled
   --i-accept-live-risk` instruction and collect real execution evidence before
   any scale decision.

## Validation standard

This plan does not assume a winning strategy exists. A credible survivor must
remain positive after all declared costs in untouched chronological evidence,
avoid dependence on one asset/month/side, and retain acceptable behavior under
the declared perturbations. Failure to meet that standard updates confidence
downward but remains a reported result rather than an implicit trial abort.

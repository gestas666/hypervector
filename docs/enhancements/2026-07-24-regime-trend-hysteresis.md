# Enhancement: Hysteresis Trend State Machine for the Ultimate Regime Engine

- **Date:** 2026-07-24
- **Status:** Proposed (not implemented)
- **Target:** `src/hypervector/regime/ultimate.py` (`detect_ultimate_regime`, momentum-expansion tier)
- **Source of insight:** trend-related Pine Scripts in `reference/pine-scripts/`

## Proposal

Replace the raw `EMA12 > EMA48` sign comparison in the momentum tier of
`detect_ultimate_regime` with the volatility-banded hysteresis trend state
machine already ported to `src/hypervector/strategies/indicators.py` as
`zero_lag_trend_ohlc`, applied on both the 1m and HTF (15m/5m) legs.

## Evidence from the Pine Scripts

Every serious trend script in `reference/pine-scripts/` converges on the same
core mechanic; the regime engine is the only trend consumer not using it:

| Script | Trend mechanic |
|---|---|
| `zero_lag_trend_signals.pine` | ZLEMA ± ATR-band, sticky `var trend` state (flips only on band cross) |
| `ML_adaptive_supertrend.pine` | Supertrend trailing band, k-means adaptive ATR |
| `optimized_trend_tracker.pine` | CMO-adaptive VAR MA + percent trailing stop with ratchet |
| `self-learning-supertrend.pine` | `trend := close < lowerBand ? -1 : close > upperBand ? 1 : previousTrend` |
| `trend_state.pine` | Persistent `state` var with explicit losing/damaged transitions |

Shared insight: **trend is a state with hysteresis, not an instantaneous MA
sign.**

## Problem with the current implementation

`detect_ultimate_regime` classifies `BULL/BEAR_MOMENTUM_EXPANSION` from
`ef_1m > es_1m` AND the same comparison on the HTF. This has both dominant
error modes at once:

1. **Whipsaw:** the EMA sign flips repeatedly around crossings, so the
   residual else-branch bleeds momentum bars into `RANGE_CHOP_HIGH_FRICTION`
   and destroys persistence stats.
2. **Lag:** EMA48 confirms late, so momentum-expansion states get stamped
   after much of the move is gone, directly degrading the mean forward-return
   edge that `regime-eval` measures.

ZLEMA (lag-corrected) addresses (2); the ATR-scaled band flip addresses (1).
It is the exact `var trend` machine from `zero_lag_trend_signals.pine`,
already implemented, tested, and unused by the regime engine.

## Implementation sketch (~10 lines changed in `ultimate.py`)

```python
_, t_1m = zero_lag_trend_ohlc(h, l, c, length=70, mult=1.2)
# HTF resample must aggregate high/max, low/min, close/last (today it's close-only)
_, t_htf = zero_lag_trend_ohlc(h15, l15, c15, length=70, mult=1.2)
t_htf = t_htf.shift(1).reindex(c.index, method="ffill")  # keep the lookahead fix
macro_bull = (t_1m == 1) & (t_htf == 1)
macro_bear = (t_1m == -1) & (t_htf == -1)
```

Note: the internal 5m/15m resampling currently aggregates `close` only; it
must also aggregate `high` (max) and `low` (min) to feed the OHLC variant.

## Why this is the highest +EV single change

- **Cost ~zero:** the indicator exists in `indicators.py`, is tested, and
  mirrors a trusted script; only the HTF resample needs `high`/`low` added.
- **Directly measurable:** before/after via
  `uv run python -m hypervector regime-eval --symbol BTC --timeframe 5m --lookback 180`
  (persistence, mean forward bps, win %, Sharpe per state).
- **Charter-safe:** pure label-fidelity change; regime outputs stay
  research-only reporting (SRS_HV1_REGIME, SRS_HV1_REGIME_NO_GATE); no gating
  introduced or touched.
- **Beats the alternatives:**
  - Wiring real ADX (the `adx_threshold` param is currently dead code) adds
    lag for marginal gain.
  - K-means adaptive ATR (`ML_adaptive_supertrend.pine`) is a good phase-2
    refinement on top of this, but costs more to validate.

## Side observations (reconcile when touching the file)

The `ultimate.py` docstring promises ADX > 25 and "OI Up", but
`adx_threshold`, `oi_ret`, `r_1m`, and the `ef_arr`/`es_arr` numpy conversions
are all computed-and-unused dead code.

## Validation plan

1. Run `regime-eval` on BTC 5m, 180d lookback, before the change; record
   per-state persistence, mean forward-return bps, win %, Sharpe.
2. Apply the change; rerun with identical arguments; compare.
3. Run `uv run pytest tests/ -q -m "not network"` and
   `cargo test -p hypervector-tui`.
4. No promotion/gating criteria attached: results are reported either way
   per charter.

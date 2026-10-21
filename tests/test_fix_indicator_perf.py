"""Golden tests for the vectorised indicators and the scoped indicator cache.

The optimised squeeze_momentum linreg and the chunked percentile_rank must be
bit-for-bit identical to the original implementations (copied here verbatim
as references), including NaN propagation and degenerate window lengths.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from hypervector.strategies import indicators as ind


def _reference_linreg(delta: pd.Series, kc_length: int) -> pd.Series:
    def _linreg_last(window: np.ndarray) -> float:
        y = window.astype(float)
        if np.any(np.isnan(y)):
            return np.nan
        x = np.arange(len(y), dtype=float)
        x = x - x.mean()
        y = y - y.mean()
        denom = (x * x).sum()
        if denom == 0:
            return 0.0
        slope = (x * y).sum() / denom
        return float(slope * x[-1] + window.mean())

    return delta.rolling(kc_length, min_periods=kc_length).apply(_linreg_last, raw=True)


def _reference_percentile_rank(series: pd.Series, lookback: int) -> pd.Series:
    s = series.astype(float).to_numpy().copy()
    n = len(s)
    out = np.full(n, np.nan, dtype=float)
    min_periods = max(lookback // 4, 5)
    if n < min_periods:
        return pd.Series(out, index=series.index)
    for i in range(min_periods - 1, min(lookback - 1, n)):
        window = s[: i + 1]
        x = window[-1]
        if np.isnan(x):
            continue
        valid = window[~np.isnan(window)]
        if valid.size:
            out[i] = 100.0 * float(np.sum(valid <= x)) / float(valid.size)
    if n >= lookback:
        windows = np.lib.stride_tricks.sliding_window_view(s, lookback)
        last = windows[:, -1]
        valid = ~np.isnan(windows)
        le = (windows <= last[:, None]) & valid
        counts = valid.sum(axis=1).astype(float)
        le_counts = le.sum(axis=1).astype(float)
        ranks = np.where(counts > 0, 100.0 * le_counts / counts, np.nan)
        ranks = np.where(np.isnan(last), np.nan, ranks)
        out[lookback - 1 :] = ranks
    return pd.Series(out, index=series.index)


def _reference_supertrend(high, low, close, *, atr_period=10, multiplier=3.0):
    h = high.astype(float).to_numpy()
    lows = low.astype(float).to_numpy()
    c = close.astype(float).to_numpy()
    n = len(c)
    tr = ind.true_range(high, low, close).to_numpy()
    atr_arr = pd.Series(tr).ewm(alpha=1.0 / atr_period, min_periods=atr_period, adjust=False).mean().to_numpy()
    hl2 = (h + lows) / 2.0
    upper = hl2 + multiplier * atr_arr
    lower = hl2 - multiplier * atr_arr
    st = np.full(n, np.nan)
    direction = np.ones(n, dtype=int)
    for i in range(1, n):
        if np.isnan(atr_arr[i]):
            direction[i] = direction[i - 1]
            st[i] = st[i - 1]
            continue
        if c[i - 1] > lower[i - 1] if not np.isnan(lower[i - 1]) else False:
            lower[i] = max(lower[i], lower[i - 1]) if not np.isnan(lower[i - 1]) else lower[i]
        if c[i - 1] < upper[i - 1] if not np.isnan(upper[i - 1]) else False:
            upper[i] = min(upper[i], upper[i - 1]) if not np.isnan(upper[i - 1]) else upper[i]
        if direction[i - 1] == 1:
            direction[i] = -1 if c[i] < lower[i] else 1
        else:
            direction[i] = 1 if c[i] > upper[i] else -1
        st[i] = lower[i] if direction[i] == 1 else upper[i]
    return st, direction


def _reference_sticky_trend(cv: np.ndarray, up: np.ndarray, lo: np.ndarray) -> np.ndarray:
    trend = np.zeros(len(cv), dtype=int)
    t = 0
    for i in range(len(cv)):
        if np.isnan(up[i]) or np.isnan(lo[i]):
            trend[i] = t
            continue
        if cv[i] > up[i]:
            t = 1
        elif cv[i] < lo[i]:
            t = -1
        trend[i] = t
    return trend


def _ohlc(n: int, seed: int = 3) -> tuple[pd.Series, pd.Series, pd.Series]:
    rng = np.random.default_rng(seed)
    close = 30_000.0 * np.exp(np.cumsum(rng.normal(0.0, 0.002, n)))
    high = close * (1.0 + np.abs(rng.normal(0.0, 0.001, n)))
    low = close * (1.0 - np.abs(rng.normal(0.0, 0.001, n)))
    return pd.Series(high), pd.Series(low), pd.Series(close)


def _squeeze_delta(high: pd.Series, low: pd.Series, close: pd.Series, kc_length: int) -> pd.Series:
    mid = (
        high.rolling(kc_length, min_periods=kc_length).max()
        + low.rolling(kc_length, min_periods=kc_length).min()
    ) / 2.0
    mid = (mid + ind.sma(close, kc_length)) / 2.0
    return close - mid


@pytest.mark.parametrize("kc_length", [1, 2, 5, 20])
def test_squeeze_momentum_matches_the_rolling_apply_reference_exactly(kc_length: int) -> None:
    high, low, close = _ohlc(3_000)
    close.iloc[[50, 51, 900, 2_000]] = np.nan  # NaN gaps propagate through windows

    mom, on, off = ind.squeeze_momentum(high, low, close, kc_length=kc_length)
    expected = _reference_linreg(_squeeze_delta(high, low, close, kc_length), kc_length)

    assert mom.index.equals(close.index)
    np.testing.assert_array_equal(mom.to_numpy(), expected.to_numpy())
    assert on.dtype == bool and off.dtype == bool


@pytest.mark.parametrize(("atr_period", "multiplier"), [(10, 3.0), (14, 2.5), (3, 1.0)])
def test_supertrend_loop_matches_the_reference_exactly(atr_period: int, multiplier: float) -> None:
    high, low, close = _ohlc(4_000, seed=atr_period)
    high.iloc[[700, 701]] = np.nan
    low.iloc[[1_500]] = np.nan

    line, direction = ind.supertrend(high, low, close, atr_period=atr_period, multiplier=multiplier)
    ref_line, ref_direction = _reference_supertrend(
        high, low, close, atr_period=atr_period, multiplier=multiplier
    )

    np.testing.assert_array_equal(line.to_numpy(), ref_line)
    np.testing.assert_array_equal(direction.to_numpy(), ref_direction)
    assert direction.dtype == ref_direction.dtype


def test_zero_lag_trends_match_the_reference_loop_exactly() -> None:
    high, low, close = _ohlc(3_000, seed=17)
    close.iloc[[100, 2_000]] = np.nan

    zlema, trend = ind.zero_lag_trend_ohlc(high, low, close, length=30, mult=1.1)
    vol = ind.atr(high, low, close, 30).rolling(90, min_periods=30).max() * 1.1
    expected = _reference_sticky_trend(
        close.to_numpy(), (zlema + vol).to_numpy(), (zlema - vol).to_numpy()
    )
    np.testing.assert_array_equal(trend.to_numpy(), expected)

    zl_close, trend_close = ind.zero_lag_trend(close, length=40, mult=1.3)
    proxy = close.diff().abs().ewm(alpha=1.0 / 40, min_periods=40, adjust=False).mean()
    vol_c = proxy.rolling(120, min_periods=40).max() * 1.3
    expected_c = _reference_sticky_trend(
        close.to_numpy(), (zl_close + vol_c).to_numpy(), (zl_close - vol_c).to_numpy()
    )
    np.testing.assert_array_equal(trend_close.to_numpy(), expected_c)


def test_squeeze_momentum_short_input_is_all_nan() -> None:
    high, low, close = _ohlc(10)
    mom, _, _ = ind.squeeze_momentum(high, low, close, kc_length=20)
    assert mom.isna().all()
    assert len(mom) == 10


def test_squeeze_linreg_chunking_is_exact(monkeypatch: pytest.MonkeyPatch) -> None:
    high, low, close = _ohlc(2_500, seed=8)
    reference, _, _ = ind.squeeze_momentum(high, low, close)
    monkeypatch.setattr(ind, "_WINDOW_CHUNK_ROWS", 97)
    chunked, _, _ = ind.squeeze_momentum(high, low, close)
    np.testing.assert_array_equal(chunked.to_numpy(), reference.to_numpy())


@pytest.mark.parametrize("lookback", [8, 20, 252])
def test_percentile_rank_chunked_matches_reference_exactly(
    lookback: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, close = _ohlc(4_000, seed=12)
    width = ind.bollinger_width(close, 20)
    width.iloc[[300, 301, 302, 2_500]] = np.nan
    monkeypatch.setattr(ind, "_WINDOW_CHUNK_ROWS", 333)

    got = ind.percentile_rank(width, lookback)
    expected = _reference_percentile_rank(width, lookback)

    np.testing.assert_array_equal(got.to_numpy(), expected.to_numpy())


def test_indicator_cache_returns_identical_results_and_counts_hits() -> None:
    high, low, close = _ohlc(2_000, seed=4)
    uncached = ind.supertrend(high, low, close, atr_period=10, multiplier=3.0)

    with ind.indicator_cache() as stats:
        first = ind.supertrend(high.copy(), low.copy(), close.copy(), atr_period=10, multiplier=3.0)
        second = ind.supertrend(high.copy(), low.copy(), close.copy(), atr_period=10, multiplier=3.0)
        other = ind.supertrend(high, low, close, atr_period=14, multiplier=3.0)
        # caller-side mutation must not leak into later cache hits
        first[0].iloc[:] = -1.0
        third = ind.supertrend(high, low, close, atr_period=10, multiplier=3.0)

    assert stats.misses == 2
    assert stats.hits == 2
    for got in (second, third):
        pd.testing.assert_series_equal(got[0], uncached[0])
        pd.testing.assert_series_equal(got[1], uncached[1])
    assert not other[0].equals(uncached[0])


def test_indicator_cache_distinguishes_values_and_index() -> None:
    high, low, close = _ohlc(500, seed=6)
    with ind.indicator_cache() as stats:
        base = ind.zero_lag_trend_ohlc(high, low, close, length=20)
        bumped = ind.zero_lag_trend_ohlc(high, low, close * 1.01, length=20)
        shifted_index = ind.zero_lag_trend_ohlc(
            high.set_axis(high.index + 1), low.set_axis(low.index + 1), close.set_axis(close.index + 1), length=20
        )
    assert stats.hits == 0  # nested cached atr() calls also miss
    assert not base[0].equals(bumped[0])
    assert shifted_index[0].index.equals(close.index + 1)


def test_indicator_cache_memory_is_bounded() -> None:
    high, low, close = _ohlc(1_000, seed=9)
    one_result = 1_000 * 8 * 2  # supertrend: float line + int direction
    with ind.indicator_cache(max_bytes=2 * one_result) as stats:
        for multiplier in (1.0, 2.0, 3.0):
            ind.supertrend(high, low, close, multiplier=multiplier)
        again = ind.supertrend(high, low, close, multiplier=1.0)  # evicted -> recomputed
        recent = ind.supertrend(high, low, close, multiplier=3.0)  # still cached

    assert stats.evictions >= 1
    assert stats.misses == 4 and stats.hits == 1
    pd.testing.assert_series_equal(again[0], ind.supertrend(high, low, close, multiplier=1.0)[0])
    pd.testing.assert_series_equal(recent[0], ind.supertrend(high, low, close, multiplier=3.0)[0])


def test_indicators_are_uncached_outside_a_cache_scope() -> None:
    high, low, close = _ohlc(300, seed=2)
    a = ind.supertrend(high, low, close)
    b = ind.supertrend(high, low, close)
    assert a[0] is not b[0]
    pd.testing.assert_series_equal(a[0], b[0])


def test_grid_search_results_match_uncached_per_trial_evaluation() -> None:
    from hypervector.data.sources import fixture_ohlcv
    from hypervector.strategies.registry import StrategySpec
    from hypervector.sweep.costs import resolve_cost_model
    from hypervector.sweep.metrics import compute_trial_metrics
    from hypervector.sweep.search import run_grid_search

    def supertrend_chop_long(
        df: pd.DataFrame, st_atr: int = 10, st_mult: float = 3.0, chop_max: float = 60.0
    ):
        """Test builder over cached indicators (supertrend, choppiness)."""
        _, trend = ind.supertrend(
            df["high"], df["low"], df["close"], atr_period=st_atr, multiplier=st_mult
        )
        chop = ind.choppiness_index(df["high"], df["low"], df["close"], 14)
        turned_up = (trend == 1) & (trend.shift(1) == -1)
        turned_down = (trend == -1) & (trend.shift(1) == 1)
        entries = (turned_up & (chop < chop_max)).fillna(False)
        return entries.astype(bool), turned_down.fillna(False).astype(bool), "long"

    spec = StrategySpec("test_supertrend_chop_long", "uptrend", {}, supertrend_chop_long)
    df = fixture_ohlcv(n_bars=1_200, drift=0.5, wave_period=80)
    grid = {"st_atr": [10], "st_mult": [2.5, 3.0], "chop_max": [45.0, 60.0]}
    cost = resolve_cost_model("hl_base_taker")
    results = run_grid_search(df, spec, param_grid=grid, cost=cost)
    assert all(r.status == "ok" for r in results)
    assert any(r.metrics["trade_count"] > 0 for r in results)
    for r in results:
        build = {k: v for k, v in r.params.items() if k != "exit_mode"}
        entries, exits, direction = spec.build_signals(df, **build)
        fresh = compute_trial_metrics(df["close"], entries, exits, direction=direction, df=df, cost=cost)
        assert r.metrics["net_pnl"] == fresh["net_pnl"]
        assert r.metrics["trade_count"] == fresh["trade_count"]

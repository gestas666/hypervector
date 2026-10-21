"""Indicator building blocks for strategies (pure pandas/numpy).

Expensive indicators are pure functions of their input values, index and
parameters. Inside an :func:`indicator_cache` scope (opened by the grid search
for one bar frame) repeated calls with identical inputs reuse the first result,
so parameter-invariant indicators are computed once per search instead of once
per trial. Outside a scope nothing is cached.
"""

from __future__ import annotations

import contextvars
import functools
import hashlib
import inspect
import math
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, TypeVar

import numpy as np
import pandas as pd

# Rows per block for sliding-window temporaries (bounds peak memory to
# O(rows x window) instead of O(bars x window)).
_WINDOW_CHUNK_ROWS = 32_768

_F = TypeVar("_F", bound=Callable[..., Any])


@dataclass
class IndicatorCacheStats:
    """Hit/miss counters for one :func:`indicator_cache` scope."""

    hits: int = 0
    misses: int = 0
    evictions: int = 0


# Default memory budget for one scope; least recently used results are evicted
# beyond it, so a wide grid on a long lookback cannot grow memory unboundedly.
DEFAULT_INDICATOR_CACHE_BYTES = 256 * 1024 * 1024


class _IndicatorCache:
    """Byte-bounded LRU of indicator results keyed by input content."""

    def __init__(self, max_bytes: int) -> None:
        self.max_bytes = int(max_bytes)
        self.entries: dict[tuple[Any, ...], tuple[Any, int]] = {}
        self.total_bytes = 0
        self.stats = IndicatorCacheStats()

    def get(self, key: tuple[Any, ...]) -> tuple[bool, Any]:
        entry = self.entries.pop(key, None)
        if entry is None:
            self.stats.misses += 1
            return False, None
        self.entries[key] = entry  # most recently used goes last
        self.stats.hits += 1
        return True, entry[0]

    def put(self, key: tuple[Any, ...], value: Any) -> None:
        size = _result_bytes(value)
        if size > self.max_bytes:
            return
        self.entries[key] = (value, size)
        self.total_bytes += size
        while self.total_bytes > self.max_bytes and self.entries:
            oldest = next(iter(self.entries))
            self.total_bytes -= self.entries.pop(oldest)[1]
            self.stats.evictions += 1


_ACTIVE_CACHE: contextvars.ContextVar[_IndicatorCache | None] = contextvars.ContextVar(
    "hypervector_indicator_cache", default=None
)


@contextmanager
def indicator_cache(
    max_bytes: int = DEFAULT_INDICATOR_CACHE_BYTES,
) -> Iterator[IndicatorCacheStats]:
    """Memoize cached indicators by input content for the duration of the scope."""
    cache = _IndicatorCache(max_bytes)
    token = _ACTIVE_CACHE.set(cache)
    try:
        yield cache.stats
    finally:
        _ACTIVE_CACHE.reset(token)


def _result_bytes(value: Any) -> int:
    if isinstance(value, pd.Series):
        return int(value.to_numpy().nbytes)
    if isinstance(value, np.ndarray):
        return int(value.nbytes)
    if isinstance(value, tuple):
        return sum(_result_bytes(item) for item in value)
    return 64


def _digest(values: np.ndarray) -> str:
    data = np.ascontiguousarray(values)
    return hashlib.blake2b(data.view(np.uint8), digest_size=16).hexdigest()


def _index_key(index: pd.Index) -> tuple[Any, ...] | None:
    if isinstance(index, pd.RangeIndex):
        return ("range", index.start, index.stop, index.step, index.name)
    values = index.to_numpy()
    if values.dtype.kind not in "iufbMm":
        return None
    return ("index", str(index.dtype), len(values), _digest(values), index.name)


def _argument_key(value: Any) -> tuple[Any, ...] | None:
    if isinstance(value, pd.Series):
        values = value.to_numpy()
        if values.dtype.kind not in "iufb":
            return None
        index = _index_key(value.index)
        if index is None:
            return None
        try:
            hash(value.name)
        except TypeError:
            return None
        return (
            "series",
            str(values.dtype),
            len(values),
            _digest(values),
            index,
            value.name,
        )
    if value is None or isinstance(value, (bool, int, float, str)):
        return (type(value).__name__, value)
    return None


def _detached(value: Any) -> Any:
    """Return a result the caller may mutate without touching the cached copy."""
    if isinstance(value, (pd.Series, pd.DataFrame)):
        return value.copy(deep=False)  # copy-on-write: writes never reach the cache
    if isinstance(value, np.ndarray):
        return value.copy()
    if isinstance(value, tuple):
        return tuple(_detached(item) for item in value)
    return value


def _cached_indicator(fn: _F) -> _F:
    """Memoize ``fn`` inside an active :func:`indicator_cache` scope."""
    signature = inspect.signature(fn)

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        cache = _ACTIVE_CACHE.get()
        if cache is None:
            return fn(*args, **kwargs)
        bound = signature.bind(*args, **kwargs)
        bound.apply_defaults()
        parts: list[Any] = [fn.__qualname__]
        for name, value in bound.arguments.items():
            part = _argument_key(value)
            if part is None:
                return fn(*args, **kwargs)
            parts.append((name, part))
        key = tuple(parts)
        found, result = cache.get(key)
        if not found:
            result = fn(*args, **kwargs)
            cache.put(key, result)
        return _detached(result)

    return wrapper  # type: ignore[return-value]


def ema(series: pd.Series, length: int) -> pd.Series:
    return series.astype(float).ewm(span=length, adjust=False).mean()


def sma(series: pd.Series, length: int) -> pd.Series:
    return series.astype(float).rolling(length, min_periods=length).mean()


def rsi(close: pd.Series, length: int = 14) -> pd.Series:
    """Wilder-style RSI via ewm alpha=1/length (matches common TV ports closely)."""
    c = close.astype(float)
    delta = c.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / length, min_periods=length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / length, min_periods=length, adjust=False).mean()

    out = pd.Series(50.0, index=c.index)
    both_zero = (avg_gain == 0.0) & (avg_loss == 0.0)
    zero_loss = (avg_loss == 0.0) & (avg_gain > 0.0)
    zero_gain = (avg_gain == 0.0) & (avg_loss > 0.0)
    normal = (avg_loss > 0.0) & (avg_gain > 0.0)

    rs = avg_gain[normal] / avg_loss[normal]
    out.loc[normal] = 100.0 - (100.0 / (1.0 + rs))
    out.loc[zero_loss] = 100.0
    out.loc[zero_gain] = 0.0
    out.loc[both_zero] = 50.0
    return out


def bollinger_width(
    close: pd.Series, length: int = 20, n_std: float = 2.0
) -> pd.Series:
    mid = sma(close, length)
    std = close.astype(float).rolling(length, min_periods=length).std()
    upper = mid + n_std * std
    lower = mid - n_std * std
    width = (upper - lower) / mid.replace(0.0, np.nan)
    return width


@_cached_indicator
def percentile_rank(series: pd.Series, lookback: int) -> pd.Series:
    """Rolling percentile rank of the last value in [0, 100]."""
    s = series.astype(float).to_numpy().copy()
    n = len(s)
    out = np.full(n, np.nan, dtype=float)
    min_periods = max(lookback // 4, 5)
    if n < min_periods:
        return pd.Series(out, index=series.index)

    # Warm-up with variable windows
    for i in range(min_periods - 1, min(lookback - 1, n)):
        window = s[: i + 1]
        x = window[-1]
        if np.isnan(x):
            continue
        valid = window[~np.isnan(window)]
        if valid.size:
            out[i] = 100.0 * float(np.sum(valid <= x)) / float(valid.size)

    if n >= lookback:
        # Fixed-size windows via stride tricks, processed in row blocks so the
        # boolean temporaries stay O(block x lookback) rather than O(n x lookback).
        windows = np.lib.stride_tricks.sliding_window_view(s, lookback)
        for start in range(0, windows.shape[0], _WINDOW_CHUNK_ROWS):
            block = windows[start : start + _WINDOW_CHUNK_ROWS]
            last = block[:, -1]
            # count of non-nan and how many <= last (nan is non-comparable)
            valid = ~np.isnan(block)
            counts = valid.sum(axis=1).astype(float)
            le_counts = ((block <= last[:, None]) & valid).sum(axis=1).astype(float)
            ranks = np.where(counts > 0, 100.0 * le_counts / counts, np.nan)
            ranks = np.where(np.isnan(last), np.nan, ranks)
            first = lookback - 1 + start
            out[first : first + len(block)] = ranks

    return pd.Series(out, index=series.index)


def bbwp(
    close: pd.Series,
    *,
    bb_length: int = 20,
    lookback: int = 252,
    signal_sma: int = 5,
) -> tuple[pd.Series, pd.Series]:
    """Bollinger Band Width Percentile and its signal SMA."""
    width = bollinger_width(close, length=bb_length)
    pct = percentile_rank(width, lookback)
    sig = sma(pct, signal_sma)
    return pct, sig


def pmarp(
    close: pd.Series,
    *,
    ema_length: int = 21,
    lookback: int = 250,
) -> pd.Series:
    """Price / EMA ratio percentile — return extreme meter."""
    ratio = close.astype(float) / ema(close, ema_length).replace(0.0, np.nan)
    return percentile_rank(ratio, lookback)


def ema_bias(
    close: pd.Series,
    *,
    fast: int = 21,
    slow: int = 55,
) -> pd.Series:
    """EMA fast/slow bias on the chart timeframe (MVP: 1m bars).

    Returns 1=up, -1=down, 0=flat/unknown. Not a daily resample — lengths are
    bar counts on the series TF (e.g. 21/55 minutes on 1m).
    """
    c = close.astype(float)
    f = ema(c, fast)
    s = ema(c, slow)
    bias = pd.Series(0, index=c.index, dtype=int)
    bias = bias.mask(f > s, 1)
    bias = bias.mask(f < s, -1)
    return bias.fillna(0).astype(int)


def triple_ema(
    close: pd.Series, fast: int = 9, mid: int = 21, slow: int = 55
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Fast, mid and slow EMAs of one series (an EMA ribbon)."""
    return ema(close, fast), ema(close, mid), ema(close, slow)


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    h = high.astype(float)
    lows = low.astype(float)
    c = close.astype(float)
    prev_c = c.shift(1)
    tr = pd.concat([(h - lows), (h - prev_c).abs(), (lows - prev_c).abs()], axis=1).max(
        axis=1
    )
    return tr


@_cached_indicator
def atr(
    high: pd.Series, low: pd.Series, close: pd.Series, length: int = 10
) -> pd.Series:
    return (
        true_range(high, low, close)
        .ewm(alpha=1.0 / length, min_periods=length, adjust=False)
        .mean()
    )


@_cached_indicator
def supertrend(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    *,
    atr_period: int = 10,
    multiplier: float = 3.0,
) -> tuple[pd.Series, pd.Series]:
    """Classic Supertrend. Returns (line, direction) dir=1 up / -1 down."""
    h = high.astype(float).to_numpy()
    lows = low.astype(float).to_numpy()
    c = close.astype(float).to_numpy()
    n = len(c)
    tr = true_range(high, low, close).to_numpy()
    atr_arr = (
        pd.Series(tr)
        .ewm(alpha=1.0 / atr_period, min_periods=atr_period, adjust=False)
        .mean()
        .to_numpy()
    )
    hl2 = (h + lows) / 2.0
    # Plain Python floats in the loop: identical IEEE arithmetic without numpy
    # scalar boxing on every element access.
    upper = (hl2 + multiplier * atr_arr).tolist()
    lower = (hl2 - multiplier * atr_arr).tolist()
    atr_list = atr_arr.tolist()
    cl = c.tolist()
    isnan = math.isnan
    st = [math.nan] * n
    direction = [1] * n
    for i in range(1, n):
        if isnan(atr_list[i]):
            direction[i] = direction[i - 1]
            st[i] = st[i - 1]
            continue
        # band ratchets
        prev_lower = lower[i - 1]
        if not isnan(prev_lower) and cl[i - 1] > prev_lower:
            lower[i] = max(lower[i], prev_lower)
        prev_upper = upper[i - 1]
        if not isnan(prev_upper) and cl[i - 1] < prev_upper:
            upper[i] = min(upper[i], prev_upper)
        if direction[i - 1] == 1:
            direction[i] = -1 if cl[i] < lower[i] else 1
        else:
            direction[i] = 1 if cl[i] > upper[i] else -1
        st[i] = lower[i] if direction[i] == 1 else upper[i]
    return (
        pd.Series(np.asarray(st, dtype=float), index=close.index),
        pd.Series(np.asarray(direction, dtype=int), index=close.index, dtype=int),
    )


def zero_lag_ema(close: pd.Series, length: int = 70) -> pd.Series:
    """Zero-lag EMA (ZLEMA): EMA of the lag-compensated close."""
    lag = int((length - 1) // 2)
    c = close.astype(float)
    return ema(c + (c - c.shift(lag)), length)


def _sticky_band_trend(
    close: np.ndarray, upper: np.ndarray, lower: np.ndarray
) -> np.ndarray:
    """1 after a close above ``upper``, -1 after one below ``lower``; sticky otherwise."""
    trend = [0] * len(close)
    isnan = math.isnan
    t = 0
    for i, (cv, up, lo) in enumerate(
        zip(close.tolist(), upper.tolist(), lower.tolist())
    ):
        if isnan(up) or isnan(lo):
            trend[i] = t
            continue
        if cv > up:
            t = 1
        elif cv < lo:
            t = -1
        trend[i] = t
    return np.asarray(trend, dtype=int)


@_cached_indicator
def zero_lag_trend(
    close: pd.Series,
    *,
    length: int = 70,
    mult: float = 1.2,
    atr_period: int | None = None,
) -> tuple[pd.Series, pd.Series]:
    """Zero-lag basis + sticky trend dir (1/-1). Entry helper: pullback to zlema in trend."""
    c = close.astype(float)
    zlema = zero_lag_ema(c, length)
    ap = atr_period or length
    # The reference band is highest(atr, length*3)*mult.
    # we only have close here — approximate ATR from close range via rolling high-low if H/L not passed
    # Caller should prefer full OHLC version; use close-only TR proxy
    tr_proxy = c.diff().abs()
    atr_s = tr_proxy.ewm(alpha=1.0 / ap, min_periods=ap, adjust=False).mean()
    vol = atr_s.rolling(length * 3, min_periods=ap).max() * mult
    upper = zlema + vol
    lower = zlema - vol
    trend = _sticky_band_trend(c.to_numpy(), upper.to_numpy(), lower.to_numpy())
    return zlema, pd.Series(trend, index=close.index, dtype=int)


@_cached_indicator
def zero_lag_trend_ohlc(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    *,
    length: int = 70,
    mult: float = 1.2,
) -> tuple[pd.Series, pd.Series]:
    c = close.astype(float)
    zlema = zero_lag_ema(c, length)
    a = atr(high, low, close, length)
    vol = a.rolling(length * 3, min_periods=length).max() * mult
    upper = zlema + vol
    lower = zlema - vol
    trend = _sticky_band_trend(c.to_numpy(), upper.to_numpy(), lower.to_numpy())
    return zlema, pd.Series(trend, index=close.index, dtype=int)


@_cached_indicator
def choppiness_index(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    length: int = 14,
) -> pd.Series:
    """Choppiness Index (CIB). Low = trending."""
    h = high.astype(float)
    lows = low.astype(float)
    c = close.astype(float)
    tr = true_range(h, lows, c)
    tr_sum = tr.rolling(length, min_periods=length).sum()
    hh = (
        pd.concat([h, c.shift(1)], axis=1)
        .max(axis=1)
        .rolling(length, min_periods=length)
        .max()
    )
    ll = (
        pd.concat([lows, c.shift(1)], axis=1)
        .min(axis=1)
        .rolling(length, min_periods=length)
        .min()
    )
    rng = (hh - ll).replace(0.0, np.nan)
    cib = (np.log10(tr_sum / rng) / np.log10(float(length))) * 100.0
    return cib


@_cached_indicator
def squeeze_momentum(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    *,
    bb_length: int = 20,
    bb_mult: float = 2.0,
    kc_length: int = 20,
    kc_mult: float = 1.5,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """LazyBear squeeze: returns (mom_val, squeeze_on, squeeze_off)."""
    c = close.astype(float)
    h = high.astype(float)
    lows = low.astype(float)
    basis = sma(c, bb_length)
    dev = c.rolling(bb_length, min_periods=bb_length).std() * bb_mult
    upper_bb = basis + dev
    lower_bb = basis - dev
    ma = sma(c, kc_length)
    rangema = true_range(h, lows, c).rolling(kc_length, min_periods=kc_length).mean()
    upper_kc = ma + rangema * kc_mult
    lower_kc = ma - rangema * kc_mult
    sqz_on = (lower_bb > lower_kc) & (upper_bb < upper_kc)
    sqz_off = (lower_bb < lower_kc) & (upper_bb > upper_kc)
    # linreg of (close - midline of highest/lowest/sma)
    mid = (
        h.rolling(kc_length, min_periods=kc_length).max()
        + lows.rolling(kc_length, min_periods=kc_length).min()
    ) / 2.0
    mid = (mid + sma(c, kc_length)) / 2.0
    delta = c - mid
    mom = _rolling_linreg_last(delta, kc_length)
    return mom, sqz_on.fillna(False), sqz_off.fillna(False)


def _rolling_linreg_last(src: pd.Series, length: int) -> pd.Series:
    """``linreg(src, length, 0)``: least-squares fit value at each window's end.

    Vectorised over sliding windows with the same per-window arithmetic as the
    former ``rolling(length).apply`` implementation (centred x, centred y,
    ``slope * x[-1] + mean``), so results are bit-for-bit identical. Windows
    containing NaN give NaN; ``length == 1`` gives 0.0 (zero x-variance).
    """
    if length < 1:
        raise ValueError(f"linreg length must be >= 1, got {length}")
    values = src.to_numpy(dtype=float)
    out = np.full(len(values), np.nan)
    if len(values) < length:
        return pd.Series(out, index=src.index)
    x = np.arange(length, dtype=float)
    x = x - x.mean()
    denom = (x * x).sum()
    windows = np.lib.stride_tricks.sliding_window_view(values, length)
    for start in range(0, windows.shape[0], _WINDOW_CHUNK_ROWS):
        block = np.ascontiguousarray(windows[start : start + _WINDOW_CHUNK_ROWS])
        mean = block.mean(axis=1)
        if denom == 0:
            fitted = np.zeros(len(block))
        else:
            slope = (x * (block - mean[:, None])).sum(axis=1) / denom
            fitted = slope * x[-1] + mean
        fitted[np.isnan(block).any(axis=1)] = np.nan
        first = length - 1 + start
        out[first : first + len(block)] = fitted
    return pd.Series(out, index=src.index)


@_cached_indicator
def vortex(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    length: int = 14,
) -> tuple[pd.Series, pd.Series]:
    """Vortex indicator VI+ / VI-."""
    h = high.astype(float)
    lows = low.astype(float)
    c = close.astype(float)
    vmp = (h - lows.shift(1)).abs().rolling(length, min_periods=length).sum()
    vmm = (lows - h.shift(1)).abs().rolling(length, min_periods=length).sum()
    tr_sum = (
        true_range(h, lows, c)
        .rolling(length, min_periods=length)
        .sum()
        .replace(0.0, np.nan)
    )
    return vmp / tr_sum, vmm / tr_sum

"""Indicator building blocks for research strategies (pure pandas)."""

from __future__ import annotations

import numpy as np
import pandas as pd


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
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - (100.0 / (1.0 + rs))
    return out.fillna(50.0)


def bollinger_width(close: pd.Series, length: int = 20, n_std: float = 2.0) -> pd.Series:
    mid = sma(close, length)
    std = close.astype(float).rolling(length, min_periods=length).std()
    upper = mid + n_std * std
    lower = mid - n_std * std
    width = (upper - lower) / mid.replace(0.0, np.nan)
    return width


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
        # Fast path: fixed-size windows via stride tricks
        # Replace NaNs with sentinel so comparisons stay defined, then mask
        nan_mask = np.isnan(s)
        filled = np.where(nan_mask, np.nan, s)
        windows = np.lib.stride_tricks.sliding_window_view(filled, lookback)
        # windows shape (n - lookback + 1, lookback); last col is current value
        last = windows[:, -1]
        # count of non-nan and how many <= last (treating nan as non-comparable)
        valid = ~np.isnan(windows)
        # broadcast last; nan last → leave nan
        le = (windows <= last[:, None]) & valid
        counts = valid.sum(axis=1).astype(float)
        le_counts = le.sum(axis=1).astype(float)
        ranks = np.where(counts > 0, 100.0 * le_counts / counts, np.nan)
        ranks = np.where(np.isnan(last), np.nan, ranks)
        out[lookback - 1 :] = ranks

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


# Back-compat alias — older name implied daily; implementation is chart-TF.
def daily_ema_bias(
    df: pd.DataFrame,
    *,
    fast: int = 21,
    slow: int = 55,
) -> pd.Series:
    """Deprecated name: chart-TF EMA bias from df['close'] (not daily)."""
    return ema_bias(df["close"], fast=fast, slow=slow)


def crown_emas(close: pd.Series, fast: int = 9, mid: int = 21, slow: int = 55):
    return ema(close, fast), ema(close, mid), ema(close, slow)


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    h = high.astype(float)
    l = low.astype(float)
    c = close.astype(float)
    prev_c = c.shift(1)
    tr = pd.concat([(h - l), (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    return tr


def atr(
    high: pd.Series, low: pd.Series, close: pd.Series, length: int = 10
) -> pd.Series:
    return true_range(high, low, close).ewm(alpha=1.0 / length, min_periods=length, adjust=False).mean()


def supertrend(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    *,
    atr_period: int = 10,
    multiplier: float = 3.0,
) -> tuple[pd.Series, pd.Series]:
    """Classic Supertrend (supetrend.pine). Returns (line, direction) dir=1 up / -1 down."""
    h = high.astype(float).to_numpy()
    l = low.astype(float).to_numpy()
    c = close.astype(float).to_numpy()
    n = len(c)
    tr = true_range(high, low, close).to_numpy()
    atr_arr = pd.Series(tr).ewm(alpha=1.0 / atr_period, min_periods=atr_period, adjust=False).mean().to_numpy()
    hl2 = (h + l) / 2.0
    upper = hl2 + multiplier * atr_arr
    lower = hl2 - multiplier * atr_arr
    st = np.full(n, np.nan)
    direction = np.ones(n, dtype=int)
    for i in range(1, n):
        if np.isnan(atr_arr[i]):
            direction[i] = direction[i - 1]
            st[i] = st[i - 1]
            continue
        # band ratchets
        if c[i - 1] > lower[i - 1] if not np.isnan(lower[i - 1]) else False:
            lower[i] = max(lower[i], lower[i - 1]) if not np.isnan(lower[i - 1]) else lower[i]
        if c[i - 1] < upper[i - 1] if not np.isnan(upper[i - 1]) else False:
            upper[i] = min(upper[i], upper[i - 1]) if not np.isnan(upper[i - 1]) else upper[i]
        prev_dir = direction[i - 1]
        if prev_dir == 1:
            direction[i] = -1 if c[i] < lower[i] else 1
        else:
            direction[i] = 1 if c[i] > upper[i] else -1
        st[i] = lower[i] if direction[i] == 1 else upper[i]
    return (
        pd.Series(st, index=close.index),
        pd.Series(direction, index=close.index, dtype=int),
    )


def zero_lag_ema(close: pd.Series, length: int = 70) -> pd.Series:
    """ZLEMA from zero_lag_trend_signals.pine."""
    lag = int((length - 1) // 2)
    c = close.astype(float)
    return ema(c + (c - c.shift(lag)), length)


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
    # pine uses highest(atr, length*3)*mult as volatility band
    # we only have close here — approximate ATR from close range via rolling high-low if H/L not passed
    # Caller should prefer full OHLC version; use close-only TR proxy
    tr_proxy = c.diff().abs()
    atr_s = tr_proxy.ewm(alpha=1.0 / ap, min_periods=ap, adjust=False).mean()
    vol = atr_s.rolling(length * 3, min_periods=ap).max() * mult
    upper = zlema + vol
    lower = zlema - vol
    n = len(c)
    trend = np.zeros(n, dtype=int)
    cv = c.to_numpy()
    up = upper.to_numpy()
    lo = lower.to_numpy()
    t = 0
    for i in range(n):
        if np.isnan(up[i]) or np.isnan(lo[i]):
            trend[i] = t
            continue
        if cv[i] > up[i]:
            t = 1
        elif cv[i] < lo[i]:
            t = -1
        trend[i] = t
    return zlema, pd.Series(trend, index=close.index, dtype=int)


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
    n = len(c)
    trend = np.zeros(n, dtype=int)
    cv, up, lo = c.to_numpy(), upper.to_numpy(), lower.to_numpy()
    t = 0
    for i in range(n):
        if np.isnan(up[i]) or np.isnan(lo[i]):
            trend[i] = t
            continue
        if cv[i] > up[i]:
            t = 1
        elif cv[i] < lo[i]:
            t = -1
        trend[i] = t
    return zlema, pd.Series(trend, index=close.index, dtype=int)


def choppiness_index(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    length: int = 14,
) -> pd.Series:
    """Choppiness Index (CIB) from choppines_indicator.pine. Low = trending."""
    h = high.astype(float)
    l = low.astype(float)
    c = close.astype(float)
    tr = true_range(h, l, c)
    tr_sum = tr.rolling(length, min_periods=length).sum()
    hh = pd.concat([h, c.shift(1)], axis=1).max(axis=1).rolling(length, min_periods=length).max()
    ll = pd.concat([l, c.shift(1)], axis=1).min(axis=1).rolling(length, min_periods=length).min()
    rng = (hh - ll).replace(0.0, np.nan)
    cib = (np.log10(tr_sum / rng) / np.log10(float(length))) * 100.0
    return cib


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
    l = low.astype(float)
    basis = sma(c, bb_length)
    dev = c.rolling(bb_length, min_periods=bb_length).std() * bb_mult
    upper_bb = basis + dev
    lower_bb = basis - dev
    ma = sma(c, kc_length)
    rangema = true_range(h, l, c).rolling(kc_length, min_periods=kc_length).mean()
    upper_kc = ma + rangema * kc_mult
    lower_kc = ma - rangema * kc_mult
    sqz_on = (lower_bb > lower_kc) & (upper_bb < upper_kc)
    sqz_off = (lower_bb < lower_kc) & (upper_bb > upper_kc)
    # linreg of (close - midline of highest/lowest/sma)
    mid = (
        h.rolling(kc_length, min_periods=kc_length).max()
        + l.rolling(kc_length, min_periods=kc_length).min()
    ) / 2.0
    mid = (mid + sma(c, kc_length)) / 2.0
    delta = c - mid
    # rolling linear regression slope*x approx: use rolling cov with index
    # Pine linreg(src, length, 0) = fit value at end of window
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
        # value at last bar of demeaned fit + mean
        return float(slope * x[-1] + window.mean())

    # faster: use simple momentum proxy = close - mid (LazyBear hist is linreg)
    # full linreg for fidelity on shorter windows
    mom = delta.rolling(kc_length, min_periods=kc_length).apply(_linreg_last, raw=True)
    return mom, sqz_on.fillna(False), sqz_off.fillna(False)


def vortex(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    length: int = 14,
) -> tuple[pd.Series, pd.Series]:
    """Vortex VI+ / VI- from vortex.pine."""
    h = high.astype(float)
    l = low.astype(float)
    c = close.astype(float)
    vmp = (h - l.shift(1)).abs().rolling(length, min_periods=length).sum()
    vmm = (l - h.shift(1)).abs().rolling(length, min_periods=length).sum()
    tr_sum = true_range(h, l, c).rolling(length, min_periods=length).sum().replace(0.0, np.nan)
    return vmp / tr_sum, vmm / tr_sum

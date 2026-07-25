"""Real-telemetry regime snapshot exporter for the tui-regime-detector cockpit.

Computes per-bar telemetry (RSI, BBWP percentile, MTF zero-lag trends, OPI,
spread, depth ratio, funding z-score, ultimate regime states, policy weights
and dynamic leverage) from cached market data and writes the JSON array the
Rust TUI loads from ``data/exports/regime_snapshots.json``.

Read-only research telemetry (SRS_HV1_REGIME): no execution clients, no
secrets, no venue calls.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from hypervector.regime.ultimate import detect_ultimate_regime
from hypervector.strategies.indicators import bbwp, rsi, zero_lag_trend_ohlc

_TREND_LABELS = {1: "BULL", -1: "BEAR", 0: "NEUTRAL"}

_STATE_DEFAULT_OPI = 0.0
_DEFAULT_SPREAD_BPS = 2.0
_DEFAULT_DEPTH_RATIO = 1.0


def _ensure_datetime_index(df: pd.DataFrame) -> pd.DataFrame:
    out = df
    if not isinstance(df.index, pd.DatetimeIndex):
        if "timestamp" not in df.columns:
            return df
        out = df.copy()
        out.index = pd.DatetimeIndex(pd.to_datetime(out["timestamp"], utc=True))
    if not out.index.is_monotonic_increasing or out.index.has_duplicates:
        out = out[~out.index.duplicated(keep="last")].sort_index()
    return out


def _resampled_trend(df: pd.DataFrame, rule: str, index: pd.Index) -> pd.Series:
    """Zero-lag trend on a resampled timeframe, shifted 1 bar (no lookahead)."""
    if not isinstance(df.index, pd.DatetimeIndex):
        return pd.Series(0, index=index, dtype=int)
    agg = df.resample(rule, label="right", closed="right").agg(
        {"high": "max", "low": "min", "close": "last"}
    ).dropna()
    if len(agg) < 3:
        return pd.Series(0, index=index, dtype=int)
    _, trend = zero_lag_trend_ohlc(
        agg["high"], agg["low"], agg["close"], length=min(70, max(len(agg) // 2, 3))
    )
    return trend.shift(1).reindex(index, method="ffill").fillna(0).astype(int)


def _merge_book_features(df: pd.DataFrame, data_root: Path, symbol: str, timeframe: str) -> pd.DataFrame:
    """Merge aligned L2 book features (spread/OBI/depth) when available."""
    candidate = data_root / "cache" / "aligned" / f"{symbol}_{timeframe}_aligned_book.parquet"
    if not candidate.is_file():
        return df
    try:
        book = pd.read_parquet(candidate)
    except Exception:
        return df
    if "timestamp" not in book.columns:
        return df
    book = _ensure_datetime_index(book)
    if not isinstance(book.index, pd.DatetimeIndex):
        return df
    cols = [c for c in ("spread_bps", "obi_5", "book_depth_ratio", "book_pressure") if c in book.columns]
    if not cols:
        return df
    out = df.copy()
    joined = book[cols].reindex(out.index, method="ffill")
    for c in cols:
        if c not in out.columns:
            out[c] = joined[c]
    return out


def build_regime_snapshots(
    df: pd.DataFrame,
    *,
    symbol: str = "BTC",
    timeframe: str = "1m",
    data_root: Path | str = "data",
    max_bars: int = 1500,
) -> list[dict[str, Any]]:
    """Compute real per-bar telemetry snapshots for the TUI cockpit."""
    root = Path(data_root)
    df = _ensure_datetime_index(df)
    df = _merge_book_features(df, root, symbol, timeframe)

    close = df["close"].astype(float)
    high = df["high"].astype(float) if "high" in df.columns else close
    low = df["low"].astype(float) if "low" in df.columns else close
    volume = df["volume"].astype(float) if "volume" in df.columns else pd.Series(0.0, index=df.index)

    regime = detect_ultimate_regime(df)

    rsi_s = rsi(close, 14)
    bb_pct, _ = bbwp(close, bb_length=20, lookback=180)
    _, t_1m = zero_lag_trend_ohlc(high, low, close, length=70, mult=1.2)
    t_5m = _resampled_trend(df, "5min", close.index)
    t_15m = _resampled_trend(df, "15min", close.index)

    if "order_pressure_index" in df.columns:
        opi = df["order_pressure_index"].astype(float)
    elif "obi_5" in df.columns:
        opi = df["obi_5"].astype(float)
    elif "book_pressure" in df.columns:
        opi = df["book_pressure"].astype(float)
    else:
        opi = pd.Series(_STATE_DEFAULT_OPI, index=close.index)

    spread = (
        df["spread_bps"].astype(float)
        if "spread_bps" in df.columns
        else pd.Series(_DEFAULT_SPREAD_BPS, index=close.index)
    )
    depth_ratio = (
        df["book_depth_ratio"].astype(float)
        if "book_depth_ratio" in df.columns
        else pd.Series(_DEFAULT_DEPTH_RATIO, index=close.index)
    )

    if "funding_rate" in df.columns and (df["funding_rate"].astype(float) != 0.0).any():
        fr = df["funding_rate"].astype(float)
        fr_mean = fr.rolling(48, min_periods=10).mean()
        fr_std = fr.rolling(48, min_periods=10).std().replace(0.0, np.nan).fillna(1e-6)
        funding_z = ((fr - fr_mean) / fr_std).fillna(0.0)
    else:
        funding_z = pd.Series(0.0, index=close.index)

    # Deterministic conviction heuristic from real inputs: MTF alignment,
    # orderbook flow magnitude, and policy leverage utilisation.
    align_frac = (
        (t_1m == t_5m).astype(float) + (t_5m == t_15m).astype(float) + (t_1m == t_15m).astype(float)
    ) / 3.0
    lev_util = (regime["dynamic_leverage"] / regime["max_leverage"].replace(0.0, np.nan)).fillna(0.5)
    confidence = (
        0.35
        + 0.25 * align_frac
        + 0.25 * opi.abs().clip(upper=1.0)
        + 0.15 * lev_util.clip(0.0, 1.0)
    ).clip(0.0, 1.0)

    n = len(df)
    start = max(0, n - int(max_bars))
    idx = df.index[start:]

    if isinstance(idx, pd.DatetimeIndex):
        ts_ms = (idx.as_unit("ns").asi8 // 1_000_000).astype("int64")
        ts_str = idx.strftime("%Y-%m-%d %H:%M:%S UTC")
    else:
        ts_ms = pd.Index(np.arange(start, n, dtype="int64") * 60_000)
        ts_str = pd.Index([f"bar {i}" for i in range(start, n)])

    snapshots: list[dict[str, Any]] = []
    for pos, i in enumerate(range(start, n)):
        snapshots.append(
            {
                "timestamp_str": str(ts_str[pos]),
                "timestamp_ms": int(ts_ms[pos]),
                "close": round(float(close.iloc[i]), 2),
                "high": round(float(high.iloc[i]), 2),
                "low": round(float(low.iloc[i]), 2),
                "volume": round(float(volume.iloc[i]), 5),
                "regime_state": str(regime["regime_state"].iloc[i]),
                "confidence": round(float(confidence.iloc[i]), 3),
                "opi": round(float(opi.iloc[i]), 4),
                "spread_bps": round(float(spread.iloc[i]), 3),
                "bid_depth_ratio": round(float(depth_ratio.iloc[i]), 3),
                "bbwp_percentile": round(float(bb_pct.iloc[i]), 2) if not np.isnan(bb_pct.iloc[i]) else 50.0,
                "rsi": round(float(rsi_s.iloc[i]), 2) if not np.isnan(rsi_s.iloc[i]) else 50.0,
                "funding_zscore": round(float(funding_z.iloc[i]), 3),
                "trend_1m": _TREND_LABELS.get(int(t_1m.iloc[i]), "NEUTRAL"),
                "trend_5m": _TREND_LABELS.get(int(t_5m.iloc[i]), "NEUTRAL"),
                "trend_15m": _TREND_LABELS.get(int(t_15m.iloc[i]), "NEUTRAL"),
                "long_weight": round(float(regime["long_weight"].iloc[i]), 2),
                "short_weight": round(float(regime["short_weight"].iloc[i]), 2),
                "max_leverage": round(float(regime["max_leverage"].iloc[i]), 2),
                "dynamic_leverage": round(float(regime["dynamic_leverage"].iloc[i]), 2),
                "taker_allowed": False,
            }
        )
    return snapshots


def export_regime_snapshots(
    df: pd.DataFrame,
    out_path: Path | str,
    *,
    symbol: str = "BTC",
    timeframe: str = "1m",
    data_root: Path | str = "data",
    max_bars: int = 1500,
) -> dict[str, Any]:
    """Write TUI snapshot JSON and return a summary dict."""
    snaps = build_regime_snapshots(
        df, symbol=symbol, timeframe=timeframe, data_root=data_root, max_bars=max_bars
    )
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snaps), encoding="utf-8")

    states = pd.Series([s["regime_state"] for s in snaps])
    return {
        "ok": True,
        "out": str(out),
        "snapshots": len(snaps),
        "symbol": symbol,
        "timeframe": timeframe,
        "first_timestamp": snaps[0]["timestamp_str"] if snaps else None,
        "last_timestamp": snaps[-1]["timestamp_str"] if snaps else None,
        "state_distribution": states.value_counts().to_dict() if snaps else {},
    }

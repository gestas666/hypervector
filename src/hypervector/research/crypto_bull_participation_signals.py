"""Completed-hour state construction for crypto bull participation."""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd

from hypervector.research.crypto_bull_participation_models import (
    CryptoBullParticipationConfig,
)

_OHLC = ("open", "high", "low", "close")


def build_crypto_bull_decisions(
    hourly_by_symbol: Mapping[str, pd.DataFrame],
    config: CryptoBullParticipationConfig | None = None,
) -> dict[str, pd.DataFrame]:
    """Build next-boundary decisions from synchronized completed hourly bars."""
    cfg = config or CryptoBullParticipationConfig()
    frames = _validated_hourly_frames(hourly_by_symbol, cfg)
    aligned = {
        symbol: _individual_alignment(frame, cfg) for symbol, frame in frames.items()
    }
    breadth = pd.concat(aligned, axis=1).sum(axis=1).astype(int)
    decisions = {
        symbol: _decision_frame(frames[symbol], state, breadth, cfg)
        for symbol, state in aligned.items()
    }
    return decisions


def _validated_hourly_frames(
    values: Mapping[str, pd.DataFrame], config: CryptoBullParticipationConfig
) -> dict[str, pd.DataFrame]:
    if set(values) != set(config.symbols):
        raise ValueError("hourly source symbols differ from the frozen universe")
    frames = {symbol: values[symbol].copy() for symbol in config.symbols}
    expected: pd.DatetimeIndex | None = None
    for symbol, frame in frames.items():
        _validate_frame(frame, symbol)
        if expected is None:
            expected = frame.index
        elif not frame.index.equals(expected):
            raise ValueError("crypto sources require aligned hourly indexes")
    return frames


def _validate_frame(frame: pd.DataFrame, symbol: str) -> None:
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
        raise ValueError(f"{symbol} hourly index must be timezone-aware")
    if frame.empty or not frame.index.is_monotonic_increasing:
        raise ValueError(f"{symbol} hourly frame must be ordered and non-empty")
    if frame.index.has_duplicates:
        raise ValueError(f"{symbol} hourly frame contains duplicate timestamps")
    missing = sorted(set(_OHLC).difference(frame.columns))
    if missing:
        raise ValueError(f"{symbol} hourly frame missing columns: {missing}")
    numeric = frame.loc[:, _OHLC].apply(pd.to_numeric, errors="raise")
    if not np.isfinite(numeric.to_numpy()).all() or (numeric <= 0.0).any().any():
        raise ValueError(f"{symbol} hourly OHLC must be finite and positive")


def _individual_alignment(
    frame: pd.DataFrame, config: CryptoBullParticipationConfig
) -> pd.Series:
    close = frame["close"].astype(float)
    fast = close.ewm(
        span=config.fast_ema_hours,
        adjust=False,
        min_periods=config.minimum_ema_hours,
    ).mean()
    slow = close.ewm(
        span=config.slow_ema_hours,
        adjust=False,
        min_periods=config.minimum_ema_hours,
    ).mean()
    return (close > fast) & (fast > slow)


def _decision_frame(
    frame: pd.DataFrame,
    aligned: pd.Series,
    breadth: pd.Series,
    config: CryptoBullParticipationConfig,
) -> pd.DataFrame:
    close = frame["close"].astype(float)
    fast = close.ewm(
        span=config.fast_ema_hours,
        adjust=False,
        min_periods=config.minimum_ema_hours,
    ).mean()
    slow = close.ewm(
        span=config.slow_ema_hours,
        adjust=False,
        min_periods=config.minimum_ema_hours,
    ).mean()
    eligible = aligned & breadth.ge(config.entry_breadth)
    onset = eligible & ~eligible.shift(1, fill_value=False)
    exit_signal = close.lt(fast) | breadth.lt(config.exit_breadth)
    output = pd.DataFrame(
        {
            "completed_hour_close": close,
            "completed_hour_high": frame["high"].astype(float),
            "ema_fast": fast,
            "ema_slow": slow,
            "breadth": breadth,
            "individual_alignment": aligned,
            "entry_eligible": eligible,
            "entry_onset": onset,
            "exit_signal": exit_signal,
        }
    )
    output.index = output.index + pd.Timedelta(hours=1)
    return output

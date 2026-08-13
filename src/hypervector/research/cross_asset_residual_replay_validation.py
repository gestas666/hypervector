"""Fail-closed input validation for cross-asset residual replay."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from hypervector.research.cross_asset_residual_models import ResidualSignal

_MINUTE_COLUMNS = {"timestamp", "open", "high", "low", "close", "funding_rate"}
_STATE_COLUMNS = {"decision_time_utc", "zscore"}
_SUPPORTED_SYMBOLS = {"BTC", "ETH", "SOL", "HYPE"}


def validated_minute_bars(
    frames: dict[str, pd.DataFrame],
) -> tuple[tuple[str, str], dict[str, pd.DataFrame]]:
    """Return two aligned minute frames or reject incomplete evidence."""
    if len(frames) != 2:
        raise ValueError("residual replay requires exactly two asset frames")
    pair = tuple(frames)
    if pair[0] == pair[1] or any(symbol not in _SUPPORTED_SYMBOLS for symbol in pair):
        raise ValueError("residual replay pair identity is invalid")
    indexed = {
        symbol: _validated_asset_bars(frame, symbol) for symbol, frame in frames.items()
    }
    if not indexed[pair[0]].index.equals(indexed[pair[1]].index):
        raise ValueError("residual replay asset minutes must align exactly")
    return (pair[0], pair[1]), indexed


def validated_states(
    states: pd.DataFrame,
    minute_index: pd.DatetimeIndex,
) -> dict[pd.Timestamp, float]:
    """Index unique finite residual states by executable minute."""
    missing = sorted(_STATE_COLUMNS.difference(states.columns))
    if missing:
        raise ValueError(f"residual replay states missing columns: {missing}")
    result: dict[pd.Timestamp, float] = {}
    for _, row in states.iterrows():
        timestamp = pd.Timestamp(row["decision_time_utc"])
        if timestamp.tz is None or timestamp not in minute_index:
            raise ValueError("residual state decision time is unavailable")
        zscore = float(row["zscore"])
        if timestamp in result or not math.isfinite(zscore):
            raise ValueError("residual state decisions must be unique and finite")
        result[timestamp] = zscore
    return result


def validated_signals(
    signals: tuple[ResidualSignal, ...],
    pair: tuple[str, str],
    minute_index: pd.DatetimeIndex,
) -> dict[pd.Timestamp, tuple[ResidualSignal, ...]]:
    """Return causal report-only signals grouped by entry minute."""
    scheduled: dict[pd.Timestamp, list[ResidualSignal]] = {}
    for signal in signals:
        timestamp = pd.Timestamp(signal.decision_time_utc)
        _validate_signal(signal, pair, timestamp, minute_index)
        scheduled.setdefault(timestamp, []).append(signal)
    return {timestamp: tuple(values) for timestamp, values in scheduled.items()}


def _validated_asset_bars(frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
    missing = sorted(_MINUTE_COLUMNS.difference(frame.columns))
    if missing:
        raise ValueError(f"{symbol} residual minute bars missing columns: {missing}")
    times = pd.DatetimeIndex(frame["timestamp"])
    if frame.empty or times.tz is None or times.has_duplicates:
        raise ValueError(f"{symbol} residual minutes require unique aware timestamps")
    if not times.is_monotonic_increasing:
        raise ValueError(f"{symbol} residual minutes must be ordered")
    if len(times) > 1 and not (times[1:] - times[:-1] == pd.Timedelta(minutes=1)).all():
        raise ValueError(f"{symbol} residual minutes must be complete")
    numeric = frame[["open", "high", "low", "close", "funding_rate"]].to_numpy(float)
    if not np.isfinite(numeric).all() or (numeric[:, :4] <= 0.0).any():
        raise ValueError(f"{symbol} residual minute values are invalid")
    return frame.set_index("timestamp").copy()


def _validate_signal(
    signal: ResidualSignal,
    pair: tuple[str, str],
    timestamp: pd.Timestamp,
    minute_index: pd.DatetimeIndex,
) -> None:
    if (signal.left_symbol, signal.right_symbol) != pair:
        raise ValueError("residual signal pair does not match replay frames")
    if signal.execution_authority != "none" or timestamp.tz is None:
        raise ValueError("residual research signal authority or time is invalid")
    if timestamp not in minute_index:
        raise ValueError("residual signal entry minute is unavailable")
    if signal.direction not in {"long_spread", "short_spread"}:
        raise ValueError("residual signal direction is invalid")
    if not math.isfinite(signal.hedge_ratio) or signal.hedge_ratio == 0.0:
        raise ValueError("residual signal hedge ratio must be finite and nonzero")

"""Validation and causal signal scheduling for Market Cipher replay."""

from __future__ import annotations

import math

import pandas as pd

from hypervector.research.market_cipher_replay_models import (
    MarketCipherReplayConfig,
    ReplayRejection,
)
from hypervector.research.market_cipher_replay_state import ReplayCandidate
from hypervector.research.shared_portfolio_models import Direction

_BAR_COLUMNS = {"open", "high", "low", "close", "funding_rate", "wave_cross"}
_SIGNAL_COLUMNS = {
    "signal_time_utc",
    "symbol",
    "candidate",
    "side",
    "stop_anchor",
    "eligible",
}


def validate_replay_bars(bars_by_symbol: dict[str, pd.DataFrame]) -> None:
    """Reject incomplete, non-causal, or invalid OHLC inputs."""
    if not bars_by_symbol:
        raise ValueError("Market Cipher replay requires at least one symbol")
    for symbol, bars in bars_by_symbol.items():
        missing = sorted(_BAR_COLUMNS.difference(bars.columns))
        valid_index = isinstance(bars.index, pd.DatetimeIndex) and bars.index.tz
        if not symbol.strip() or bars.empty or missing or not valid_index:
            raise ValueError(
                f"invalid bars for {symbol}: missing={missing} timezone={bool(valid_index)}"
            )
        if not bars.index.is_monotonic_increasing or not bars.index.is_unique:
            raise ValueError(f"bars for {symbol} require sorted unique timestamps")
        prices = bars[["open", "high", "low", "close"]].to_numpy(dtype=float)
        if not math.isfinite(float(prices.sum())) or (prices <= 0.0).any():
            raise ValueError(f"bars for {symbol} contain invalid prices")


def prepare_replay_candidates(
    bars_by_symbol: dict[str, pd.DataFrame],
    signals: pd.DataFrame,
    config: MarketCipherReplayConfig,
) -> tuple[dict[pd.Timestamp, list[ReplayCandidate]], list[ReplayRejection]]:
    """Schedule valid decisions on the next available bar for their symbol."""
    missing = sorted(_SIGNAL_COLUMNS.difference(signals.columns))
    if missing:
        raise ValueError(f"Market Cipher signals missing columns: {missing}")
    scheduled: dict[pd.Timestamp, list[ReplayCandidate]] = {}
    rejected: list[ReplayRejection] = []
    for _, row in signals.iterrows():
        candidate, rejection = _candidate_from_row(bars_by_symbol, row, config)
        if rejection is not None:
            rejected.append(rejection)
        elif candidate is not None:
            scheduled.setdefault(candidate.entry_time, []).append(candidate)
    return scheduled, rejected


def replay_event_times(
    bars_by_symbol: dict[str, pd.DataFrame],
) -> list[pd.Timestamp]:
    """Return the sorted union of all symbol bar timestamps."""
    values = {timestamp for bars in bars_by_symbol.values() for timestamp in bars.index}
    return sorted(values)


def replay_bars_at_time(
    bars_by_symbol: dict[str, pd.DataFrame], timestamp: pd.Timestamp
) -> dict[str, pd.Series]:
    """Return symbol rows present at one global portfolio timestamp."""
    return {
        symbol: bars.loc[timestamp]
        for symbol, bars in bars_by_symbol.items()
        if timestamp in bars.index
    }


def _candidate_from_row(
    bars_by_symbol: dict[str, pd.DataFrame],
    row: pd.Series,
    config: MarketCipherReplayConfig,
) -> tuple[ReplayCandidate | None, ReplayRejection | None]:
    timestamp = pd.Timestamp(row["signal_time_utc"])
    if timestamp.tz is None:
        raise ValueError("signal_time_utc must be timezone-aware")
    symbol = str(row["symbol"])
    name = str(row["candidate"])
    reason = _candidate_data_reason(
        bars_by_symbol, row, symbol, timestamp, config.entry_delay_bars
    )
    if reason is not None:
        return None, ReplayRejection(timestamp.isoformat(), symbol, name, reason)
    entry_override, override_error = _entry_price_override(row)
    if override_error is not None:
        return None, ReplayRejection(
            timestamp.isoformat(), symbol, name, override_error
        )
    bars = bars_by_symbol[symbol]
    location = int(bars.index.get_loc(timestamp))
    entry_location = location + config.entry_delay_bars
    side = str(row["side"])
    direction: Direction = "long" if side == "long" else "short"
    score_value = row.get("score", row.get("quality_score", 0.0))
    return ReplayCandidate(
        timestamp,
        bars.index[entry_location],
        float(bars.iloc[entry_location]["open"]),
        symbol,
        name,
        direction,
        float(score_value),
        float(row["stop_anchor"]),
        float(row.get("risk_multiplier", 1.0)),
        entry_override,
    ), None


def _entry_price_override(row: pd.Series) -> tuple[float | None, str | None]:
    raw = row.get("entry_price_override")
    if raw is None or pd.isna(raw):
        return None, None
    if isinstance(raw, bool):
        return None, "invalid_entry_price_override"
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None, "invalid_entry_price_override"
    if not math.isfinite(value) or value <= 0.0:
        return None, "invalid_entry_price_override"
    return value, None


def _candidate_data_reason(
    bars_by_symbol: dict[str, pd.DataFrame],
    row: pd.Series,
    symbol: str,
    timestamp: pd.Timestamp,
    entry_delay_bars: int,
) -> str | None:
    if not bool(row["eligible"]):
        return "signal_ineligible"
    if str(row["side"]) not in {"long", "short"}:
        raise ValueError("signal side must be long or short")
    if symbol not in bars_by_symbol or timestamp not in bars_by_symbol[symbol].index:
        return "signal_bar_unavailable"
    location = int(bars_by_symbol[symbol].index.get_loc(timestamp))
    if location + entry_delay_bars >= len(bars_by_symbol[symbol]):
        return "no_next_bar"
    anchor = float(row["stop_anchor"])
    if not math.isfinite(anchor) or anchor <= 0.0:
        return "invalid_stop_anchor"
    multiplier = float(row.get("risk_multiplier", 1.0))
    if not math.isfinite(multiplier) or multiplier <= 0.0:
        return "invalid_risk_multiplier"
    return None

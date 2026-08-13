"""Causal signal-time features for HYPE breakout entry attribution."""

from __future__ import annotations

from dataclasses import asdict
import math

import pandas as pd

from hypervector.research.hype_breakout_exit_models import HypeExitTrade

_REQUIRED_COLUMNS = frozenset(
    {
        "open",
        "high",
        "low",
        "close",
        "volume",
        "entry_side",
        "state_1m",
        "context_15m",
        "sma_gap_bps",
        "regime_strength_score",
        "bbwp_percentile",
        "ema_gap_bps_signed",
        "rsi",
        "breakout_volume_ratio",
        "regime_5m_strength_percentile",
        "regime_5m_bbwp_percentile",
        "regime_5m_ema_gap_bps",
        "regime_5m_breakout_volume_ratio",
    }
)
HYPE_ENTRY_ATTRIBUTION_FEATURES = (
    "sma_gap_directional_bps",
    "regime_strength",
    "current_bbwp_percentile",
    "prior_bbwp_min_15m",
    "prior_bbwp_below25_count_15m",
    "ema_gap_directional_bps",
    "rsi_directional_distance",
    "breakout_volume_ratio",
    "directional_return_5m_bps",
    "directional_return_15m_bps",
    "directional_return_60m_bps",
    "volume_ratio_20m",
    "bar_range_bps",
    "directional_bar_body_bps",
    "breakout_clearance_20m_bps",
    "state_1m_alignment",
    "context_15m_alignment",
    "authoritative_5m_strength_percentile",
    "authoritative_5m_bbwp_percentile",
    "authoritative_5m_ema_gap_directional_bps",
    "authoritative_5m_breakout_volume_ratio",
)


def build_hype_entry_features(market: pd.DataFrame) -> pd.DataFrame:
    """Build point-in-time features for every raw HYPE breakout onset."""
    _validate_market(market)
    side = _side_sign(market["entry_side"])
    prices = market[["open", "high", "low", "close"]].astype(float)
    features = _base_features(market, prices)
    _attach_directional_features(features, market, prices, side)
    _attach_context_alignment(features, market, side)
    signals = side.notna()
    output = features.loc[signals].copy()
    output.insert(0, "entry_side", market.loc[signals, "entry_side"].astype(str))
    _validate_signal_features(output)
    return output


def join_hype_entry_outcomes(
    features: pd.DataFrame,
    trades: tuple[HypeExitTrade, ...],
) -> pd.DataFrame:
    """Join exact control-admitted trade outcomes to signal-time features."""
    if not trades:
        raise ValueError("HYPE entry attribution requires at least one trade")
    timestamps = pd.DatetimeIndex(
        [pd.Timestamp(trade.signal_time_utc) for trade in trades]
    )
    if timestamps.has_duplicates:
        raise ValueError("HYPE attribution trade signal timestamps must be unique")
    missing = timestamps.difference(features.index)
    if not missing.empty:
        raise ValueError("HYPE trade signal timestamp is missing feature evidence")
    selected = features.loc[timestamps].copy()
    _validate_trade_sides(selected, trades)
    outcomes = pd.DataFrame([asdict(trade) for trade in trades], index=timestamps)
    return pd.concat([selected, outcomes], axis=1)


def _base_features(
    market: pd.DataFrame,
    prices: pd.DataFrame,
) -> pd.DataFrame:
    close = prices["close"]
    bbwp = market["bbwp_percentile"].astype(float)
    prior_bbwp = bbwp.shift(1)
    below_25 = prior_bbwp.lt(25.0).where(prior_bbwp.notna()).astype(float)
    output = pd.DataFrame(index=market.index)
    output["regime_strength"] = market["regime_strength_score"].astype(float)
    output["current_bbwp_percentile"] = bbwp
    for minutes in (15, 30, 60):
        prior = prior_bbwp.rolling(minutes, min_periods=minutes)
        output[f"prior_bbwp_min_{minutes}m"] = prior.min()
        output[f"prior_bbwp_below25_count_{minutes}m"] = below_25.rolling(
            minutes,
            min_periods=minutes,
        ).sum()
    output["breakout_volume_ratio"] = market["breakout_volume_ratio"].astype(float)
    output["authoritative_5m_strength_percentile"] = market[
        "regime_5m_strength_percentile"
    ].astype(float)
    output["authoritative_5m_bbwp_percentile"] = market[
        "regime_5m_bbwp_percentile"
    ].astype(float)
    output["authoritative_5m_breakout_volume_ratio"] = market[
        "regime_5m_breakout_volume_ratio"
    ].astype(float)
    prior_volume = market["volume"].astype(float).shift(1).rolling(20).mean()
    output["volume_ratio_20m"] = market["volume"].astype(float) / prior_volume
    output["bar_range_bps"] = (prices["high"] - prices["low"]) / close * 10_000.0
    return output


def _attach_directional_features(
    output: pd.DataFrame,
    market: pd.DataFrame,
    prices: pd.DataFrame,
    side: pd.Series,
) -> None:
    close = prices["close"]
    output["sma_gap_directional_bps"] = market["sma_gap_bps"].astype(float) * side
    output["ema_gap_directional_bps"] = (
        market["ema_gap_bps_signed"].astype(float) * side
    )
    output["authoritative_5m_ema_gap_directional_bps"] = (
        market["regime_5m_ema_gap_bps"].astype(float) * side
    )
    output["rsi_directional_distance"] = (market["rsi"].astype(float) - 50.0) * side
    output["directional_bar_body_bps"] = (
        (close / prices["open"] - 1.0) * 10_000.0 * side
    )
    for minutes in (5, 15, 60):
        output[f"directional_return_{minutes}m_bps"] = (
            (close / close.shift(minutes) - 1.0) * 10_000.0 * side
        )
    prior_high = prices["high"].shift(1).rolling(20).max()
    prior_low = prices["low"].shift(1).rolling(20).min()
    long_clearance = (close / prior_high - 1.0) * 10_000.0
    short_clearance = (prior_low / close - 1.0) * 10_000.0
    output["breakout_clearance_20m_bps"] = long_clearance.where(
        side > 0.0, short_clearance
    )


def _attach_context_alignment(
    output: pd.DataFrame,
    market: pd.DataFrame,
    side: pd.Series,
) -> None:
    state_1m = market["state_1m"].astype(str)
    context_15m = market["context_15m"].astype(str)
    output["state_1m_alignment"] = _trend_alignment(state_1m, side)
    output["context_15m_alignment"] = _trend_alignment(context_15m, side)


def _trend_alignment(states: pd.Series, side: pd.Series) -> pd.Series:
    long_alignment = side.gt(0.0) & states.eq("TREND_UP")
    short_alignment = side.lt(0.0) & states.eq("TREND_DOWN")
    return (long_alignment | short_alignment).astype(float)


def _side_sign(values: pd.Series) -> pd.Series:
    output = pd.Series(float("nan"), index=values.index, dtype=float)
    output.loc[values.eq("long")] = 1.0
    output.loc[values.eq("short")] = -1.0
    invalid = values.notna() & ~values.isin(("long", "short"))
    if invalid.any():
        raise ValueError("HYPE feature entry_side must be long, short, or empty")
    return output


def _validate_trade_sides(
    selected: pd.DataFrame,
    trades: tuple[HypeExitTrade, ...],
) -> None:
    for position, trade in enumerate(trades):
        if selected["entry_side"].iloc[position] != trade.side:
            raise ValueError("HYPE trade side does not match feature source side")


def _validate_market(market: pd.DataFrame) -> None:
    missing = sorted(_REQUIRED_COLUMNS.difference(market.columns))
    if missing:
        raise ValueError(f"HYPE entry feature market missing columns: {missing}")
    if not isinstance(market.index, pd.DatetimeIndex) or market.index.tz is None:
        raise ValueError("HYPE entry features require a timezone-aware DatetimeIndex")
    if market.index.has_duplicates or not market.index.is_monotonic_increasing:
        raise ValueError("HYPE entry feature index must be ordered and unique")
    market_values = market[["open", "high", "low", "close", "volume"]].astype(float)
    if not market_values.map(math.isfinite).to_numpy().all():
        raise ValueError("HYPE entry feature prices and volume must be finite")


def _validate_signal_features(features: pd.DataFrame) -> None:
    if features.empty:
        raise ValueError("HYPE entry attribution requires at least one raw signal")
    values = features[list(HYPE_ENTRY_ATTRIBUTION_FEATURES)].astype(float)
    if not values.map(math.isfinite).to_numpy().all():
        raise ValueError("HYPE entry feature values must be finite at every signal")

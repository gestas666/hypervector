"""Shared frozen 60/60/24h BTC research replay helpers."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from hypervector.research.shared_portfolio_models import SharedPortfolioConfig


def validated_btc_replay_slippage(value: float, label: str) -> float:
    """Return finite nonnegative taker slippage for a report-only replay."""
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0.0:
        raise ValueError(f"{label} slippage must be finite and non-negative")
    return numeric


def validated_btc_entry_window(
    start_utc: pd.Timestamp | None,
    end_utc: pd.Timestamp | None,
    label: str,
) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    """Return an optional ordered UTC entry window."""
    start = _optional_utc_timestamp(start_utc, f"{label} entry start")
    end = _optional_utc_timestamp(end_utc, f"{label} entry end")
    if start is not None and end is not None and start >= end:
        raise ValueError(f"{label} entry start must precede entry end")
    return start, end


def shift_btc_entry_signals(
    signals: pd.DataFrame,
    bars: pd.DataFrame,
    delay_minutes: int,
) -> pd.DataFrame:
    """Delay entry pulses and cancel pulses that cross explicit data gaps."""
    if delay_minutes < 0:
        raise ValueError("BTC entry delay must be nonnegative")
    output = signals.copy()
    if delay_minutes == 0:
        return output
    entries = ["long_entry", "short_entry"]
    output.loc[:, entries] = output.loc[:, entries].shift(
        delay_minutes,
        fill_value=False,
    )
    if "gap_before_bars" in bars:
        gaps = pd.to_numeric(bars["gap_before_bars"], errors="raise").gt(0)
        crossed = gaps.rolling(delay_minutes, min_periods=1).max().astype(bool)
        output.loc[crossed, entries] = False
    return output


def mask_btc_entry_window(
    signals: pd.DataFrame,
    start: pd.Timestamp | None,
    end: pd.Timestamp | None,
) -> pd.DataFrame:
    """Suppress entry pulses outside one half-open UTC partition."""
    output = signals.copy()
    selected = pd.Series(True, index=output.index)
    if start is not None:
        selected &= output.index >= start
    if end is not None:
        selected &= output.index < end
    output.loc[~selected, ["long_entry", "short_entry"]] = False
    return output


def validated_btc_replay_market(bars: pd.DataFrame, label: str) -> pd.DataFrame:
    """Return replay bars with exact finite funding and explicit gap counts."""
    if "funding_rate" not in bars:
        raise ValueError(f"{label} replay requires exact funding_rate")
    market = bars.copy()
    funding = pd.to_numeric(market["funding_rate"], errors="raise").astype(float)
    if not np.isfinite(funding.to_numpy()).all():
        raise ValueError(f"{label} funding must be finite")
    market["funding_rate"] = funding
    if "gap_before_bars" not in market:
        market["gap_before_bars"] = 0
    return market


def btc_fixed_60_60_portfolio_config(slippage_bps: float) -> SharedPortfolioConfig:
    """Return the frozen V58-compatible BTC 60/60/24h economic contract."""
    return SharedPortfolioConfig(
        symbol="BTC",
        initial_equity=5_000.0,
        margin_fraction=0.10,
        leverage=10.0,
        venue_max_leverage=40.0,
        maximum_notional_usd=5_000.0,
        target_margin_pct=6.0,
        stop_margin_pct=6.0,
        maximum_stop_distance_bps=60.0,
        entry_fee_rate=0.00045,
        target_fee_rate=0.00015,
        market_exit_fee_rate=0.00045,
        liquidation_fee_rate=0.00045,
        entry_slippage_bps=slippage_bps,
        market_exit_slippage_bps=slippage_bps,
        liquidation_slippage_bps=slippage_bps,
        max_hold_bars=1_440,
        reentry_cooldown_bars=1,
        same_direction_reentry_requires_reset=True,
        close_on_opposite_signal=False,
    )


def _optional_utc_timestamp(
    value: pd.Timestamp | None,
    label: str,
) -> pd.Timestamp | None:
    if value is None:
        return None
    timestamp = pd.Timestamp(value)
    if timestamp.tz is None:
        raise ValueError(f"{label} must be timezone-aware")
    return timestamp.tz_convert("UTC")

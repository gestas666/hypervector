"""Validated signal and market inputs for shared-portfolio screening."""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from hypervector.research.shared_portfolio_models import (
    Direction,
    SharedPortfolioConfig,
)
from hypervector.research.shared_portfolio_quotes import validate_execution_quotes


@dataclass(frozen=True)
class BarEntrySignal:
    """One close-known instruction eligible for next-bar entry."""

    direction: Direction
    signal_position: int
    signal_name: str
    target_price: float | None
    stop_price: float | None


def desired_entry(
    signals: pd.DataFrame,
    position: int,
) -> tuple[Direction | None, bool]:
    """Resolve one directional entry or report a simultaneous conflict."""
    if {"long_entry", "short_entry"}.issubset(signals.columns):
        long_entry = bool(signals["long_entry"].iloc[position])
        short_entry = bool(signals["short_entry"].iloc[position])
        if long_entry and short_entry:
            return None, True
        return ("long" if long_entry else "short" if short_entry else None), False
    value = signals["entry_direction"].iloc[position]
    return (value if value in ("long", "short") else None), False


def bar_entry_signal(
    signals: pd.DataFrame,
    position: int,
    direction: Direction,
) -> BarEntrySignal:
    """Capture optional source and barrier metadata at decision time."""
    side_name = f"{direction}_signal_name"
    name = (
        _optional_text(signals, side_name, position)
        or _optional_text(signals, "signal_name", position)
        or "unspecified"
    )
    target = _optional_number(signals, "target_price", position)
    stop = _optional_number(signals, "stop_price", position)
    return BarEntrySignal(direction, position, name, target, stop)


def side_exit_signal(
    signals: pd.DataFrame,
    position: int,
    direction: Direction,
) -> bool:
    """Return only the close instruction applicable to the open side."""
    side_column = f"{direction}_exit"
    if side_column in signals:
        return bool(signals[side_column].iloc[position])
    return bool(signals["exit_signal"].iloc[position])


def validate_barrier_side(
    entry: float,
    direction: Direction,
    target: float | None,
    stop: float | None,
) -> None:
    """Require target and stop prices to be directionally coherent."""
    if target is not None and not _barrier_is_valid(entry, direction, target, True):
        raise ValueError("target_price is on the wrong side of entry")
    if stop is not None and not _barrier_is_valid(entry, direction, stop, False):
        raise ValueError("stop_price is on the wrong side of entry")


def barriers_allow_entry(
    entry: float,
    direction: Direction,
    target: float | None,
    stop: float | None,
) -> bool:
    """Return whether close-defined barriers remain valid at next-bar entry."""
    target_valid = target is None or _barrier_is_valid(entry, direction, target, True)
    stop_valid = stop is None or _barrier_is_valid(entry, direction, stop, False)
    return target_valid and stop_valid


def _barrier_is_valid(
    entry: float,
    direction: Direction,
    barrier: float,
    favorable: bool,
) -> bool:
    greater = barrier > entry
    return greater == ((direction == "long") == favorable)


def validate_shared_inputs(
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    config: SharedPortfolioConfig,
) -> None:
    """Validate chronological OHLC, funding, and signal alignment."""
    required = {
        "open",
        "high",
        "low",
        "close",
        config.risk_high_column,
        config.risk_low_column,
    }
    if config.entry_risk_high_column is not None:
        required.add(config.entry_risk_high_column)
    if config.entry_risk_low_column is not None:
        required.add(config.entry_risk_low_column)
    missing = required.difference(bars.columns)
    if missing:
        raise ValueError(f"shared portfolio bars missing columns: {sorted(missing)}")
    if len(bars) < 2 or not isinstance(bars.index, pd.DatetimeIndex):
        raise ValueError("shared portfolio requires at least two datetime bars")
    if not bars.index.equals(signals.index):
        raise ValueError("shared portfolio bars and signals require the same index")
    if "exit_signal" not in signals and not {"long_exit", "short_exit"}.issubset(
        signals.columns
    ):
        raise ValueError("signals require exit_signal or long_exit/short_exit")
    if "entry_direction" not in signals and not {"long_entry", "short_entry"}.issubset(
        signals.columns
    ):
        raise ValueError("signals require entry_direction or long_entry/short_entry")
    _validate_market_values(bars, config)
    validate_execution_quotes(bars, config)


def _validate_market_values(
    bars: pd.DataFrame,
    config: SharedPortfolioConfig,
) -> None:
    if not bars.index.is_monotonic_increasing or not bars.index.is_unique:
        raise ValueError("shared portfolio bars require a unique increasing index")
    risk_columns = [config.risk_high_column, config.risk_low_column]
    if config.entry_risk_high_column is not None:
        risk_columns.append(config.entry_risk_high_column)
    if config.entry_risk_low_column is not None:
        risk_columns.append(config.entry_risk_low_column)
    risk = bars[list(dict.fromkeys(risk_columns))].astype(float)
    if not risk.map(math.isfinite).to_numpy().all() or risk.le(0.0).any().any():
        raise ValueError("shared portfolio risk high/low must be finite and positive")
    if risk[config.risk_high_column].lt(risk[config.risk_low_column]).any():
        raise ValueError("shared portfolio risk high must not be below risk low")
    if config.entry_risk_high_column is not None:
        if (
            risk[config.entry_risk_high_column]
            .lt(risk[config.entry_risk_low_column])
            .any()
        ):
            raise ValueError("shared portfolio entry risk high must not be below low")
    prices = bars.loc[:, ["open", "high", "low", "close"]].astype(float)
    if not prices.map(math.isfinite).to_numpy().all() or (prices <= 0.0).any().any():
        raise ValueError("shared portfolio OHLC must be finite and positive")
    if (prices["high"] < prices[["open", "close", "low"]].max(axis=1)).any():
        raise ValueError("shared portfolio high values are inconsistent")
    if (prices["low"] > prices[["open", "close", "high"]].min(axis=1)).any():
        raise ValueError("shared portfolio low values are inconsistent")
    if config.funding_column in bars:
        funding = bars[config.funding_column].astype(float)
        if not funding.map(math.isfinite).all():
            raise ValueError("shared portfolio funding must be finite")


def _optional_text(
    frame: pd.DataFrame,
    column: str,
    position: int,
) -> str | None:
    if column not in frame:
        return None
    value = frame[column].iloc[position]
    return value if isinstance(value, str) and value else None


def _optional_number(
    frame: pd.DataFrame,
    column: str,
    position: int,
) -> float | None:
    if column not in frame:
        return None
    value = frame[column].iloc[position]
    if pd.isna(value):
        return None
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError(f"{column} must contain finite positive prices")
    return number

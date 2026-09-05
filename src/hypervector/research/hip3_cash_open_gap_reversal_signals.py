"""Causal U.S. cash-open gap-reversal signals for HIP-3 research."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import math

import numpy as np
import pandas as pd


_NEW_YORK = "America/New_York"
_BAR_MINUTES = 15
_BAR_MS = _BAR_MINUTES * 60_000
_DECISION_MINUTE = 570
_SESSION_CLOSE_MINUTE = 945
_CLOSED_2026 = (date(2026, 6, 19), date(2026, 7, 3))
_SPCX_CLOSED_2026 = (
    date(2026, 1, 1),
    date(2026, 1, 19),
    date(2026, 2, 16),
    date(2026, 4, 3),
    date(2026, 5, 25),
    date(2026, 6, 19),
    date(2026, 7, 3),
    date(2026, 9, 7),
    date(2026, 11, 26),
    date(2026, 12, 25),
)
_SPCX_EARLY_CLOSES_2026 = (
    (date(2026, 11, 27), 765),
    (date(2026, 12, 24), 765),
)


@dataclass(frozen=True)
class Hip3CashOpenGapReversalConfig:
    """Frozen gap, protection, session, and holding parameters."""

    gap_threshold_bps: float = 20.0
    stop_bps: float = 80.0
    maximum_hold_bars: int = 25
    closed_session_dates: tuple[date, ...] = _CLOSED_2026
    early_close_minutes: tuple[tuple[date, int], ...] = ()

    def __post_init__(self) -> None:
        """Reject malformed parameters before any signal construction."""
        numbers = (self.gap_threshold_bps, self.stop_bps)
        if any(not math.isfinite(value) or value <= 0.0 for value in numbers):
            raise ValueError("cash-open gap and stop parameters must be positive")
        if isinstance(self.maximum_hold_bars, bool) or self.maximum_hold_bars <= 0:
            raise ValueError("cash-open maximum hold bars must be positive")
        dates = [value[0] for value in self.early_close_minutes]
        invalid = any(
            not isinstance(day, date)
            or isinstance(minute, bool)
            or not isinstance(minute, int)
            or not 0 <= minute < _SESSION_CLOSE_MINUTE
            for day, minute in self.early_close_minutes
        )
        if invalid or len(dates) != len(set(dates)):
            raise ValueError("cash-open early closes must be unique earlier minutes")


def spcx_cash_open_live_config() -> Hip3CashOpenGapReversalConfig:
    """Return the exact 2026 SPCX live signal and session contract."""
    return Hip3CashOpenGapReversalConfig(
        closed_session_dates=_SPCX_CLOSED_2026,
        early_close_minutes=_SPCX_EARLY_CLOSES_2026,
    )


def cash_session_bar_opens(
    start_ms: int,
    end_ms: int,
    config: Hip3CashOpenGapReversalConfig,
) -> pd.DatetimeIndex:
    """Return scheduled U.S. cash-session bar opens in one UTC window."""
    first_open_ms = (start_ms + _BAR_MS - 1) // _BAR_MS * _BAR_MS
    candidates = pd.date_range(
        pd.Timestamp(first_open_ms, unit="ms", tz="UTC"),
        pd.Timestamp(end_ms, unit="ms", tz="UTC"),
        freq=f"{_BAR_MINUTES}min",
        inclusive="left",
    )
    local = candidates.tz_convert(_NEW_YORK)
    overrides = dict(config.early_close_minutes)
    selected = [
        timestamp
        for timestamp, local_timestamp in zip(candidates, local, strict=True)
        if _scheduled_cash_bar(local_timestamp, config, overrides)
    ]
    return pd.DatetimeIndex(selected)


def latest_completed_cash_session_boundary_ms(
    observed_at_ms: int,
    minimum_start_ms: int,
    config: Hip3CashOpenGapReversalConfig,
) -> int | None:
    """Return the latest scheduled cash-bar close observable at a cutoff."""
    completed_boundary_ms = observed_at_ms // _BAR_MS * _BAR_MS
    opens = cash_session_bar_opens(
        minimum_start_ms,
        completed_boundary_ms,
        config,
    )
    if opens.empty:
        return None
    return int(opens[-1].timestamp() * 1_000) + _BAR_MS


def _scheduled_cash_bar(
    local: pd.Timestamp,
    config: Hip3CashOpenGapReversalConfig,
    close_overrides: dict[date, int],
) -> bool:
    day = local.date()
    minute = local.hour * 60 + local.minute
    close_minute = close_overrides.get(day, _SESSION_CLOSE_MINUTE)
    return (
        local.weekday() < 5
        and day not in config.closed_session_dates
        and _DECISION_MINUTE <= minute <= close_minute
    )


def build_hip3_cash_open_gap_reversal_signals(
    bars: pd.DataFrame,
    config: Hip3CashOpenGapReversalConfig,
) -> pd.DataFrame:
    """Return first-bar gap-fade entries, barriers, and causal exits."""
    frame = _validated_bars(bars)
    context = _session_context(frame, config)
    entries = _entry_signals(frame, context, config)
    exits = _exit_signals(frame, context)
    return pd.concat([entries, exits, context], axis=1)


def _session_context(
    frame: pd.DataFrame,
    config: Hip3CashOpenGapReversalConfig,
) -> pd.DataFrame:
    """Attach eligible local sessions and exact prior cash closes."""
    local = frame.index.tz_convert(_NEW_YORK)
    context = pd.DataFrame(index=frame.index)
    context["session_date"] = local.date
    context["local_minute"] = local.hour * 60 + local.minute
    weekday = pd.Series(local.weekday, index=frame.index).lt(5)
    context["session_eligible"] = weekday & ~context["session_date"].isin(
        config.closed_session_dates
    )
    overrides = dict(config.early_close_minutes)
    context["session_close_minute"] = context["session_date"].map(
        lambda value: overrides.get(value, _SESSION_CLOSE_MINUTE)
    )
    context["previous_cash_close"] = _previous_cash_close(frame, context)
    previous = context["previous_cash_close"].astype(float)
    context["opening_gap_bps"] = 10_000.0 * (frame["open"] / previous - 1.0)
    return context


def _previous_cash_close(
    frame: pd.DataFrame,
    context: pd.DataFrame,
) -> pd.Series:
    """Map each eligible date to the immediately prior eligible cash close."""
    eligible = context["session_eligible"]
    dates = pd.Index(context.loc[eligible, "session_date"].drop_duplicates())
    close_rows = (
        eligible
        & context["local_minute"].eq(context["session_close_minute"])
        & frame["gap_before_bars"].eq(0)
    )
    closes = frame["close"].where(close_rows).groupby(context["session_date"]).last()
    prior_by_date = closes.reindex(dates).shift(1)
    return context["session_date"].map(prior_by_date)


def _entry_signals(
    frame: pd.DataFrame,
    context: pd.DataFrame,
    config: Hip3CashOpenGapReversalConfig,
) -> pd.DataFrame:
    """Fade fixed large gaps only while the prior-close target remains ahead."""
    previous = context["previous_cash_close"].astype(float)
    gap = context["opening_gap_bps"].astype(float)
    ready = _decision_ready(frame, context)
    long_entry = ready & gap.le(-config.gap_threshold_bps) & frame["close"].lt(previous)
    short_entry = ready & gap.ge(config.gap_threshold_bps) & frame["close"].gt(previous)
    stop_fraction = config.stop_bps / 10_000.0
    stop = (frame["close"] * (1.0 - stop_fraction)).where(
        long_entry, (frame["close"] * (1.0 + stop_fraction)).where(short_entry)
    )
    output = pd.DataFrame(index=frame.index)
    output["long_entry"] = long_entry
    output["short_entry"] = short_entry
    output["entry_direction"] = np.select(
        [long_entry, short_entry], ["long", "short"], default=None
    )
    output["signal_name"] = output["entry_direction"].map(_SIGNAL_NAMES)
    output["stop_price"] = stop
    output["target_price"] = previous.where(long_entry | short_entry)
    output["execution_authority"] = "none"
    return output


_SIGNAL_NAMES = {
    "long": "hip3_cash_open_gap_reversal_long@15m",
    "short": "hip3_cash_open_gap_reversal_short@15m",
}


def _decision_ready(frame: pd.DataFrame, context: pd.DataFrame) -> pd.Series:
    """Require the completed opening bar and no source recovery at decision."""
    return (
        context["session_eligible"]
        & context["local_minute"].eq(_DECISION_MINUTE)
        & context["previous_cash_close"].notna()
        & frame["gap_before_bars"].eq(0)
    )


def _exit_signals(frame: pd.DataFrame, context: pd.DataFrame) -> pd.DataFrame:
    """Exit symmetrically on source recovery or the completed cash close."""
    recovery = frame["gap_before_bars"].gt(0)
    session_close = context["session_eligible"] & context["local_minute"].eq(
        context["session_close_minute"]
    )
    output = pd.DataFrame(index=frame.index)
    output["long_exit"] = recovery | session_close
    output["short_exit"] = recovery | session_close
    return output


def _validated_bars(bars: pd.DataFrame) -> pd.DataFrame:
    """Validate ordered, gap-aware, finite completed OHLC rows."""
    required = {"open", "high", "low", "close", "gap_before_bars"}
    missing = required.difference(bars.columns)
    if missing:
        raise ValueError(f"cash-open source bars missing columns: {sorted(missing)}")
    if not isinstance(bars.index, pd.DatetimeIndex) or bars.index.tz is None:
        raise ValueError("cash-open source bars require timezone-aware timestamps")
    if bars.empty or not bars.index.is_monotonic_increasing or not bars.index.is_unique:
        raise ValueError("cash-open source bars require ordered unique rows")
    _validate_values(bars)
    return bars.copy()


def _validate_values(bars: pd.DataFrame) -> None:
    """Reject invalid OHLC geometry and gap counts."""
    values = bars[["open", "high", "low", "close"]].to_numpy(dtype=float)
    gaps = bars["gap_before_bars"].to_numpy(dtype=float)
    invalid = not np.isfinite(values).all() or (values <= 0.0).any()
    invalid |= (values[:, 1] < values[:, [0, 2, 3]].max(axis=1)).any()
    invalid |= (values[:, 2] > values[:, [0, 1, 3]].min(axis=1)).any()
    if invalid or not np.isfinite(gaps).all() or (gaps < 0.0).any():
        raise ValueError("cash-open OHLC and gaps are invalid")

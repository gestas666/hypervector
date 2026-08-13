"""Point-in-time input preparation for the HYPE five-minute impulse study."""

from __future__ import annotations

from typing import Literal, Protocol

import pandas as pd

Side = Literal["long", "short"]
BAR_DURATION = pd.Timedelta(minutes=5)
BAR_COLUMNS = [
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "contains_gap_fill",
]


class ImpulseSignalConfig(Protocol):
    """Structural type required by the signal builder."""

    maximum_close_vs_ema21_bps: float
    maximum_di_delta: float
    maximum_roc_5_pct: float
    clean_history_bars: int


def aggregate_completed_five_minute_bars(minute: pd.DataFrame) -> pd.DataFrame:
    """Aggregate exact consecutive one-minute rows into completed five-minute bars."""
    frame = _validated_minute_frame(minute)
    frame["_bucket"] = frame["timestamp"].dt.floor("5min")
    rows: list[dict[str, object]] = []
    for timestamp, group in frame.groupby("_bucket", sort=True):
        expected = pd.date_range(timestamp, periods=5, freq="1min", tz="UTC")
        actual = group["timestamp"].reset_index(drop=True)
        if len(group) != 5 or not actual.equals(pd.Series(expected)):
            continue
        rows.append(_aggregate_group(pd.Timestamp(timestamp), group))
    return pd.DataFrame(rows, columns=BAR_COLUMNS)


def build_impulse_signals(
    bars: pd.DataFrame,
    *,
    config: ImpulseSignalConfig,
    side: Side,
) -> tuple[pd.Series, pd.Series]:
    """Build point-in-time impulse signals and ATR distance in basis points."""
    frame = validate_five_minute_bars(bars)
    _require_side(side)
    close = frame["close"]
    ema21 = close.ewm(span=21, adjust=False, min_periods=21).mean()
    close_gap = (close / ema21 - 1.0) * 10_000.0
    atr, di_delta = _wilder_atr_and_di_delta(frame)
    roc_5_pct = close.pct_change(5) * 100.0
    clean = _clean_history(frame["contains_gap_fill"], config.clean_history_bars)
    signal = _signal_for_side(close_gap, di_delta, roc_5_pct, clean, config, side)
    return signal.fillna(False).astype(bool), (atr / close) * 10_000.0


def validate_five_minute_bars(bars: pd.DataFrame) -> pd.DataFrame:
    """Return canonical bars after exact schema, identity, and cadence checks."""
    missing = sorted(set(BAR_COLUMNS) - set(bars.columns))
    if missing:
        raise ValueError(f"HYPE five-minute bars missing columns: {missing}")
    frame = bars.loc[:, BAR_COLUMNS].copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    _require_ordered_unique(frame["timestamp"], "HYPE five-minute bars")
    if len(frame) > 1 and not frame["timestamp"].diff().iloc[1:].eq(BAR_DURATION).all():
        raise ValueError("HYPE five-minute bars must have exact five-minute cadence")
    return frame.reset_index(drop=True)


def _validated_minute_frame(minute: pd.DataFrame) -> pd.DataFrame:
    required = {"timestamp", "open", "high", "low", "close", "volume", "source"}
    missing = sorted(required - set(minute.columns))
    if missing:
        raise ValueError(f"HYPE one-minute bars missing columns: {missing}")
    frame = minute.loc[:, sorted(required)].copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    _require_ordered_unique(frame["timestamp"], "HYPE one-minute bars")
    if not set(frame["source"].astype(str)).issubset({"hl", "hl_gap_fill"}):
        raise ValueError("HYPE one-minute bars contain an unsupported source")
    return frame.reset_index(drop=True)


def _aggregate_group(timestamp: pd.Timestamp, group: pd.DataFrame) -> dict[str, object]:
    return {
        "timestamp": timestamp,
        "open": float(group.iloc[0]["open"]),
        "high": float(group["high"].max()),
        "low": float(group["low"].min()),
        "close": float(group.iloc[-1]["close"]),
        "volume": float(group["volume"].sum()),
        "contains_gap_fill": bool(group["source"].eq("hl_gap_fill").any()),
    }


def _wilder_atr_and_di_delta(frame: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    previous_close = frame["close"].shift(1)
    true_range = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - previous_close).abs(),
            (frame["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    up = frame["high"].diff()
    down = -frame["low"].diff()
    plus_dm = up.where((up > down) & (up > 0), 0.0)
    minus_dm = down.where((down > up) & (down > 0), 0.0)
    atr = true_range.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    plus_di = _directional_index(plus_dm, atr)
    minus_di = _directional_index(minus_dm, atr)
    return atr, plus_di - minus_di


def _directional_index(movement: pd.Series, atr: pd.Series) -> pd.Series:
    smoothed = movement.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    return 100.0 * smoothed / atr


def _signal_for_side(
    gap: pd.Series,
    di_delta: pd.Series,
    roc: pd.Series,
    clean: pd.Series,
    config: ImpulseSignalConfig,
    side: Side,
) -> pd.Series:
    if side == "long":
        return (
            clean
            & gap.le(config.maximum_close_vs_ema21_bps)
            & di_delta.le(config.maximum_di_delta)
            & roc.le(config.maximum_roc_5_pct)
        )
    return (
        clean
        & gap.ge(abs(config.maximum_close_vs_ema21_bps))
        & di_delta.ge(abs(config.maximum_di_delta))
        & roc.ge(abs(config.maximum_roc_5_pct))
    )


def _clean_history(gaps: pd.Series, bars: int) -> pd.Series:
    return gaps.astype(int).rolling(bars, min_periods=bars).sum().eq(0)


def _require_ordered_unique(timestamps: pd.Series, label: str) -> None:
    if timestamps.isna().any() or timestamps.duplicated().any():
        raise ValueError(f"{label} timestamps must be non-null and unique")
    if not timestamps.is_monotonic_increasing:
        raise ValueError(f"{label} timestamps must be ordered")


def _require_side(side: str) -> None:
    if side not in {"long", "short"}:
        raise ValueError("HYPE impulse side must be long or short")

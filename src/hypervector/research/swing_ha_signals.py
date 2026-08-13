"""Causal Swing Auto and Heikin-Ashi signal reconstruction."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Literal

import numpy as np
import pandas as pd

from hypervector.research.swing_order_blocks import build_order_block_state

EntryMode = Literal["state", "onset"]
ExitMode = Literal["ha_flip", "alignment_loss"]
OrderBlockRole = Literal["none", "agreement", "structural_stop"]
_OHLC = ("open", "high", "low", "close")


@dataclass(frozen=True)
class SwingHaSignalConfig:
    """Immutable signal and order-block translation parameters."""

    fast_ema: int = 9
    slow_ema: int = 21
    pivot_length: int = 5
    entry_mode: EntryMode = "state"
    exit_mode: ExitMode = "ha_flip"
    order_block_role: OrderBlockRole = "none"
    order_block_periods: int = 5
    order_block_minimum_move_pct: float = 0.0

    def __post_init__(self) -> None:
        """Reject malformed or internally inconsistent signal parameters."""
        _positive_integer(self.fast_ema, "fast_ema")
        _positive_integer(self.slow_ema, "slow_ema")
        if self.fast_ema >= self.slow_ema:
            raise ValueError("fast_ema must be below slow_ema")
        _positive_integer(self.pivot_length, "pivot_length")
        if self.entry_mode not in ("state", "onset"):
            raise ValueError("entry_mode must be state or onset")
        if self.exit_mode not in ("ha_flip", "alignment_loss"):
            raise ValueError("exit_mode must be ha_flip or alignment_loss")
        if self.order_block_role not in ("none", "agreement", "structural_stop"):
            raise ValueError("unsupported order_block_role")
        _positive_integer(self.order_block_periods, "order_block_periods")
        move = self.order_block_minimum_move_pct
        if not math.isfinite(move) or move < 0.0:
            raise ValueError("order-block minimum move must be non-negative")


def build_heikin_ashi(bars: pd.DataFrame) -> pd.DataFrame:
    """Build recursive Heikin-Ashi values for signal use only."""
    frame = _validated_bars(bars)
    ha_close = frame.loc[:, list(_OHLC)].mean(axis=1).to_numpy(dtype=np.float64)
    ha_open = np.empty(len(frame), dtype=np.float64)
    ha_open[0] = (float(frame["open"].iloc[0]) + float(frame["close"].iloc[0])) / 2
    for position in range(1, len(frame)):
        ha_open[position] = (ha_open[position - 1] + ha_close[position - 1]) / 2
    return pd.DataFrame(
        {
            "ha_open": ha_open,
            "ha_high": np.maximum.reduce(
                [frame["high"].to_numpy(float), ha_open, ha_close]
            ),
            "ha_low": np.minimum.reduce(
                [frame["low"].to_numpy(float), ha_open, ha_close]
            ),
            "ha_close": ha_close,
        },
        index=frame.index,
    )


def confirmed_pivot_levels(bars: pd.DataFrame, *, pivot_length: int) -> pd.DataFrame:
    """Expose pivot levels at confirmation time, never at the plotted source."""
    frame = _validated_bars(bars)
    _positive_integer(pivot_length, "pivot_length")
    highs = frame["high"].to_numpy(dtype=np.float64)
    lows = frame["low"].to_numpy(dtype=np.float64)
    records = _pivot_records(highs, lows, pivot_length)
    return pd.DataFrame.from_records(records, index=frame.index)


def build_swing_ha_signals(
    bars: pd.DataFrame,
    config: SwingHaSignalConfig | None = None,
) -> pd.DataFrame:
    """Build aligned long/short states, entries, exits, and diagnostics."""
    cfg = config or SwingHaSignalConfig()
    frame = _validated_bars(bars)
    ha = build_heikin_ashi(frame)
    pivots = confirmed_pivot_levels(frame, pivot_length=cfg.pivot_length)
    blocks = _order_blocks(frame, cfg)
    output = _base_features(frame, ha, pivots, blocks, cfg)
    output = _entry_exit_columns(output, cfg)
    output["long_signal_name"] = "swing_ha_long@15m"
    output["short_signal_name"] = "swing_ha_short@15m"
    output["execution_authority"] = "none"
    return output


def _order_blocks(bars: pd.DataFrame, config: SwingHaSignalConfig) -> pd.DataFrame:
    if config.order_block_role == "none":
        return _neutral_order_blocks(bars.index)
    return build_order_block_state(
        bars,
        periods=config.order_block_periods,
        minimum_move_pct=config.order_block_minimum_move_pct,
    )


def _neutral_order_blocks(index: pd.DatetimeIndex) -> pd.DataFrame:
    values: dict[str, object] = {
        "bull_ob_detected": False,
        "bear_ob_detected": False,
        "active_bull_ob_low": np.nan,
        "active_bull_ob_high": np.nan,
        "active_bear_ob_low": np.nan,
        "active_bear_ob_high": np.nan,
        "bull_ob_source_position": np.nan,
        "bear_ob_source_position": np.nan,
        "active_ob_direction": 0,
    }
    return pd.DataFrame(values, index=index)


def _pivot_records(
    highs: np.ndarray, lows: np.ndarray, length: int
) -> list[dict[str, float]]:
    last_high = math.nan
    last_low = math.nan
    high_source = math.nan
    low_source = math.nan
    records: list[dict[str, float]] = []
    for position in range(len(highs)):
        source = position - length
        if source >= length:
            window = slice(source - length, source + length + 1)
            if highs[source] == np.max(highs[window]):
                last_high, high_source = float(highs[source]), float(source)
            if lows[source] == np.min(lows[window]):
                last_low, low_source = float(lows[source]), float(source)
        records.append(
            {
                "last_pivot_high": last_high,
                "last_pivot_low": last_low,
                "pivot_high_source_position": high_source,
                "pivot_low_source_position": low_source,
            }
        )
    return records


def _base_features(
    bars: pd.DataFrame,
    ha: pd.DataFrame,
    pivots: pd.DataFrame,
    blocks: pd.DataFrame,
    config: SwingHaSignalConfig,
) -> pd.DataFrame:
    output = pd.concat([ha, pivots, blocks], axis=1)
    output["ema_fast"] = (
        bars["close"]
        .ewm(span=config.fast_ema, adjust=False, min_periods=config.fast_ema)
        .mean()
    )
    output["ema_slow"] = (
        bars["close"]
        .ewm(span=config.slow_ema, adjust=False, min_periods=config.slow_ema)
        .mean()
    )
    output["ha_color"] = np.sign(output["ha_close"] - output["ha_open"]).astype(int)
    output["buy_state"] = bars["close"].gt(output["last_pivot_high"]) & output[
        "ema_fast"
    ].gt(output["ema_slow"])
    output["sell_state"] = bars["close"].lt(output["last_pivot_low"]) & output[
        "ema_fast"
    ].lt(output["ema_slow"])
    output["long_alignment"] = output["buy_state"] & output["ha_color"].eq(1)
    output["short_alignment"] = output["sell_state"] & output["ha_color"].eq(-1)
    return _apply_order_block_role(output, bars, config)


def _apply_order_block_role(
    output: pd.DataFrame,
    bars: pd.DataFrame,
    config: SwingHaSignalConfig,
) -> pd.DataFrame:
    if config.order_block_role == "agreement":
        output["long_alignment"] &= output["active_ob_direction"].eq(1)
        output["short_alignment"] &= output["active_ob_direction"].eq(-1)
    output["long_stop_price"] = np.where(
        output["active_bull_ob_low"].lt(bars["close"]),
        output["active_bull_ob_low"],
        np.nan,
    )
    output["short_stop_price"] = np.where(
        output["active_bear_ob_high"].gt(bars["close"]),
        output["active_bear_ob_high"],
        np.nan,
    )
    return output


def _entry_exit_columns(
    output: pd.DataFrame, config: SwingHaSignalConfig
) -> pd.DataFrame:
    if config.entry_mode == "onset":
        output["long_entry"] = _onset(output["long_alignment"])
        output["short_entry"] = _onset(output["short_alignment"])
    else:
        output["long_entry"] = output["long_alignment"]
        output["short_entry"] = output["short_alignment"]
    if config.exit_mode == "ha_flip":
        output["long_exit"] = output["ha_color"].eq(-1)
        output["short_exit"] = output["ha_color"].eq(1)
    else:
        output["long_exit"] = ~output["long_alignment"]
        output["short_exit"] = ~output["short_alignment"]
    output["stop_price"] = _entry_stop(output, config.order_block_role)
    return output


def _entry_stop(output: pd.DataFrame, role: OrderBlockRole) -> pd.Series:
    stops = pd.Series(np.nan, index=output.index, dtype=float)
    if role != "structural_stop":
        return stops
    stops.loc[output["long_entry"]] = output.loc[
        output["long_entry"], "long_stop_price"
    ]
    stops.loc[output["short_entry"]] = output.loc[
        output["short_entry"], "short_stop_price"
    ]
    return stops


def _onset(state: pd.Series) -> pd.Series:
    return state & ~state.shift(1, fill_value=False)


def _validated_bars(bars: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(set(_OHLC).difference(bars.columns))
    if missing:
        raise ValueError(f"Swing/HA bars missing columns: {missing}")
    if not isinstance(bars.index, pd.DatetimeIndex) or bars.index.tz is None:
        raise ValueError("Swing/HA bars require a timezone-aware index")
    if bars.empty or not bars.index.is_monotonic_increasing or not bars.index.is_unique:
        raise ValueError("Swing/HA bars require ordered unique rows")
    values = bars.loc[:, list(_OHLC)].to_numpy(dtype=np.float64)
    if not np.isfinite(values).all() or (values <= 0.0).any():
        raise ValueError("Swing/HA OHLC must contain finite positive values")
    return bars


def _positive_integer(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")

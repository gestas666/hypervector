"""Literal Swing Auto signals evaluated in the Heikin-Ashi chart domain."""

from __future__ import annotations

import numpy as np
import pandas as pd

from hypervector.research.swing_ha_signals import (
    SwingHaSignalConfig,
    build_heikin_ashi,
    confirmed_pivot_levels,
)
from hypervector.research.swing_order_blocks import build_order_block_state


def build_swing_ha_chart_signals(
    raw_bars: pd.DataFrame,
    config: SwingHaSignalConfig,
) -> pd.DataFrame:
    """Build Swing Auto state on HA OHLC while leaving raw bars for fills."""
    chart = _heikin_ashi_chart(raw_bars)
    pivots = confirmed_pivot_levels(chart, pivot_length=config.pivot_length)
    blocks = _order_blocks(chart, config)
    output = pd.concat([_display_columns(chart), pivots, blocks], axis=1)
    _add_swing_state(output, chart, config)
    _apply_order_block_role(output, chart, config)
    _add_entry_exit_state(output, config)
    output["signal_price_domain"] = "heikin_ashi_chart"
    output["long_signal_name"] = "swing_ha_chart_long@15m"
    output["short_signal_name"] = "swing_ha_chart_short@15m"
    output["execution_authority"] = "none"
    return output


def _heikin_ashi_chart(raw_bars: pd.DataFrame) -> pd.DataFrame:
    values = build_heikin_ashi(raw_bars)
    return values.rename(
        columns={
            "ha_open": "open",
            "ha_high": "high",
            "ha_low": "low",
            "ha_close": "close",
        }
    )


def _display_columns(chart: pd.DataFrame) -> pd.DataFrame:
    return chart.rename(
        columns={
            "open": "ha_open",
            "high": "ha_high",
            "low": "ha_low",
            "close": "ha_close",
        }
    )


def _order_blocks(
    chart: pd.DataFrame,
    config: SwingHaSignalConfig,
) -> pd.DataFrame:
    if config.order_block_role != "none":
        return build_order_block_state(
            chart,
            periods=config.order_block_periods,
            minimum_move_pct=config.order_block_minimum_move_pct,
        )
    return _neutral_order_blocks(chart.index)


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


def _add_swing_state(
    output: pd.DataFrame,
    chart: pd.DataFrame,
    config: SwingHaSignalConfig,
) -> None:
    output["ema_fast"] = (
        chart["close"]
        .ewm(
            span=config.fast_ema,
            adjust=False,
            min_periods=config.fast_ema,
        )
        .mean()
    )
    output["ema_slow"] = (
        chart["close"]
        .ewm(
            span=config.slow_ema,
            adjust=False,
            min_periods=config.slow_ema,
        )
        .mean()
    )
    output["ha_color"] = np.sign(chart["close"] - chart["open"]).astype(int)
    output["buy_state"] = chart["close"].gt(output["last_pivot_high"]) & output[
        "ema_fast"
    ].gt(output["ema_slow"])
    output["sell_state"] = chart["close"].lt(output["last_pivot_low"]) & output[
        "ema_fast"
    ].lt(output["ema_slow"])
    output["long_alignment"] = output["buy_state"] & output["ha_color"].eq(1)
    output["short_alignment"] = output["sell_state"] & output["ha_color"].eq(-1)


def _apply_order_block_role(
    output: pd.DataFrame,
    chart: pd.DataFrame,
    config: SwingHaSignalConfig,
) -> None:
    if config.order_block_role == "agreement":
        output["long_alignment"] &= output["active_ob_direction"].eq(1)
        output["short_alignment"] &= output["active_ob_direction"].eq(-1)
    output["long_stop_price"] = np.where(
        output["active_bull_ob_low"].lt(chart["close"]),
        output["active_bull_ob_low"],
        np.nan,
    )
    output["short_stop_price"] = np.where(
        output["active_bear_ob_high"].gt(chart["close"]),
        output["active_bear_ob_high"],
        np.nan,
    )


def _add_entry_exit_state(
    output: pd.DataFrame,
    config: SwingHaSignalConfig,
) -> None:
    if config.entry_mode == "onset":
        output["long_entry"] = _onset(output["long_alignment"])
        output["short_entry"] = _onset(output["short_alignment"])
    else:
        output["long_entry"] = output["long_alignment"]
        output["short_entry"] = output["short_alignment"]
    if config.exit_mode == "alignment_loss":
        output["long_exit"] = ~output["long_alignment"]
        output["short_exit"] = ~output["short_alignment"]
    else:
        output["long_exit"] = output["ha_color"].eq(-1)
        output["short_exit"] = output["ha_color"].eq(1)
    output["stop_price"] = _entry_stop(output, config.order_block_role)


def _entry_stop(output: pd.DataFrame, role: str) -> pd.Series:
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

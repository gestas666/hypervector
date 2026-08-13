"""Experiment orchestration contracts for the Swing/HA screen."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pandas as pd

from hypervector.research.swing_ha_experiment import (
    config_summary,
    gap_touched_trade_count,
    select_development_config,
)
from hypervector.research.swing_ha_experiment_data import default_asset_inputs
from hypervector.research.swing_ha_screen import SwingHaScreenCell
from hypervector.research.swing_ha_signals import SwingHaSignalConfig


def _cell(
    symbol: str,
    net: float,
    *,
    longs: int = 3,
    shorts: int = 3,
) -> SwingHaScreenCell:
    return SwingHaScreenCell(
        symbol=symbol,
        signal_config={},
        completed_trades=longs + shorts,
        wins=4,
        losses=2,
        net_pnl_usd=net,
        return_pct=net / 150.0,
        profit_factor=1.5,
        maximum_drawdown_pct=2.0,
        liquidations=0,
        total_fees_usd=10.0,
        funding_cashflow_usd=0.0,
        direction_trades={"long": longs, "short": shorts},
        direction_net_pnl_usd={"long": net / 2, "short": net / 2},
        forced_end_exits=0,
        trade_records=(),
    )


def test_default_inputs_cover_all_four_native_perpetuals() -> None:
    inputs = default_asset_inputs(Path("data"))

    assert [item.symbol for item in inputs] == ["BTC", "ETH", "SOL", "HYPE"]
    assert all(item.bars_path.name.endswith("_1m_365d.parquet") for item in inputs)


def test_selection_prefers_broad_bidirectional_positive_evidence() -> None:
    broad = SwingHaSignalConfig(fast_ema=9, slow_ema=21)
    narrow = replace(broad, fast_ema=7)
    broad_cells = tuple(
        _cell(symbol, 100.0) for symbol in ("BTC", "ETH", "SOL", "HYPE")
    )
    narrow_cells = tuple(
        _cell(symbol, 500.0, shorts=0) for symbol in ("BTC", "ETH", "SOL", "HYPE")
    )

    selected = select_development_config(
        {broad: broad_cells, narrow: narrow_cells},
        {broad: broad_cells, narrow: narrow_cells},
    )

    assert selected == broad
    summary = config_summary(broad, broad_cells, broad_cells)
    assert summary["bidirectional_coin_count"] == 4
    assert summary["positive_coin_count"] == 4


def test_gap_touch_count_uses_complete_trade_lifecycle_positions() -> None:
    bars = pd.DataFrame(
        {"gap_fill_touched": [False, True, False, False]},
        index=pd.date_range("2026-01-01", periods=4, freq="15min", tz="UTC"),
    )
    cell = _cell("BTC", 10.0)
    trade = {
        "entry_position": 0,
        "exit_position": 2,
    }
    with_trade = replace(cell, trade_records=(trade,))

    assert gap_touched_trade_count(bars, with_trade) == 1

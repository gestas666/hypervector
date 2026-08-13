"""Chronological tuning and validation orchestration for Swing/HA."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import median

import pandas as pd

from hypervector.research.swing_ha_experiment_data import SwingHaAssetData
from hypervector.research.swing_ha_screen import (
    SwingHaScreenCell,
    SwingHaScreenConfig,
    delayed_signals,
    evaluate_swing_ha_cell,
    signal_config_id,
)
from hypervector.research.swing_ha_signals import (
    SwingHaSignalConfig,
    build_swing_ha_signals,
)


@dataclass(frozen=True)
class SwingHaEvaluation:
    """One full and chronological-fold evaluation for a signal config."""

    config: SwingHaSignalConfig
    full_cells: tuple[SwingHaScreenCell, ...]
    fold_cells: tuple[SwingHaScreenCell, ...]


def evaluate_development_grid(
    assets: tuple[SwingHaAssetData, ...],
    configs: tuple[SwingHaSignalConfig, ...],
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> tuple[SwingHaEvaluation, ...]:
    """Evaluate every configuration on the full window and three flat folds."""
    folds = _development_folds(start, end)
    evaluations: list[SwingHaEvaluation] = []
    for config in configs:
        full_cells: list[SwingHaScreenCell] = []
        fold_cells: list[SwingHaScreenCell] = []
        for asset in assets:
            signals = build_swing_ha_signals(asset.bars, config)
            full_cells.append(_evaluate_window(asset, signals, config, start, end))
            fold_cells.extend(
                _evaluate_window(asset, signals, config, fold_start, fold_end)
                for fold_start, fold_end in folds
            )
        evaluations.append(
            SwingHaEvaluation(config, tuple(full_cells), tuple(fold_cells))
        )
    return tuple(evaluations)


def select_development_config(
    full_cells: dict[SwingHaSignalConfig, tuple[SwingHaScreenCell, ...]],
    fold_cells: dict[SwingHaSignalConfig, tuple[SwingHaScreenCell, ...]],
) -> SwingHaSignalConfig:
    """Select stable broad bidirectional evidence using development only."""
    if not full_cells or set(full_cells) != set(fold_cells):
        raise ValueError("development selection requires matching non-empty cells")
    return max(
        full_cells,
        key=lambda config: _selection_key(full_cells[config], fold_cells[config]),
    )


def selected_from_evaluations(
    evaluations: tuple[SwingHaEvaluation, ...],
) -> SwingHaSignalConfig:
    """Select one development configuration from complete evaluations."""
    return select_development_config(
        {item.config: item.full_cells for item in evaluations},
        {item.config: item.fold_cells for item in evaluations},
    )


def config_summary(
    config: SwingHaSignalConfig,
    full_cells: tuple[SwingHaScreenCell, ...],
    fold_cells: tuple[SwingHaScreenCell, ...],
) -> dict[str, object]:
    """Return compact complete metrics for ranking and audit."""
    fold_returns = [cell.return_pct for cell in fold_cells]
    coin_returns = [cell.return_pct for cell in full_cells]
    return {
        "config_id": signal_config_id(config),
        "config": asdict(config),
        "bidirectional_coin_count": sum(_bidirectional(cell) for cell in full_cells),
        "positive_coin_count": sum(cell.net_pnl_usd > 0.0 for cell in full_cells),
        "positive_fold_count": sum(cell.net_pnl_usd > 0.0 for cell in fold_cells),
        "coin_count": len(full_cells),
        "fold_cell_count": len(fold_cells),
        "median_coin_return_pct": median(coin_returns),
        "median_fold_return_pct": median(fold_returns),
        "worst_fold_return_pct": min(fold_returns),
        "total_net_pnl_usd": sum(cell.net_pnl_usd for cell in full_cells),
        "total_trades": sum(cell.completed_trades for cell in full_cells),
        "long_trades": sum(cell.direction_trades["long"] for cell in full_cells),
        "short_trades": sum(cell.direction_trades["short"] for cell in full_cells),
        "liquidations": sum(cell.liquidations for cell in full_cells),
        "maximum_cell_drawdown_pct": max(
            cell.maximum_drawdown_pct for cell in full_cells
        ),
        "asset_cells": [_compact_cell(cell) for cell in full_cells],
        "fold_cells": [_compact_cell(cell) for cell in fold_cells],
        "execution_authority": "none",
    }


def evaluate_frozen_segment(
    assets: tuple[SwingHaAssetData, ...],
    config: SwingHaSignalConfig,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    screen_config: SwingHaScreenConfig | None = None,
    entry_delay_bars: int = 0,
) -> tuple[SwingHaScreenCell, ...]:
    """Evaluate one frozen config on an untouched chronological segment."""
    cells: list[SwingHaScreenCell] = []
    for asset in assets:
        signals = build_swing_ha_signals(asset.bars, config)
        if entry_delay_bars:
            signals = delayed_signals(signals, bars=entry_delay_bars)
        cells.append(
            _evaluate_window(
                asset, signals, config, start, end, screen_config=screen_config
            )
        )
    return tuple(cells)


def gap_touched_trade_count(bars: pd.DataFrame, cell: SwingHaScreenCell) -> int:
    """Count trades whose complete entry-to-exit path touches a gap-fill bar."""
    touched = 0
    flags = bars["gap_fill_touched"].astype(bool)
    for trade in cell.trade_records:
        start = int(trade["entry_position"])
        end = int(trade["exit_position"])
        touched += int(flags.iloc[start : end + 1].any())
    return touched


def evaluation_summaries(
    evaluations: tuple[SwingHaEvaluation, ...],
) -> list[dict[str, object]]:
    """Return every development trial without success-shaped filtering."""
    return [
        config_summary(item.config, item.full_cells, item.fold_cells)
        for item in evaluations
    ]


def _evaluate_window(
    asset: SwingHaAssetData,
    signals: pd.DataFrame,
    config: SwingHaSignalConfig,
    start: pd.Timestamp,
    end: pd.Timestamp,
    *,
    screen_config: SwingHaScreenConfig | None = None,
) -> SwingHaScreenCell:
    selected = asset.bars.index.to_series().ge(start) & asset.bars.index.to_series().lt(
        end
    )
    bars = asset.bars.loc[selected].copy()
    window_signals = signals.loc[selected].copy()
    _reject_gap_through_stops(bars, window_signals)
    return evaluate_swing_ha_cell(
        bars,
        window_signals,
        symbol=asset.symbol,
        signal_config=config,
        venue_max_leverage=asset.venue_max_leverage,
        screen_config=screen_config,
    )


def _reject_gap_through_stops(bars: pd.DataFrame, signals: pd.DataFrame) -> None:
    next_open = bars["open"].shift(-1)
    stop = signals["stop_price"]
    invalid_long = signals["long_entry"] & stop.notna() & stop.ge(next_open)
    invalid_short = signals["short_entry"] & stop.notna() & stop.le(next_open)
    signals.loc[invalid_long, "long_entry"] = False
    signals.loc[invalid_short, "short_entry"] = False


def _development_folds(
    start: pd.Timestamp, end: pd.Timestamp
) -> tuple[tuple[pd.Timestamp, pd.Timestamp], ...]:
    if start >= end:
        raise ValueError("development start must precede end")
    first = start + pd.Timedelta(days=62)
    second = first + pd.Timedelta(days=61)
    if second >= end:
        raise ValueError("development window is too short for frozen folds")
    return ((start, first), (first, second), (second, end))


def _selection_key(
    full_cells: tuple[SwingHaScreenCell, ...],
    fold_cells: tuple[SwingHaScreenCell, ...],
) -> tuple[float, ...]:
    summary = config_summary(SwingHaSignalConfig(), full_cells, fold_cells)
    return (
        float(summary["bidirectional_coin_count"]),
        float(summary["positive_coin_count"]),
        float(summary["positive_fold_count"]),
        float(summary["median_fold_return_pct"]),
        float(summary["worst_fold_return_pct"]),
        float(summary["median_coin_return_pct"]),
        -float(summary["liquidations"]),
        -float(summary["maximum_cell_drawdown_pct"]),
    )


def _bidirectional(cell: SwingHaScreenCell) -> bool:
    return cell.direction_trades["long"] > 0 and cell.direction_trades["short"] > 0


def _compact_cell(cell: SwingHaScreenCell) -> dict[str, object]:
    values = asdict(cell)
    values.pop("trade_records")
    return values

"""Complete-cell tests for the four-Pine 15m/30m development screen."""

from __future__ import annotations

import numpy as np
import pandas as pd
import duckdb
import pytest

from hypervector.research.pine_stack_features import build_pine_stack_features
from hypervector.research.pine_stack_screen import (
    PineStackScreenConfig,
    evaluate_pine_stack_cells,
)
from hypervector.research.pine_stack_screen_journal import PineStackScreenJournal
from hypervector.research.pine_stack_signals import compose_pine_stack_entries


def _bars(rows: int = 500) -> pd.DataFrame:
    """Return deterministic 15m waves with an explicit zero funding column."""
    positions = np.arange(rows, dtype=float)
    close = 100.0 + 6.0 * np.sin(positions / 10.0)
    open_ = np.concatenate(([close[0]], close[:-1]))
    return pd.DataFrame(
        {
            "bar_open_at": pd.date_range(
                "2026-01-01", periods=rows, freq="15min", tz="UTC"
            ),
            "open": open_,
            "high": np.maximum(open_, close) + 0.5,
            "low": np.minimum(open_, close) - 0.5,
            "close": close,
            "volume": 100.0 + positions,
            "funding_rate": np.zeros(rows),
        }
    )


def test_screen_retains_all_entry_exit_cells_and_denies_execution() -> None:
    """All 24 ablations must remain visible even when a cell has no entries."""
    bars = _bars()
    features = build_pine_stack_features(bars, bar_minutes=15)
    entries = compose_pine_stack_entries(features, symbol="BTC")

    cells = evaluate_pine_stack_cells(
        bars=bars,
        features=features,
        entries=entries,
        symbol="BTC",
        bar_minutes=15,
        venue_max_leverage=40.0,
        config=PineStackScreenConfig(maximum_hold_hours=4),
    )

    assert len(cells) == 24
    assert len({(cell.candidate, cell.exit_variant) for cell in cells}) == 24
    assert any(cell.signal_count == 0 for cell in cells)
    assert all(cell.execution_authority == "none" for cell in cells)
    assert all(cell.bar_minutes == 15 for cell in cells)


def test_screen_uses_duration_matched_hold_and_realistic_cost_contract() -> None:
    """15m and 30m trials must share hours, fees, slippage, and risk semantics."""
    config = PineStackScreenConfig(maximum_hold_hours=8)

    fifteen = config.portfolio_config(
        symbol="BTC", bar_minutes=15, venue_max_leverage=40.0
    )
    thirty = config.portfolio_config(
        symbol="ETH", bar_minutes=30, venue_max_leverage=25.0
    )

    assert fifteen.max_hold_bars == 32
    assert thirty.max_hold_bars == 16
    assert fifteen.entry_fee_rate == thirty.entry_fee_rate == 0.00045
    assert fifteen.market_exit_fee_rate == thirty.market_exit_fee_rate == 0.00045
    assert fifteen.entry_slippage_bps == thirty.entry_slippage_bps == 2.0
    assert fifteen.margin_fraction == thirty.margin_fraction == 0.10
    assert fifteen.leverage == thirty.leverage == 5.0
    assert fifteen.stop_margin_pct == thirty.stop_margin_pct == 10.0


def test_screen_journal_separates_complete_cells_and_trade_rows(tmp_path) -> None:
    """DuckDB must retain every cell and trade without bloating summary JSON."""
    bars = _bars()
    features = build_pine_stack_features(bars, bar_minutes=15)
    entries = compose_pine_stack_entries(features, symbol="BTC")
    cells = evaluate_pine_stack_cells(
        bars=bars,
        features=features,
        entries=entries,
        symbol="BTC",
        bar_minutes=15,
        venue_max_leverage=40.0,
    )
    journal = PineStackScreenJournal(tmp_path / "strategy_trials.duckdb")

    journal.write_run(
        run_id="pine_stack_test_v1",
        segment="development",
        source_identity=({"symbol": "BTC", "bar_minutes": 15},),
        cells=cells,
    )

    with duckdb.connect(str(journal.path), read_only=True) as connection:
        run_count = connection.execute(
            "SELECT count(*) FROM pine_stack_screen_runs"
        ).fetchone()
        cell_count = connection.execute(
            "SELECT count(*) FROM pine_stack_screen_cells"
        ).fetchone()
        trade_count = connection.execute(
            "SELECT count(*) FROM pine_stack_screen_trades"
        ).fetchone()
    assert run_count == (1,)
    assert cell_count == (24,)
    assert trade_count == (sum(cell.completed_trades for cell in cells),)
    with pytest.raises(ValueError, match="already exists"):
        journal.write_run(
            run_id="pine_stack_test_v1",
            segment="development",
            source_identity=({"symbol": "BTC", "bar_minutes": 15},),
            cells=cells,
        )

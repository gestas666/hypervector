"""Reported PnL includes open positions; trade count is reported next to orders."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hypervector.nautilus.runner import run_phase2_backtest
from nautilus_fix_support import (
    FIXTEST_ENTER_AT,
    capture_engine,
    register_fix_strategies,
    synth_ohlcv,
    write_export,
)


@pytest.fixture(autouse=True)
def _strategies() -> None:
    register_fix_strategies()


def test_open_position_at_end_is_marked_to_market(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    df = synth_ohlcv(80)
    export_dir = write_export(
        tmp_path,
        strategy=FIXTEST_ENTER_AT,
        params={"entry_ts": "2026-01-01T05:00:00+00:00", "direction": "long"},
        exit_mode="trail",
        exits={"trail_atr_mult": 50.0},  # never hit: position stays open
    )
    captured = capture_engine(monkeypatch)
    result = run_phase2_backtest(
        export_dir=export_dir, data_root=tmp_path / "data", ohlcv=df
    )
    summary = json.loads(result.report_path.read_text())

    entry = captured["fills"][0]
    last_close = float(df["close"].iloc[-1])
    expected_unrealized = (last_close - entry["avg_px"]) * entry["filled_qty"]
    assert result.open_positions_at_end == 1
    assert result.pnl_unrealized == pytest.approx(expected_unrealized, abs=1e-6)
    # Realized PnL is only the entry commission while the position is open.
    assert result.pnl_realized == pytest.approx(-result.commissions_total, abs=1e-6)
    assert result.pnl == pytest.approx(
        result.pnl_realized + result.pnl_unrealized - result.funding_cost
    )
    # Equity identity: mark-to-market PnL == equity - init cash (before funding).
    assert summary["pnl_before_funding"] == pytest.approx(
        captured["equity"] - 10_000.0, abs=1e-6
    )
    assert summary["pnl_basis"] == "mark_to_market_net_of_fees_and_funding"
    assert summary["trade_count"] == 1


def test_trade_count_counts_position_cycles_not_bracket_orders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    export_dir = write_export(
        tmp_path,
        metrics={
            "net_pnl": 12.5,
            "total_return_pct": 0.1,
            "sharpe": 0.1,
            "trade_count": 7,
        },
    )
    captured = capture_engine(monkeypatch)
    result = run_phase2_backtest(
        export_dir=export_dir, data_root=tmp_path / "data", ohlcv=synth_ohlcv(400)
    )
    summary = json.loads(result.report_path.read_text())
    assert result.trade_count > 0
    assert result.orders_count > result.trade_count  # bracket children are orders
    assert result.trade_count == captured["positions_report_rows"]
    assert summary["positions_count"] == summary["trade_count"] == result.trade_count
    parity = summary["parity"]
    assert parity["export_trade_count"] == 7
    assert parity["nautilus_trade_count"] == result.trade_count
    assert parity["trade_count_delta"] == result.trade_count - 7
    assert parity["pnl_delta"] == pytest.approx(result.pnl - 12.5)

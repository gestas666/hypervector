"""Shared SP500 profit-lock evidence input tests."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def test_lifecycle_loader_filters_exact_contract_and_archive_bounds(
    tmp_path: Path,
) -> None:
    from hypervector.research.sp500_profit_lock_evidence import (
        load_sp500_profit_lock_lifecycles,
        profit_lock_lifecycle_bounds,
        sp500_profit_lock_selection,
    )

    path = tmp_path / "trades.parquet"
    row = _row("development", "2026-06-08T08:01:00Z")
    rows = (
        row,
        _row("validation", "2026-06-08T08:02:00Z"),
        _row("development", "2026-06-08T07:59:00Z"),
        {**row, "strategy_id": "different_provider"},
    )
    pd.DataFrame(rows).to_parquet(path, index=False)
    start_ms = _ms("2026-06-08T08:00:00Z")
    end_ms = _ms("2026-06-08T09:00:00Z")

    lifecycles = load_sp500_profit_lock_lifecycles(
        path,
        start_ms=start_ms,
        end_ms=end_ms,
    )

    assert len(lifecycles) == 2
    assert profit_lock_lifecycle_bounds(lifecycles) == (
        _ms("2026-06-08T08:01:00Z"),
        _ms("2026-06-08T08:05:00Z"),
    )
    assert sp500_profit_lock_selection(lifecycles) == {
        "strategy_id": "hip3_breakout_pressure_sp500_spcx_bidirectional_v1",
        "symbol": "xyz:SP500",
        "friction": "stress",
        "phases": ["development", "validation"],
        "selected_lifecycles": 2,
    }


def _row(phase: str, entry_time: str) -> dict[str, object]:
    entry = pd.Timestamp(entry_time)
    exit_time = entry + pd.Timedelta(minutes=3)
    return {
        "strategy_id": "hip3_breakout_pressure_sp500_spcx_bidirectional_v1",
        "symbol": "xyz:SP500",
        "phase": phase,
        "friction": "stress",
        "direction": "long",
        "entry_time_utc": entry.isoformat(),
        "exit_time_utc": exit_time.isoformat(),
        "entry_price": 100.0,
        "exit_price": 100.2,
        "quantity": 1.0,
        "gross_pnl_usd": 0.2,
        "fees_usd": 0.09,
    }


def _ms(value: str) -> int:
    return int(pd.Timestamp(value).timestamp() * 1_000)

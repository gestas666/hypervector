"""Data-boundary tests for flow-exhaustion research inputs."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from hypervector.research.flow_exhaustion_data import (
    assemble_flow_exhaustion_rows,
    load_flow_exhaustion_minute_path,
)
from hypervector.research.low_tf_duckdb import LowTimeframeInputFrames


def _inputs() -> LowTimeframeInputFrames:
    opens = pd.date_range("2026-01-01", periods=2, freq="5min", tz=UTC)
    bars = pd.DataFrame(
        {
            "bar_open_at": opens,
            "open": [100.0, 101.0],
            "high": [101.0, 102.0],
            "low": [99.0, 100.0],
            "close": [100.5, 101.5],
            "volume": [10.0, 20.0],
            "trade_count": [2, 3],
        }
    )
    trades = pd.DataFrame(
        {
            "bar_open_at": opens,
            "buy_volume": [6.0, 8.0],
            "sell_volume": [4.0, 2.0],
            "final_60_buy_volume": [1.0, 2.0],
            "final_60_sell_volume": [2.0, 1.0],
        }
    )
    books = pd.DataFrame(
        {
            "bar_open_at": opens[:1],
            "last_book_at": opens[:1] + pd.Timedelta(minutes=5),
            "imbalance_5_last": [-0.2],
        }
    )
    return LowTimeframeInputFrames(
        bars,
        trades,
        books,
        datetime(2026, 1, 1, tzinfo=UTC),
        datetime(2026, 1, 2, tzinfo=UTC),
        1,
        0,
    )


def test_assembly_retains_missing_book_as_explicit_non_signal_row() -> None:
    """Threshold history must stay continuous when current L2 is absent."""
    rows = assemble_flow_exhaustion_rows(_inputs())

    assert len(rows) == 2
    assert rows.loc[0, "imbalance_5_last"] == pytest.approx(-0.2)
    assert pd.isna(rows.loc[1, "imbalance_5_last"])
    assert rows["final_60_buy_volume"].tolist() == [1.0, 2.0]


def test_minute_loader_attaches_only_exact_verified_hourly_funding(
    tmp_path: Path,
) -> None:
    """Funding must remain an explicit venue row rather than a forward fill."""
    database = tmp_path / "market.duckdb"
    connection = duckdb.connect(str(database))
    connection.execute(
        """
        CREATE TABLE canonical_trade_1m_bars AS
        SELECT * FROM (VALUES
          ('BTC', TIMESTAMPTZ '2026-01-01 00:00:00+00', 100., 101., 99., 100.5, 1., 1),
          ('BTC', TIMESTAMPTZ '2026-01-01 00:01:00+00', 100.5, 101., 100., 100.8, 1., 1)
        ) t(symbol, bar_open_at, open, high, low, close, volume, trade_count)
        """
    )
    connection.close()
    funding = tmp_path / "funding.parquet"
    pd.DataFrame(
        {
            "timestamp": [pd.Timestamp("2026-01-01T00:00:00Z")],
            "funding_rate": [0.0001],
            "source": ["hl_funding_history"],
        }
    ).to_parquet(funding, index=False)

    rows = load_flow_exhaustion_minute_path(
        database,
        "BTC",
        datetime(2026, 1, 1, tzinfo=UTC),
        datetime(2026, 1, 1, 0, 2, tzinfo=UTC),
        [funding],
    )

    assert rows["timestamp"].tolist() == list(
        pd.date_range("2026-01-01", periods=2, freq="1min", tz=UTC)
    )
    assert rows["funding_rate"].tolist() == [0.0001, 0.0]

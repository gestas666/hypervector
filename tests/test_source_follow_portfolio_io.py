"""Bounded archive streaming for production-matcher portfolio replay."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pandas as pd

from hypervector.data.hl_events import L2SnapshotEvent, PublicTradeEvent
from hypervector.data.research_database import ResearchDatabase
from hypervector.research import source_follow_portfolio_io as portfolio_io
from hypervector.research.source_follow_portfolio_io import merge_portfolio_events
from hypervector.research.source_follow_portfolio_models import (
    SourceReplayFunding,
    SourceReplayMark,
)


def test_merge_portfolio_events_uses_causal_priority() -> None:
    """Equal timestamps must apply mark, funding, book, then public trade."""
    level = [{"px": 100.0, "sz": 1.0, "n": 1}]
    books = [(1_000, level, level, "archive")]
    trades = [(1_000, 7, "buy", 100.0, 1.0, "archive")]
    prices = pd.DataFrame(
        {"ts_ms": [1_000], "mark_price": [100.0], "oracle_price": [100.0]}
    )
    funding = pd.DataFrame({"event_ts_ms": [1_000], "funding_rate": [0.001]})

    events = tuple(merge_portfolio_events("BTC", books, trades, prices, funding))

    assert isinstance(events[0], SourceReplayMark)
    assert isinstance(events[1], SourceReplayFunding)
    assert isinstance(events[2], L2SnapshotEvent)
    assert isinstance(events[3], PublicTradeEvent)


def test_live_portfolio_archive_preserves_recorded_receive_timestamps(
    tmp_path: Path,
) -> None:
    """Live replay must retain venue and local receipt chronology."""
    config_type = getattr(portfolio_io, "LiveSourcePortfolioArchiveConfig", None)
    archive_type = getattr(portfolio_io, "LiveSourcePortfolioArchive", None)
    assert config_type is not None
    assert archive_type is not None
    path = tmp_path / "research.duckdb"
    _live_database(path)
    start = datetime(2026, 7, 29, tzinfo=UTC)
    end = datetime(2026, 7, 29, 1, tzinfo=UTC)
    config = config_type(
        path,
        "BTC",
        start,
        end,
        maximum_book_gap_seconds=3_601.0,
        maximum_price_gap_seconds=3_601.0,
    )

    with archive_type(config) as archive:
        events = tuple(archive.events(start, end))

    books = [event for event in events if isinstance(event, L2SnapshotEvent)]
    trades = [event for event in events if isinstance(event, PublicTradeEvent)]
    assert [event.received_ts_ns for event in books] == [
        1_785_283_200_700_000_000,
        1_785_286_799_700_000_000,
    ]
    assert trades[0].received_ts_ns == 1_785_283_200_900_000_000


def _live_database(path: Path) -> None:
    ResearchDatabase(path)
    with duckdb.connect(str(path)) as connection:
        connection.execute(
            """
            INSERT INTO live_book_snapshots VALUES
                ('BTC', 1785283200500, 1785283200700000000,
                 [struct_pack(n := 1, px := 65000.0, sz := 2.0)],
                 [struct_pack(n := 1, px := 65001.0, sz := 3.0)],
                 'hl_ws_l2', 'book'),
                ('BTC', 1785286799500, 1785286799700000000,
                 [struct_pack(n := 1, px := 65010.0, sz := 4.0)],
                 [struct_pack(n := 1, px := 65011.0, sz := 1.0)],
                 'hl_ws_l2', 'book')
            """
        )
        connection.execute(
            """
            INSERT INTO live_public_trades VALUES
                ('BTC', 'buy', 65001.0, 0.25, '0xabc', 1785283200600,
                 1785283200900000000, 123, 'buyer', 'seller',
                 'hl_ws_trades', 'trade')
            """
        )
        connection.execute(
            """
            INSERT INTO live_asset_contexts VALUES
                ('BTC', 1785283200000, 1785283200000000000,
                 65000.5, 65000.0, 0.00001, 1000.0, 65000.5,
                 'exchange', 'hl_ws_context', 'context'),
                ('BTC', 1785286799500, 1785286799500000000,
                 65010.5, 65010.0, 0.00003, 1000.0, 65010.5,
                 'exchange', 'hl_ws_context', 'context')
            """
        )

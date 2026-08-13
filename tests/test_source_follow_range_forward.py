"""Forward-only RANGE path audit contracts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import pytest

from hypervector.research.source_follow_range_forward import (
    audit_range_forward_paths,
    extract_range_decisions,
)


def _stamp(minutes: int) -> datetime:
    return datetime(2026, 7, 31, tzinfo=UTC) + timedelta(minutes=minutes)


def _ledger_row(
    sequence: int,
    *,
    regime: str = "RANGE",
    feed_minute: int = 0,
) -> dict[str, object]:
    feed = _stamp(feed_minute)
    return {
        "run_id": "run-1",
        "sequence": sequence,
        "event_type": "regime_decision",
        "payload": {
            "feed_ts": feed.isoformat(),
            "available_at_utc": (feed + timedelta(minutes=5)).isoformat(),
            "primary_regime": regime,
            "reference_price": 100.0,
        },
    }


def _database(path: Path, *, with_gap: bool = False) -> None:
    with duckdb.connect(str(path)) as connection:
        connection.execute(
            """
            CREATE TABLE live_public_trades (
                symbol VARCHAR,
                exchange_ts_ms BIGINT,
                received_ts_ns BIGINT,
                trade_id BIGINT,
                price DOUBLE
            );
            CREATE VIEW replay_live_public_trades AS
            SELECT * FROM live_public_trades;
            CREATE TABLE live_stream_gaps (
                symbol VARCHAR,
                previous_exchange_ts_ms BIGINT,
                next_exchange_ts_ms BIGINT
            );
            """
        )
        prices = ((5, 100.0), (7, 100.3), (9, 99.8), (11, 100.1))
        rows = [
            (
                "BTC",
                int(_stamp(minute).timestamp() * 1_000),
                int(_stamp(minute).timestamp() * 1_000_000_000),
                index,
                price,
            )
            for index, (minute, price) in enumerate(prices, start=1)
        ]
        connection.executemany(
            "INSERT INTO live_public_trades VALUES (?, ?, ?, ?, ?)", rows
        )
        if with_gap:
            connection.execute(
                "INSERT INTO live_stream_gaps VALUES (?, ?, ?)",
                [
                    "BTC",
                    int(_stamp(6).timestamp() * 1_000),
                    int(_stamp(8).timestamp() * 1_000),
                ],
            )


def test_extract_range_decisions_is_run_scoped_and_range_only() -> None:
    rows = [
        _ledger_row(1),
        _ledger_row(2, regime="TREND_DOWN"),
        {**_ledger_row(3), "run_id": "other"},
    ]

    decisions = extract_range_decisions(rows, run_id="run-1")

    assert len(decisions) == 1
    assert decisions[0].sequence == 1
    assert decisions[0].available_at_utc == _stamp(5)
    assert decisions[0].reference_price == 100.0


def test_range_forward_audit_orders_targets_and_censors_future(
    tmp_path: Path,
) -> None:
    database = tmp_path / "market.duckdb"
    _database(database)
    decisions = extract_range_decisions([_ledger_row(1)], run_id="run-1")

    report = audit_range_forward_paths(
        database,
        decisions,
        symbol="BTC",
        target_price_fraction=0.002,
        horizons_minutes=(5, 10),
    )

    five = report["paths"][0]["horizons"]["5"]
    assert five["complete"] is True
    assert five["quality_usable"] is True
    assert five["long_target_hit"] is True
    assert five["short_target_hit"] is True
    assert five["first_target_direction"] == "long"
    assert five["maximum_up_bps"] == pytest.approx(30.0)
    assert five["maximum_down_bps"] == pytest.approx(20.0)
    assert report["horizons"]["5"]["usable_rows"] == 1
    assert report["horizons"]["10"]["censored_rows"] == 1


def test_range_forward_audit_marks_explicit_stream_gap_unusable(
    tmp_path: Path,
) -> None:
    database = tmp_path / "market.duckdb"
    _database(database, with_gap=True)
    decisions = extract_range_decisions([_ledger_row(1)], run_id="run-1")

    report = audit_range_forward_paths(
        database,
        decisions,
        symbol="BTC",
        target_price_fraction=0.002,
        horizons_minutes=(5,),
    )

    five = report["paths"][0]["horizons"]["5"]
    assert five["complete"] is True
    assert five["quality_usable"] is False
    assert five["explicit_stream_gaps"] == 1
    assert report["horizons"]["5"]["gap_rows"] == 1


def test_range_forward_excursions_do_not_become_negative(tmp_path: Path) -> None:
    database = tmp_path / "market.duckdb"
    _database(database)
    with duckdb.connect(str(database)) as connection:
        connection.execute(
            "UPDATE live_public_trades SET price = price - 1.0 WHERE trade_id <= 3"
        )
    decisions = extract_range_decisions([_ledger_row(1)], run_id="run-1")

    report = audit_range_forward_paths(
        database,
        decisions,
        symbol="BTC",
        target_price_fraction=0.002,
        horizons_minutes=(5,),
    )

    five = report["paths"][0]["horizons"]["5"]
    assert five["maximum_up_bps"] == 0.0
    assert five["maximum_down_bps"] == pytest.approx(120.0)


def test_range_forward_audit_reports_contiguous_episode_count(tmp_path: Path) -> None:
    database = tmp_path / "market.duckdb"
    _database(database)
    rows = [
        _ledger_row(1, feed_minute=0),
        _ledger_row(2, feed_minute=5),
        _ledger_row(3, feed_minute=15),
    ]
    decisions = extract_range_decisions(rows, run_id="run-1")

    report = audit_range_forward_paths(
        database,
        decisions,
        symbol="BTC",
        target_price_fraction=0.002,
        horizons_minutes=(5,),
    )

    assert report["range_episodes"] == {
        "count": 2,
        "rows": [
            {
                "episode": 1,
                "start_at_utc": _stamp(5).isoformat(),
                "end_at_utc": _stamp(10).isoformat(),
                "decision_rows": 2,
            },
            {
                "episode": 2,
                "start_at_utc": _stamp(20).isoformat(),
                "end_at_utc": _stamp(20).isoformat(),
                "decision_rows": 1,
            },
        ],
    }


def test_range_forward_audit_rejects_duplicate_horizons(tmp_path: Path) -> None:
    database = tmp_path / "market.duckdb"
    _database(database)
    decisions = extract_range_decisions([_ledger_row(1)], run_id="run-1")

    with pytest.raises(ValueError, match="unique"):
        audit_range_forward_paths(
            database,
            decisions,
            symbol="BTC",
            target_price_fraction=0.002,
            horizons_minutes=(5, 5),
        )

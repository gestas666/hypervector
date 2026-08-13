"""Independent public-trade and L2 checks for source-follow live audits."""

from __future__ import annotations

from pathlib import Path

import duckdb

from hypervector.research.source_follow_live_audit import audit_source_follow_live_run
from source_follow_live_audit_fixtures import candle
from source_follow_live_audit_fixtures import create_replay_schema
from source_follow_live_audit_fixtures import identity


def test_audit_retains_exact_mismatched_and_uncovered_trade_bars(
    tmp_path: Path,
) -> None:
    """Missing tape is uncovered while measured disagreement remains explicit."""
    database = tmp_path / "market.duckdb"
    with duckdb.connect(str(database)) as connection:
        create_replay_schema(connection)
        connection.executemany(
            "INSERT INTO replay_live_public_trades VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    "BTC",
                    "buy",
                    100.0,
                    5.0,
                    1_785_528_000_000,
                    1_785_528_000_100_000_000,
                    1,
                ),
                (
                    "BTC",
                    "buy",
                    102.0,
                    3.0,
                    1_785_528_120_000,
                    1_785_528_120_100_000_000,
                    2,
                ),
                (
                    "BTC",
                    "sell",
                    101.0,
                    4.0,
                    1_785_528_299_000,
                    1_785_528_299_100_000_000,
                    3,
                ),
                (
                    "BTC",
                    "buy",
                    100.0,
                    2.0,
                    1_785_528_300_000,
                    1_785_528_300_100_000_000,
                    4,
                ),
                (
                    "BTC",
                    "buy",
                    103.0,
                    3.0,
                    1_785_528_420_000,
                    1_785_528_420_100_000_000,
                    5,
                ),
                (
                    "BTC",
                    "sell",
                    98.0,
                    1.0,
                    1_785_528_480_000,
                    1_785_528_480_100_000_000,
                    6,
                ),
                (
                    "BTC",
                    "sell",
                    100.5,
                    4.0,
                    1_785_528_599_000,
                    1_785_528_599_100_000_000,
                    7,
                ),
            ],
        )
    exact = candle("run-a", 2)
    exact_payload = exact["payload"]
    assert isinstance(exact_payload, dict)
    exact_payload["low"] = 100.0
    mismatch = candle("run-a", 3, feed_ts="2026-07-31T20:05:00+00:00")
    uncovered = candle("run-a", 4, feed_ts="2026-07-31T20:10:00+00:00")

    report = audit_source_follow_live_run(
        [identity("run-a", 1, "source-bidirectional"), exact, mismatch, uncovered],
        database_path=database,
    )
    parity = report["market_parity"]

    assert parity["ledger_bars"] == 3
    assert parity["trade_bars_covered"] == 2
    assert parity["trade_bars_uncovered"] == 1
    assert parity["exact_ohlcv_rows"] == 1
    assert parity["mismatched_rows"] == 1
    assert parity["venue_equivalent_ohlcv_rows"] == 1
    assert parity["boundary_ambiguous_rows"] == 0
    assert parity["non_equivalent_rows"] == 1
    assert parity["by_event_type"] == {
        "regime_history": {
            "ledger_bars": 3,
            "trade_bars_covered": 2,
            "trade_bars_uncovered": 1,
            "exact_ohlcv_rows": 1,
            "mismatched_rows": 1,
            "venue_equivalent_ohlcv_rows": 1,
            "boundary_ambiguous_rows": 0,
            "non_equivalent_rows": 1,
        }
    }
    assert parity["uncovered"] == ["2026-07-31T20:10:00+00:00"]
    assert parity["maximum_absolute_difference"] == {
        "open": 0.0,
        "high": 1.0,
        "low": 1.0,
        "close": 0.5,
        "volume": 2.0,
    }
    assert parity["mismatches"][0]["feed_ts"] == "2026-07-31T20:05:00+00:00"


def test_audit_accepts_rest_boundary_prices_present_in_same_timestamp_trades(
    tmp_path: Path,
) -> None:
    """An unknowable same-millisecond order is ambiguous rather than corrupt."""
    database = tmp_path / "market.duckdb"
    start_ms = 1_785_528_000_000
    with duckdb.connect(str(database)) as connection:
        create_replay_schema(connection)
        connection.executemany(
            "INSERT INTO replay_live_public_trades VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                ("BTC", "buy", 100.0, 1.0, start_ms, start_ms * 1_000_000, 1),
                ("BTC", "buy", 102.0, 1.0, start_ms, start_ms * 1_000_000, 2),
                (
                    "BTC",
                    "buy",
                    103.0,
                    1.0,
                    start_ms + 100_000,
                    (start_ms + 100_000) * 1_000_000,
                    3,
                ),
                (
                    "BTC",
                    "sell",
                    99.0,
                    1.0,
                    start_ms + 299_000,
                    (start_ms + 299_000) * 1_000_000,
                    4,
                ),
                (
                    "BTC",
                    "sell",
                    101.0,
                    1.0,
                    start_ms + 299_000,
                    (start_ms + 299_000) * 1_000_000,
                    5,
                ),
            ],
        )
    backend = candle("run-a", 2, event_type="regime_decision")
    payload = backend["payload"]
    assert isinstance(payload, dict)
    payload.update(
        {"open": 102.0, "high": 103.0, "low": 99.0, "close": 99.0, "volume": 5.0}
    )

    parity = audit_source_follow_live_run(
        [identity("run-a", 1, "source-bidirectional"), backend],
        database_path=database,
    )["market_parity"]

    assert parity["exact_ohlcv_rows"] == 0
    assert parity["mismatched_rows"] == 1
    assert parity["venue_equivalent_ohlcv_rows"] == 1
    assert parity["boundary_ambiguous_rows"] == 1
    assert parity["non_equivalent_rows"] == 0
    assert parity["mismatches"][0]["venue_equivalent_ohlcv"] is True
    assert parity["mismatches"][0]["boundary_ambiguous"] is True


def test_audit_distinguishes_continuous_l2_from_partial_or_invalid_capture(
    tmp_path: Path,
) -> None:
    """Recorder continuity is measured per bar and never inferred from existence."""
    database = tmp_path / "market.duckdb"
    first_start_ms = 1_785_528_000_000
    second_start_ms = first_start_ms + 300_000
    complete = [
        (
            "BTC",
            first_start_ms + second * 1_000,
            (first_start_ms + second * 1_000) * 1_000_000 + 100_000_000,
        )
        for second in range(1, 300, 5)
    ]
    partial = [
        ("BTC", second_start_ms + 120_000, (second_start_ms + 120_000) * 1_000_000 - 1),
        (
            "BTC",
            second_start_ms + 299_000,
            (second_start_ms + 299_000) * 1_000_000 + 100_000_000,
        ),
    ]
    with duckdb.connect(str(database)) as connection:
        create_replay_schema(connection)
        connection.executemany(
            "INSERT INTO replay_live_book_snapshots VALUES (?, ?, ?)",
            complete + partial,
        )
        connection.execute(
            "INSERT INTO live_stream_gaps VALUES (?, ?, ?, ?, ?, ?)",
            [
                "BTC",
                "trades",
                (second_start_ms + 180_000) * 1_000_000,
                "sequence_gap",
                second_start_ms + 179_000,
                second_start_ms + 181_000,
            ],
        )
    rows = [
        identity("run-a", 1, "source-bidirectional"),
        candle("run-a", 2),
        candle("run-a", 3, feed_ts="2026-07-31T20:05:00+00:00"),
    ]

    quality = audit_source_follow_live_run(rows, database_path=database)["l2_quality"]

    assert quality["diagnostic_gap_threshold_seconds"] == 6.0
    assert quality["bars"] == 2
    assert quality["continuous_l2_bars"] == 1
    assert quality["quality_usable_bars"] == 1
    assert quality["negative_receive_lag_rows"] == 1
    assert quality["explicit_stream_gaps"] == 1
    assert quality["by_event_type"] == {
        "regime_history": {
            "bars": 2,
            "continuous_l2_bars": 1,
            "quality_usable_bars": 1,
            "negative_receive_lag_rows": 1,
            "explicit_stream_gaps": 1,
        }
    }
    assert quality["by_bar"][0]["continuous_l2"] is True
    assert quality["by_bar"][0]["quality_usable"] is True
    assert quality["by_bar"][1]["continuous_l2"] is False
    assert quality["by_bar"][1]["quality_usable"] is False
    assert quality["by_bar"][1]["explicit_stream_gaps"] == 1

"""Tests for the immutable low-timeframe L2 challenger command."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from importlib.util import module_from_spec, spec_from_file_location
import json
import math
from pathlib import Path
import sys
from types import ModuleType

import duckdb
import pytest


_SCRIPT = Path("scripts/low_tf_l2_directional_challenger.py")


def _module() -> ModuleType:
    spec = spec_from_file_location("low_tf_l2_directional_challenger", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load challenger script: {_SCRIPT}")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _create_database(path: Path, bars: int = 280) -> None:
    with duckdb.connect(str(path)) as connection:
        _create_tables(connection)
        _insert_fixture_rows(connection, bars)


def _create_tables(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        CREATE TABLE canonical_trade_5m_bars (
            symbol VARCHAR, bar_open_at TIMESTAMPTZ, open DOUBLE,
            high DOUBLE, low DOUBLE, close DOUBLE, volume DOUBLE,
            trade_count BIGINT
        );
        CREATE TABLE replay_public_trades (
            symbol VARCHAR, trade_id BIGINT, ts_exchange_ms BIGINT,
            ts_utc TIMESTAMPTZ, aggressor_side VARCHAR, price DOUBLE,
            size DOUBLE
        );
        CREATE TABLE replay_book_snapshots (
            symbol VARCHAR, ts_exchange_ms BIGINT, ts_utc TIMESTAMPTZ,
            bid_depth_10 DOUBLE, ask_depth_10 DOUBLE,
            imbalance_5 DOUBLE, imbalance_10 DOUBLE,
            mid_price DOUBLE, micro_price DOUBLE, spread_bps DOUBLE
        );
        """
    )


def _insert_fixture_rows(
    connection: duckdb.DuckDBPyConnection,
    count: int,
) -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    bar_rows: list[tuple[object, ...]] = []
    trade_rows: list[tuple[object, ...]] = []
    book_rows: list[tuple[object, ...]] = []
    for index in range(count):
        stamp = start + timedelta(minutes=5 * index)
        close = 100.0 + 1.7 * math.sin(index / 6.0)
        open_price = 100.0 + 1.7 * math.sin((index - 1) / 6.0)
        high = max(open_price, close) + 0.04
        low = min(open_price, close) - 0.04
        volume = 10.0 + index % 7
        trade_count = 2 + index % 3
        bar_rows.append(
            ("BTC", stamp, open_price, high, low, close, volume, trade_count)
        )
        _append_trades(trade_rows, stamp, index, close, trade_count)
        _append_books(book_rows, stamp, index, close)
    connection.executemany(
        "INSERT INTO canonical_trade_5m_bars VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        bar_rows,
    )
    connection.executemany(
        "INSERT INTO replay_public_trades VALUES (?, ?, ?, ?, ?, ?, ?)",
        trade_rows,
    )
    connection.executemany(
        "INSERT INTO replay_book_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        book_rows,
    )


def _append_trades(
    rows: list[tuple[object, ...]],
    stamp: datetime,
    index: int,
    price: float,
    count: int,
) -> None:
    for ordinal in range(count):
        observed = stamp + timedelta(minutes=1 + ordinal)
        side = "buy" if (index + ordinal) % 3 else "sell"
        rows.append(
            (
                "BTC",
                index * 10 + ordinal,
                int(observed.timestamp() * 1_000),
                observed,
                side,
                price,
                1.0 + (index + ordinal) % 5,
            )
        )


def _append_books(
    rows: list[tuple[object, ...]],
    stamp: datetime,
    index: int,
    price: float,
) -> None:
    imbalance = 0.7 * math.sin(index / 5.0)
    for ordinal, seconds in enumerate((240, 299)):
        observed = stamp + timedelta(seconds=seconds)
        shifted = imbalance + ordinal * 0.02
        rows.append(
            (
                "BTC",
                int(observed.timestamp() * 1_000),
                observed,
                100.0 + index % 11,
                95.0 + index % 13,
                shifted,
                shifted * 0.9,
                price,
                price * (1.0 + shifted / 100_000.0),
                0.5 + index % 4 / 10.0,
            )
        )


def _argv(database: Path, output: Path) -> list[str]:
    return [
        "--symbol",
        "BTC",
        "--database",
        str(database),
        "--start",
        "2026-01-01T04:00:00Z",
        "--end",
        "2026-01-01T20:00:00Z",
        "--segment",
        "development",
        "--out",
        str(output),
    ]


def test_parser_requires_the_frozen_data_identity_arguments() -> None:
    """Symbol, database, window, segment, and output must be explicit."""
    module = _module()

    with pytest.raises(SystemExit):
        module._parser().parse_args([])

    args = module._parser().parse_args(
        _argv(Path("market.duckdb"), Path("report.json"))
    )
    assert args.symbol == "BTC"
    assert args.segment == "development"


def test_command_rejects_an_incomplete_database(tmp_path: Path) -> None:
    """Missing market authorities must fail before producing an artifact."""
    database = tmp_path / "market.duckdb"
    duckdb.connect(str(database)).close()

    with pytest.raises(ValueError, match="missing required tables"):
        _module().main(_argv(database, tmp_path / "report.json"))


def test_command_refuses_to_overwrite_immutable_output(tmp_path: Path) -> None:
    """An existing report or sidecar must stop the command."""
    output = tmp_path / "report.json"
    output.write_text("existing", encoding="utf-8")

    with pytest.raises(FileExistsError, match="challenger output exists"):
        _module().main(_argv(tmp_path / "missing.duckdb", output))


def test_command_publishes_all_report_only_trials(tmp_path: Path) -> None:
    """The immutable report must retain every model/threshold result."""
    database = tmp_path / "market.duckdb"
    output = tmp_path / "report.json"
    _create_database(database)

    assert _module().main(_argv(database, output)) == 0

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["report_only"] is True
    assert report["execution_authority"] == "none"
    assert report["place_attempted"] is False
    assert report["segment"] == "development"
    assert len(report["trials"]) == 12
    assert {row["candidate"] for row in report["trials"]} == {
        "base_rate",
        "logistic_l2",
        "lightgbm_l2",
    }
    assert {row["threshold"] for row in report["trials"]} == {
        0.55,
        0.60,
        0.65,
        0.70,
    }
    assert report["input_identity"]["bars_sha256"]
    assert report["input_identity"]["trades_sha256"]
    assert report["input_identity"]["books_sha256"]
    assert output.with_suffix(".parquet").is_file()


def test_command_surface_cannot_arm_execution() -> None:
    """The research command must expose no wallet or live-order vocabulary."""
    source = _SCRIPT.read_text(encoding="utf-8")
    assert "i-accept-live-risk" not in source
    assert "private_key" not in source
    assert "submit_order" not in source

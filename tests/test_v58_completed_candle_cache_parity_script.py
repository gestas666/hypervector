"""Tests for the bounded V58 candle-cache parity command."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import duckdb
import pytest

_SCRIPT = Path("scripts/v58_completed_candle_cache_parity.py")
_START_MS = 1_800_000
_PROFILE_ID = "multi_asset_growth_first_5000_eight_asset_incremental_v58"
_SYMBOLS = (
    "BTC",
    "ETH",
    "SOL",
    "HYPE",
    "xyz:SP500",
    "xyz:SPCX",
    "xyz:SNDK",
    "xyz:BRENTOIL",
)


def _load_module() -> ModuleType:
    """Load the wished-for script without a subprocess."""
    if not _SCRIPT.is_file():
        pytest.fail("V58 completed-candle cache parity script is not implemented")
    spec = importlib.util.spec_from_file_location(
        "v58_candle_cache_parity_script", _SCRIPT
    )
    if spec is None or spec.loader is None:
        pytest.fail("V58 completed-candle cache parity script cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _row(*, live: bool, run_id: str) -> dict[str, object]:
    """Return one complete all-symbol market-candle row."""
    bars = {
        symbol: [
            {
                "timestamp_ms": _START_MS,
                "open": 100.0 + index,
                "high": 101.0 + index,
                "low": 99.0 + index,
                "close": 100.5 + index,
                "volume": 10.0 + index,
            }
        ]
        for index, symbol in enumerate(_SYMBOLS)
    }
    return {
        "sequence": 7,
        "observed_at_utc": "1970-01-01T00:32:15+00:00",
        "execution_mode": "live" if live else "observe",
        "live_armed": live,
        "execution_authority": "hyperliquid_mainnet" if live else "none",
        "profile_id": _PROFILE_ID,
        "profile_fingerprint": "live-fingerprint" if live else "observer-fingerprint",
        "run_fingerprint": "live-run-fingerprint"
        if live
        else "observer-run-fingerprint",
        "run_id": run_id,
        "event_type": "market_candles",
        "payload": {"timeframe": "1m", "bars": bars},
    }


def _database(path: Path, rows: list[dict[str, object]]) -> None:
    """Create the minimum real DuckDB source used by the command."""
    connection = duckdb.connect(str(path))
    connection.execute(
        """
        CREATE TABLE cohort_live_events (
            sequence BIGINT,
            observed_at_utc TIMESTAMPTZ,
            execution_mode VARCHAR,
            live_armed BOOLEAN,
            execution_authority VARCHAR,
            profile_id VARCHAR,
            profile_fingerprint VARCHAR,
            run_fingerprint VARCHAR,
            run_id VARCHAR,
            event_type VARCHAR,
            payload JSON
        )
        """
    )
    for row in rows:
        connection.execute(
            "INSERT INTO cohort_live_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                row["sequence"],
                row["observed_at_utc"],
                row["execution_mode"],
                row["live_armed"],
                row["execution_authority"],
                row["profile_id"],
                row["profile_fingerprint"],
                row["run_fingerprint"],
                row["run_id"],
                row["event_type"],
                json.dumps(row["payload"]),
            ],
        )
    connection.close()


def _args(tmp_path: Path, database: Path, observer: Path) -> argparse.Namespace:
    """Return deterministic command arguments."""
    return argparse.Namespace(
        research_database=database,
        live_run_id="live-run",
        observer_ledger=observer,
        observer_run_id="observer-run",
        prospective_start_ms=_START_MS,
        minimum_contiguous_minutes=1,
        maximum_database_age_seconds=180.0,
        out=tmp_path / "report.json",
    )


def test_command_queries_selected_run_and_publishes_authenticated_report(
    tmp_path: Path,
) -> None:
    """The command must bind exact query and observer-prefix evidence."""
    database = tmp_path / "market.duckdb"
    _database(
        database,
        [_row(live=True, run_id="other-run"), _row(live=True, run_id="live-run")],
    )
    observer = tmp_path / "observer.jsonl"
    observer.write_text(json.dumps(_row(live=False, run_id="observer-run")) + "\n")
    args = _args(tmp_path, database, observer)

    result = _load_module().run(
        args,
        now=datetime(1970, 1, 1, 0, 33, tzinfo=UTC),
    )

    report = json.loads(args.out.read_text())
    assert result == 0
    assert report["coverage"]["gate_status"] == "satisfied"
    assert report["comparison"]["exact_ohlcv_rows"] == 8
    assert report["evidence"]["live_database_query"]["rows"] == 1
    assert len(report["evidence"]["live_database_query"]["sha256"]) == 64
    assert report["evidence"]["observer_ledger"]["rows"] == 1
    assert len(report["evidence"]["observer_ledger"]["sha256"]) == 64
    assert report["contract"]["execution_authority"] == "none"


def test_command_rejects_stale_live_database_evidence(tmp_path: Path) -> None:
    """A lagging research import must not produce current-looking parity."""
    database = tmp_path / "market.duckdb"
    _database(database, [_row(live=True, run_id="live-run")])
    observer = tmp_path / "observer.jsonl"
    observer.write_text(json.dumps(_row(live=False, run_id="observer-run")) + "\n")
    args = _args(tmp_path, database, observer)

    with pytest.raises(ValueError, match="database query is stale"):
        _load_module().run(
            args,
            now=datetime(1970, 1, 1, 0, 40, tzinfo=UTC),
        )

    assert not args.out.exists()

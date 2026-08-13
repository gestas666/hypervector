"""Operator contract for the report-only live RANGE forward audit."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import duckdb
import pytest


_SCRIPT = Path("scripts/hypervelocity_source_range_forward_audit.py")


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("source_range_forward", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load RANGE audit script: {_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _time(minutes: int) -> datetime:
    return datetime(2026, 7, 31, tzinfo=UTC) + timedelta(minutes=minutes)


def _write_ledger(path: Path) -> None:
    row = {
        "run_id": "run-a",
        "sequence": 1,
        "event_type": "regime_decision",
        "payload": {
            "feed_ts": _time(0).isoformat(),
            "available_at_utc": _time(5).isoformat(),
            "primary_regime": "RANGE",
            "reference_price": 100.0,
        },
    }
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")


def _write_database(path: Path) -> None:
    timestamp = int(_time(11).timestamp() * 1_000)
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
        connection.execute(
            "INSERT INTO live_public_trades VALUES (?, ?, ?, ?, ?)",
            ["BTC", timestamp, timestamp * 1_000_000, 1, 100.3],
        )


def test_script_contract_requires_explicit_live_evidence() -> None:
    module = _load_script()
    args = module._parser().parse_args(
        [
            "--decisions",
            "decisions.jsonl",
            "--database",
            "market.duckdb",
            "--run-id",
            "run-a",
            "--symbol",
            "BTC",
            "--target-price-fraction",
            "0.002",
            "--horizon-minutes",
            "5",
            "--out",
            "audit.json",
        ]
    )

    assert args.run_id == "run-a"
    assert args.target_price_fraction == 0.002
    assert args.horizon_minutes == [5]
    source = _SCRIPT.read_text(encoding="utf-8")
    assert "create_armed" not in source
    assert "private_key" not in source
    assert "submit_entry" not in source


def test_script_publishes_immutable_report_only_evidence(tmp_path: Path) -> None:
    module = _load_script()
    decisions = tmp_path / "decisions.jsonl"
    database = tmp_path / "market.duckdb"
    output = tmp_path / "audit.json"
    _write_ledger(decisions)
    _write_database(database)
    argv = [
        "--decisions",
        str(decisions),
        "--database",
        str(database),
        "--run-id",
        "run-a",
        "--symbol",
        "BTC",
        "--target-price-fraction",
        "0.002",
        "--horizon-minutes",
        "5",
        "--out",
        str(output),
    ]

    assert module.main(argv) == 0

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["report_only"] is True
    assert report["execution_authority"] == "none"
    assert report["runtime_strategy_changed"] is False
    assert report["run_id"] == "run-a"
    assert report["decision_rows"] == 1
    assert report["evidence"]["decisions"]["sha256"]
    assert report["evidence"]["database"]["sha256"]
    with pytest.raises(FileExistsError, match="immutable RANGE audit output exists"):
        module.main(argv)

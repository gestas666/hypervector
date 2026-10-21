"""DuckDB ingestion tests for the append-only live cohort journal."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from hypervector.cli import main
from hypervector.data import cohort_research_database as cohort_database
from hypervector.data.research_database import ResearchDatabase
from hypervector.research import cohort_live_portfolio_archive as archive_module

load_cohort_live_portfolio_archive = archive_module.load_cohort_live_portfolio_archive


def test_cohort_ledgers_import_incrementally_and_project_fills(tmp_path: Path) -> None:
    """Portfolio and asset ledgers become queryable without duplicate rows."""
    root = tmp_path / "live" / "bidirectional_cohort"
    _write(root / "decisions.jsonl", [_event(1, "heartbeat", {})])
    _write(
        root / "btc.jsonl",
        [
            _event(1, "session_start", {"state": "PREFLIGHT"}),
            _event(
                2,
                "fill",
                {
                    "oid": 11,
                    "trade_id": 22,
                    "venue_timestamp_ms": 1_000,
                    "price": 100.0,
                    "size": 0.5,
                    "side": "B",
                    "direction": "Open Long",
                    "closed_pnl_usd": 0.0,
                    "fee_usd": 0.02,
                },
            ),
        ],
    )
    database_path = tmp_path / "research" / "market.duckdb"
    database = ResearchDatabase(database_path)

    first = database.ingest_cohort_live_ledger(root)
    repeated = database.ingest_cohort_live_ledger(root)
    with (root / "btc.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_event(3, "heartbeat", {})) + "\n")
    appended = database.ingest_cohort_live_ledger(root)

    assert first.to_dict() == {
        "source_files": 2,
        "updated_files": 2,
        "scanned_events": 3,
        "imported_events": 3,
        "skipped_events": 0,
        "ignored_observe_events": 0,
    }
    assert repeated.imported_events == 0
    assert appended.imported_events == 1
    assert database.cohort_live_summary() == {
        "source_files": 2,
        "events": 4,
        "fills": 1,
        "closed_fills": 0,
        "attributed_fills": 0,
        "close_orders": 0,
        "runs": 1,
    }
    with duckdb.connect(str(database_path), read_only=True) as connection:
        fill = connection.execute(
            "SELECT symbol, direction, price, fee_usd FROM cohort_live_fills"
        ).fetchone()
    assert fill == ("BTC", "Open Long", 100.0, 0.02)


def test_fill_identity_ignores_non_fill_appends_and_changes_on_fill(
    tmp_path: Path,
) -> None:
    """The archive cache key changes exactly when append-only fill evidence changes."""
    root = tmp_path / "cohort"
    ledger = root / "btc.jsonl"
    _write(
        ledger,
        [
            _event(1, "heartbeat", {}),
            _event(2, "fill", {"trade_id": 10}),
        ],
    )
    database_path = tmp_path / "market.duckdb"
    database = ResearchDatabase(database_path)
    database.ingest_cohort_live_ledger(root)

    first = archive_module.cohort_live_fill_identity(database_path)
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_event(3, "heartbeat", {})) + "\n")
    database.ingest_cohort_live_ledger(root)
    after_heartbeat = archive_module.cohort_live_fill_identity(database_path)
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_event(4, "fill", {"trade_id": 11})) + "\n")
    database.ingest_cohort_live_ledger(root)
    after_fill = archive_module.cohort_live_fill_identity(database_path)

    assert first.to_dict()["fill_events"] == 1
    assert after_heartbeat == first
    assert after_fill.fill_events == 2
    assert after_fill.sha256 != first.sha256


def test_incremental_import_reads_only_the_new_complete_suffix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A growing live ledger must not be loaded into RAM from byte zero."""
    root = tmp_path / "cohort"
    ledger = root / "decisions.jsonl"
    _write(ledger, [_event(index, "heartbeat", {}) for index in range(1, 101)])
    database = ResearchDatabase(tmp_path / "market.duckdb")
    database.ingest_cohort_live_ledger(root)
    prior_size = ledger.stat().st_size
    appended = json.dumps(_event(101, "heartbeat", {})) + "\n"
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write(appended)
    reads: list[tuple[int, int]] = []
    original = cohort_database._read_range

    def observed_read(path: Path, start: int, end: int) -> bytes:
        reads.append((start, end))
        return original(path, start, end)

    monkeypatch.setattr(cohort_database, "_read_range", observed_read)

    report = database.ingest_cohort_live_ledger(root)

    assert report.imported_events == 1
    assert reads == [(prior_size, prior_size + len(appended.encode()))]


def test_cohort_import_rejects_non_append_change_atomically(tmp_path: Path) -> None:
    """Changing an imported prefix cannot rewrite historical live evidence."""
    root = tmp_path / "cohort"
    ledger = root / "decisions.jsonl"
    _write(ledger, [_event(1, "heartbeat", {"status": "running"})])
    database = ResearchDatabase(tmp_path / "market.duckdb")
    database.ingest_cohort_live_ledger(root)
    _write(ledger, [_event(1, "heartbeat", {"status": "changed"})])

    with pytest.raises(ValueError, match="append-only prefix changed"):
        database.ingest_cohort_live_ledger(root)

    assert database.cohort_live_summary()["events"] == 1


def test_cohort_import_rejects_non_live_rows(tmp_path: Path) -> None:
    """The live evidence table cannot silently absorb shadow events."""
    root = tmp_path / "cohort"
    row = _event(1, "heartbeat", {})
    row["execution_mode"] = "shadow"
    _write(root / "decisions.jsonl", [row])
    database = ResearchDatabase(tmp_path / "market.duckdb")

    with pytest.raises(ValueError, match="execution_mode must be live"):
        database.ingest_cohort_live_ledger(root)

    assert database.cohort_live_summary()["events"] == 0


def test_cohort_import_skips_execution_incapable_observe_rows(
    tmp_path: Path,
) -> None:
    """Observe-only telemetry cannot block later live journal ingestion."""
    root = tmp_path / "cohort"
    observe = _event(1, "heartbeat", {})
    observe.update(
        execution_mode="observe",
        effective_mode="OBSERVE ONLY",
        live_armed=False,
        execution_authority="none",
        run_id="observe-run",
    )
    live = _event(2, "heartbeat", {})
    _write(root / "decisions.jsonl", [observe, live])
    database = ResearchDatabase(tmp_path / "market.duckdb")

    report = database.ingest_cohort_live_ledger(root)

    assert report.scanned_events == 2
    assert report.imported_events == 1
    assert report.skipped_events == 1
    assert report.ignored_observe_events == 1
    assert database.cohort_live_summary()["events"] == 1


def test_research_status_reports_pending_cohort_ledger_bytes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Status makes durable-journal ingestion lag explicit per source."""
    data_root = tmp_path / "data"
    ledger_root = data_root / "live" / "bidirectional_cohort"
    decisions = ledger_root / "decisions.jsonl"
    btc = ledger_root / "btc.jsonl"
    _write(decisions, [_event(1, "heartbeat", {})])
    _write(btc, [_event(1, "heartbeat", {})])
    database = ResearchDatabase(data_root / "research" / "market.duckdb")
    database.ingest_cohort_live_ledger(ledger_root)
    with btc.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_event(2, "heartbeat", {})) + "\n")

    result = main(["--data-root", str(data_root), "db", "status"])
    report = json.loads(capsys.readouterr().out)

    assert result == 0
    freshness = report["cohort_live_freshness"]
    assert freshness["state"] == "pending_import"
    assert freshness["source_files"] == 2
    assert freshness["synchronized_files"] == 1
    assert freshness["pending_files"] == 1
    assert freshness["missing_files"] == 0
    assert freshness["truncated_files"] == 0
    assert freshness["pending_bytes"] > 0
    assert freshness["latest_imported_event_at_utc"] == ("2026-08-03T12:00:00+00:00")
    sources = {row["ledger_symbol"]: row for row in freshness["sources"]}
    assert sources["PORTFOLIO"]["state"] == "synchronized"
    assert sources["BTC"]["state"] == "pending_import"
    assert sources["BTC"]["pending_bytes"] == freshness["pending_bytes"]


def test_snapshot_fills_are_deduplicated_and_attributed_to_close_orders(
    tmp_path: Path,
) -> None:
    """Repeated snapshot history becomes one provider-attributed close order."""
    root = tmp_path / "cohort"
    fills = _attributed_lifecycle_fills()
    _write(
        root / "decisions.jsonl",
        [
            _event(1, "cohort_snapshot", {"recent_fills": fills}),
            _event(2, "cohort_snapshot", {"recent_fills": fills}),
        ],
    )
    database_path = tmp_path / "market.duckdb"
    ResearchDatabase(database_path).ingest_cohort_live_ledger(root)

    with duckdb.connect(str(database_path), read_only=True) as connection:
        attributed = connection.execute(
            """SELECT trade_id, strategy_id, operation
               FROM cohort_live_attributed_fills ORDER BY trade_id"""
        ).fetchall()
        close = connection.execute(
            """SELECT symbol, strategy_id, exit_controller_id, exit_oid,
                      exit_size, closed_pnl_usd, lifecycle_net_pnl_usd,
                      exit_fill_count, exit_reason
               FROM cohort_live_close_orders"""
        ).fetchone()

    assert attributed == [
        (10, "test_fade_1m", "entry"),
        (11, "test_fade_1m", "reduce_only_close"),
        (12, "cohort_maximum_hold", "reduce_only_close"),
    ]
    assert close == (
        "HYPE",
        "test_fade_1m",
        "cohort_maximum_hold",
        9,
        0.5,
        0.5,
        0.45,
        2,
        "maximum_hold_seconds",
    )


def test_close_order_uses_protective_operation_when_exit_reason_is_absent(
    tmp_path: Path,
) -> None:
    """A venue stop remains explicitly classified when no reason field exists."""
    root = tmp_path / "cohort"
    entry = _attributed_fill(20, 2, "entry", 0.0, 0.5)
    stop = _attributed_fill(21, 3, "protective_stop", -0.4, 0.5)
    stop["exit_reason"] = None
    stop["net_pnl_usd"] = -0.45
    _write(
        root / "decisions.jsonl",
        [_event(1, "cohort_snapshot", {"recent_fills": [entry, stop]})],
    )
    database_path = tmp_path / "market.duckdb"
    ResearchDatabase(database_path).ingest_cohort_live_ledger(root)

    with duckdb.connect(str(database_path), read_only=True) as connection:
        reason = connection.execute(
            "SELECT exit_reason FROM cohort_live_close_orders"
        ).fetchone()

    assert reason == ("protective_stop",)


def test_portfolio_archive_reconciles_all_symbols_and_entry_leverage(
    tmp_path: Path,
) -> None:
    """All-time metrics retain retired symbols without widening live authority."""
    root = tmp_path / "cohort"
    hype_entry = _attributed_fill(30, 30, "entry", 0.0, 0.5)
    hype_close = _attributed_fill(31, 31, "reduce_only_close", 0.5, 0.5)
    btc_entry = _attributed_fill(40, 40, "entry", 0.0, 0.1)
    btc_close = _attributed_fill(41, 41, "reduce_only_close", -0.2, 0.1)
    for fill in (hype_entry, hype_close, btc_entry, btc_close):
        fill["origin_run_id"] = "run-1"
    for fill in (btc_entry, btc_close):
        fill["symbol"] = "BTC"
        fill["strategy_id"] = "test_trend_5m"
        fill["price"] = 201.0 if fill["operation"] != "entry" else 200.0
        fill["entry_price"] = 200.0 if fill["operation"] != "entry" else None
        fill["entry_venue_timestamp_ms"] = (
            3_000 if fill["operation"] != "entry" else None
        )
        fill["venue_timestamp_ms"] = 4_000 if fill["operation"] != "entry" else 3_000
        fill["direction"] = (
            "Close Short" if fill["operation"] != "entry" else "Open Short"
        )
        fill["side"] = "B" if fill["operation"] != "entry" else "A"
    hype_close["net_pnl_usd"] = 0.45
    hype_close["lifecycle_fees_usd"] = 0.04
    hype_close["lifecycle_funding_usd"] = 0.01
    btc_close["net_pnl_usd"] = -0.25
    btc_close["lifecycle_fees_usd"] = 0.03
    btc_close["lifecycle_funding_usd"] = -0.005
    _write(
        root / "decisions.jsonl",
        [
            _event(
                1,
                "configuration_identity",
                {
                    "assets": [
                        {"symbol": "HYPE", "leverage": 5.0},
                        {"symbol": "BTC", "leverage": 10.0},
                    ]
                },
            ),
            _event(
                2,
                "cohort_snapshot",
                {
                    "recent_fills": [
                        hype_entry,
                        hype_close,
                        btc_entry,
                        btc_close,
                    ]
                },
            ),
        ],
    )
    _write(
        root / "hype.jsonl",
        [
            _event(
                1,
                "order_acknowledgement",
                {"operation": "entry", "accepted": True, "oid": 30},
            ),
            _event(
                2,
                "position",
                {"size_signed": 0.5, "margin_used_usd": 9.8, "leverage": 5.0},
            ),
        ],
    )
    _write(
        root / "btc.jsonl",
        [
            _event(
                1,
                "order_acknowledgement",
                {"operation": "entry", "accepted": True, "oid": 40},
            ),
            _event(
                2,
                "position",
                {"size_signed": -0.1, "margin_used_usd": 1.9, "leverage": 10.0},
            ),
        ],
    )
    database_path = tmp_path / "market.duckdb"
    ResearchDatabase(database_path).ingest_cohort_live_ledger(root)

    archive = load_cohort_live_portfolio_archive(database_path)

    assert (
        archive["source_execution"]
        == archive_module.cohort_live_fill_identity(database_path).to_dict()
    )
    assert archive["symbols"] == ["BTC", "HYPE"]
    assert archive["coverage"] == {
        "complete": True,
        "closed_orders": 2,
        "leverage_matches": 2,
    }
    total = archive["performance"]["total"]
    assert total["closed_trades"] == 2
    assert (total["wins"], total["losses"], total["breakeven"]) == (1, 1, 0)
    assert total["net_pnl_usd"] == pytest.approx(0.2)
    assert total["entry_margin_used_usd"] == pytest.approx(11.7)
    assert total["fees_usd"] == pytest.approx(0.07)
    assert total["funding_usd"] == pytest.approx(0.005)
    assert set(archive["performance"]["by_provider_symbol"]) == {
        "test_trend_5m|BTC",
        "test_fade_1m|HYPE",
    }


def test_portfolio_archive_drawdown_uses_realized_exit_chronology(
    tmp_path: Path,
) -> None:
    """Closed-sequence drawdown must follow exit order rather than entry order."""
    root = tmp_path / "cohort"
    specifications = (
        ("HYPE", 10, 1_000, 5_000, -2.0),
        ("BTC", 20, 2_000, 3_000, 3.0),
        ("ETH", 30, 2_500, 4_000, -2.0),
    )
    fills: list[dict[str, object]] = []
    for index, (symbol, oid, entry_ms, exit_ms, net) in enumerate(specifications):
        entry = _attributed_fill(100 + index * 2, oid, "entry", 0.0, 0.5)
        close = _attributed_fill(
            101 + index * 2, oid + 1, "reduce_only_close", net, 0.5
        )
        for fill in (entry, close):
            fill["symbol"] = symbol
            fill["origin_run_id"] = "run-1"
        entry["venue_timestamp_ms"] = entry_ms
        close.update(
            venue_timestamp_ms=exit_ms,
            entry_venue_timestamp_ms=entry_ms,
            net_pnl_usd=net,
            lifecycle_fees_usd=0.01,
            lifecycle_funding_usd=0.0,
        )
        fills.extend((entry, close))
        _write(
            root / f"{symbol.lower()}.jsonl",
            [
                _event(
                    1,
                    "order_acknowledgement",
                    {"operation": "entry", "accepted": True, "oid": oid},
                ),
                _event(
                    2,
                    "position",
                    {"size_signed": 0.5, "margin_used_usd": 10.0, "leverage": 5.0},
                ),
            ],
        )
    _write(
        root / "decisions.jsonl",
        [_event(1, "cohort_snapshot", {"recent_fills": fills})],
    )
    database_path = tmp_path / "market.duckdb"
    ResearchDatabase(database_path).ingest_cohort_live_ledger(root)

    archive = load_cohort_live_portfolio_archive(database_path)

    assert archive["performance"]["total"][
        "maximum_closed_sequence_drawdown_usd"
    ] == pytest.approx(4.0)


def test_namespaced_asset_identity_reconciles_archive_entry_margin(
    tmp_path: Path,
) -> None:
    """A namespaced ledger must retain the venue symbol's exact casing."""
    root, database_path = _namespaced_archive_fixture(tmp_path)

    ResearchDatabase(database_path).ingest_cohort_live_ledger(root)
    archive = load_cohort_live_portfolio_archive(database_path)

    assert archive["symbols"] == ["xyz:BBB"]
    assert archive["performance"]["total"]["entry_margin_used_usd"] == 15.0


def test_namespaced_asset_identity_repairs_legacy_uppercase_rows(
    tmp_path: Path,
) -> None:
    """A repeated import must repair the historical HIP-3 casing defect."""
    root, database_path = _namespaced_archive_fixture(tmp_path)
    database = ResearchDatabase(database_path)
    database.ingest_cohort_live_ledger(root)
    with duckdb.connect(str(database_path)) as connection:
        connection.execute("UPDATE cohort_live_events SET ledger_symbol = 'XYZ:BBB'")
        connection.execute("UPDATE cohort_live_sources SET ledger_symbol = 'XYZ:BBB'")

    database.ingest_cohort_live_ledger(root)
    archive = load_cohort_live_portfolio_archive(database_path)

    assert archive["symbols"] == ["xyz:BBB"]
    assert archive["performance"]["total"]["entry_margin_used_usd"] == 15.0


def _namespaced_archive_fixture(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "cohort"
    entry = _attributed_fill(50, 50, "entry", 0.0, 0.5)
    close = _attributed_fill(51, 51, "protective_stop", -0.4, 0.5)
    for fill in (entry, close):
        fill["symbol"] = "xyz:BBB"
        fill["origin_run_id"] = "run-1"
        fill["strategy_id"] = "test_band_a_15m"
    close["net_pnl_usd"] = -0.45
    close["lifecycle_fees_usd"] = 0.05
    close["lifecycle_funding_usd"] = 0.0
    _write(
        root / "decisions.jsonl",
        [_event(1, "cohort_snapshot", {"recent_fills": [entry, close]})],
    )
    _write(
        root / "xyz:bbb.jsonl",
        [
            _event(1, "configuration_identity", {"symbol": "xyz:BBB"}),
            _event(
                2,
                "order_acknowledgement",
                {"operation": "entry", "accepted": True, "oid": 50},
            ),
            _event(
                3,
                "position",
                {"size_signed": 0.5, "margin_used_usd": 15.0, "leverage": 5.0},
            ),
        ],
    )
    database_path = tmp_path / "market.duckdb"
    return root, database_path


def _write(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _event(
    sequence: int,
    event_type: str,
    payload: dict[str, object],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "sequence": sequence,
        "event_type": event_type,
        "observed_at_utc": "2026-08-03T12:00:00+00:00",
        "execution_mode": "live",
        "effective_mode": "LIVE ARMED",
        "live_armed": True,
        "execution_authority": "hyperliquid_mainnet",
        "profile_id": "cohort-v2",
        "profile_fingerprint": "a" * 64,
        "run_fingerprint": "b" * 64,
        "run_id": "run-1",
        "payload": payload,
    }


def _attributed_lifecycle_fills() -> list[dict[str, object]]:
    entry = _attributed_fill(10, 1, "entry", 0.0, 0.5)
    entry.update(
        {
            "strategy_id": "test_fade_1m",
            "entry_venue_timestamp_ms": None,
        }
    )
    first = _attributed_fill(11, 9, "reduce_only_close", 0.3, 0.3)
    second = _attributed_fill(12, 9, "reduce_only_close", 0.2, 0.2)
    second["strategy_id"] = "cohort_maximum_hold"
    return [entry, first, second]


def _attributed_fill(
    trade_id: int,
    oid: int,
    operation: str,
    closed_pnl_usd: float,
    size: float,
) -> dict[str, object]:
    closing = operation != "entry"
    return {
        "symbol": "HYPE",
        "strategy_id": "test_fade_1m",
        "exit_controller_id": "cohort_maximum_hold" if closing else None,
        "origin_run_id": "entry-run",
        "operation": operation,
        "trade_id": trade_id,
        "oid": oid,
        "venue_timestamp_ms": 2_000 if closing else 1_000,
        "price": 101.0 if closing else 100.0,
        "size": size,
        "side": "A" if closing else "B",
        "direction": "Close Long" if closing else "Open Long",
        "fee_usd": 0.01,
        "closed_pnl_usd": closed_pnl_usd,
        "expected_price": 100.9 if closing else 99.9,
        "slippage_bps": 1.0,
        "acknowledgement_latency_ms": 1_200,
        "markout_bps": 2.0,
        "markout_horizon_ms": 5_000,
        "exit_reason": "maximum_hold_seconds" if closing else None,
        "lifecycle_fees_usd": 0.04 if closing else None,
        "lifecycle_funding_usd": 0.01 if closing else None,
        "net_pnl_usd": 0.45 if closing else None,
        "holding_time_ms": 1_000 if closing else None,
        "entry_price": 100.0 if closing else None,
        "entry_venue_timestamp_ms": 1_000 if closing else None,
    }

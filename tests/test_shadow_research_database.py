"""Durable, report-only DuckDB ingestion for backend shadow evidence."""

from __future__ import annotations

import json
from datetime import UTC
from pathlib import Path

import duckdb
import pytest

from hypervector.data.research_database import ResearchDatabase
from hypervector.data.oxa_storage import file_evidence
from hypervector.cli import main
from hypervector.research.hypertrader_source_adapter import (
    LEGACY_HYPERTRADER_REVISION,
    PINNED_HYPERTRADER_REVISION,
)


def _regime_row(minute: int) -> dict[str, object]:
    feed_minute = minute + 1
    return {
        "feed_ts": f"2026-07-28T00:{feed_minute:02d}:00+00:00",
        "run_id": "forward-run",
        "action": "regime_observation",
        "symbol": "BTC",
        "timeframe": "1m",
        "execution_mode": "shadow",
        "submitted": False,
        "place_attempted": False,
        "open": 100.0 + minute,
        "high": 101.0 + minute,
        "low": 99.0 + minute,
        "mark_px": 100.5 + minute,
        "volume": 2.0 + minute,
        "primary_regime": "TREND_UP",
        "state_5m": "TREND_UP",
        "entry_direction": "long",
    }


def _write_ledger(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_shadow_ledger_import_is_idempotent_and_materializes_closed_5m_bars(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / "paper" / "decisions" / "decisions.jsonl"
    rows = [_regime_row(minute) for minute in range(6)]
    rows.append(
        {
            "feed_ts": "2026-07-28T00:06:10+00:00",
            "run_id": "forward-run",
            "action": "book_observation",
            "symbol": "BTC",
            "timeframe": "1m",
            "execution_mode": "shadow",
            "submitted": False,
            "place_attempted": False,
        }
    )
    _write_ledger(ledger, rows)
    database_path = tmp_path / "research" / "market.duckdb"
    database = ResearchDatabase(database_path)

    first = database.ingest_shadow_ledger(ledger)
    second = database.ingest_shadow_ledger(ledger)

    assert first.to_dict() == {
        "source_events": 7,
        "imported_events": 7,
        "skipped_events": 0,
        "regime_observations": 6,
        "completed_5m_bars": 1,
    }
    assert second.to_dict() == {
        "source_events": 7,
        "imported_events": 0,
        "skipped_events": 7,
        "regime_observations": 6,
        "completed_5m_bars": 1,
    }
    with duckdb.connect(str(database_path), read_only=True) as connection:
        bar = connection.execute(
            """
            SELECT run_id, symbol, bar_open_at, available_at,
                   open, high, low, close, volume, source_minutes
            FROM shadow_completed_5m_bars
            """
        ).fetchone()

    assert bar is not None
    assert bar[0:2] == ("forward-run", "BTC")
    assert bar[2].astimezone(UTC).isoformat() == "2026-07-28T00:00:00+00:00"
    assert bar[3].astimezone(UTC).isoformat() == "2026-07-28T00:05:00+00:00"
    assert bar[4:] == (100.0, 105.0, 99.0, 104.5, 20.0, 5)


def test_shadow_ledger_import_rejects_non_paper_execution_mode_atomically(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / "decisions.jsonl"
    unsafe = _regime_row(0)
    unsafe["execution_mode"] = "live"
    _write_ledger(ledger, [_regime_row(0), unsafe])
    database = ResearchDatabase(tmp_path / "research.duckdb")

    try:
        database.ingest_shadow_ledger(ledger)
    except ValueError as exc:
        assert "paper or shadow" in str(exc)
    else:
        raise AssertionError("live execution-mode evidence must be rejected")

    assert database.shadow_summary()["shadow_events"] == 0


def test_shadow_ledger_import_cli_reports_annotation_only_contract(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    ledger = tmp_path / "decisions.jsonl"
    _write_ledger(ledger, [_regime_row(minute) for minute in range(5)])

    result = main(
        [
            "--data-root",
            str(tmp_path),
            "research-db-shadow-import",
            "--ledger",
            str(ledger),
        ]
    )
    captured = capsys.readouterr()
    report = json.loads(captured.out)

    assert result == 0
    assert report["report_only"] is True
    assert report["execution_authority"] == "none"
    assert report["ingest"]["completed_5m_bars"] == 1
    assert report["database_path"].endswith("research/market.duckdb")


def _write_labels(
    path: Path,
    metadata_path: Path,
    *,
    revision: str,
    primary: str,
) -> None:
    import pandas as pd

    labels = pd.DataFrame(
        {
            "available_at": [pd.Timestamp("2026-07-28T00:05:00Z")],
            "primary_code": [primary],
            "secondary_code": [None],
            "confidence": [0.8],
            "raw_primary_code": [primary],
            "raw_secondary_code": [None],
            "raw_confidence": [0.9],
            "volume_ratio": [1.2],
        },
        index=pd.DatetimeIndex([pd.Timestamp("2026-07-28T00:00:00Z")]),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    labels.to_parquet(path)
    metadata_path.write_text(
        json.dumps(
            {
                "upstream_revision": revision,
                "report_only": True,
                "runtime_strategy_changed": False,
                "model_authority": "observe",
                "output": file_evidence(path),
            }
        ),
        encoding="utf-8",
    )


def _trade_row(
    feed_ts: str,
    action: str,
    *,
    side: str,
    client_order_id: str | None = None,
    fill_qty: float = 0.0,
    fill_px: float = 0.0,
    fee_usd: float = 0.0,
    funding_payment_usd: float = 0.0,
    exit_reason: str | None = None,
    realized_pnl: float = 0.0,
    verified_liquidation: bool = False,
) -> dict[str, object]:
    """Build one minimal shadow execution event for attribution tests."""
    row: dict[str, object] = {
        "feed_ts": feed_ts,
        "run_id": "forward-run",
        "action": action,
        "symbol": "BTC",
        "timeframe": "1m",
        "execution_mode": "shadow",
        "submitted": False,
        "place_attempted": False,
        "side": side,
        "client_order_id": client_order_id,
        "fill_qty": fill_qty,
        "fill_px": fill_px,
        "fee_usd": fee_usd,
        "funding_payment_usd": funding_payment_usd,
        "exit_reason": exit_reason,
        "realized_pnl": realized_pnl,
    }
    if verified_liquidation:
        row.update(
            {
                "liquidation_price": 108.0,
                "liquidation_trigger_mark": 109.0,
                "liquidation_isolated_margin_usd": 5.0,
                "liquidation_position_equity_usd": 2.0,
                "liquidation_maintenance_margin_usd": 3.0,
            }
        )
    return row


def test_revision_labels_join_same_closed_shadow_bar_without_authority(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / "decisions.jsonl"
    _write_ledger(ledger, [_regime_row(minute) for minute in range(5)])
    database = ResearchDatabase(tmp_path / "research.duckdb")
    database.ingest_shadow_ledger(ledger)
    strict = tmp_path / "strict.parquet"
    strict_meta = tmp_path / "strict.json"
    legacy = tmp_path / "legacy.parquet"
    legacy_meta = tmp_path / "legacy.json"
    _write_labels(
        strict,
        strict_meta,
        revision=PINNED_HYPERTRADER_REVISION,
        primary="RANGE",
    )
    _write_labels(
        legacy,
        legacy_meta,
        revision=LEGACY_HYPERTRADER_REVISION,
        primary="TREND_DOWN",
    )

    strict_report = database.ingest_hypertrader_labels(strict, strict_meta)
    legacy_report = database.ingest_hypertrader_labels(legacy, legacy_meta)
    repeated = database.ingest_hypertrader_labels(legacy, legacy_meta)

    assert strict_report.revision == PINNED_HYPERTRADER_REVISION
    assert legacy_report.imported_labels == 1
    assert repeated.imported_labels == 0
    assert repeated.skipped_labels == 1
    with duckdb.connect(str(tmp_path / "research.duckdb"), read_only=True) as conn:
        comparison = conn.execute(
            """
            SELECT strict_primary, legacy_primary, label_disagrees,
                   strict_available_at <= bar_available_at,
                   legacy_available_at <= bar_available_at,
                   backend_primary, backend_state_5m, backend_entry_direction
            FROM shadow_hypertrader_regime_comparison
            """
        ).fetchone()

    assert comparison == (
        "RANGE",
        "TREND_DOWN",
        True,
        True,
        True,
        "TREND_UP",
        "TREND_UP",
        "long",
    )


def test_completed_trade_attribution_uses_filled_intent_and_causal_labels(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A closed trade must exclude stale intents and future regime evidence."""
    ledger = tmp_path / "decisions.jsonl"
    rows = [_regime_row(minute) for minute in range(5)]
    rows.extend(
        [
            _trade_row(
                "2026-07-28T00:05:01+00:00",
                "submit_entry",
                client_order_id="stale-entry",
                side="buy",
            ),
            _trade_row(
                "2026-07-28T00:05:10+00:00",
                "submit_entry",
                client_order_id="filled-entry",
                side="buy",
            ),
            _trade_row(
                "2026-07-28T00:05:20+00:00",
                "enter_long",
                client_order_id="filled-entry",
                side="buy",
                fill_qty=0.6,
                fill_px=100.0,
                fee_usd=0.01,
            ),
            _trade_row(
                "2026-07-28T00:05:21+00:00",
                "enter_long",
                client_order_id="filled-entry",
                side="buy",
                fill_qty=0.4,
                fill_px=100.0,
                fee_usd=0.02,
            ),
            _trade_row(
                "2026-07-28T00:06:00+00:00",
                "funding",
                side="buy",
                funding_payment_usd=0.1,
            ),
            _trade_row(
                "2026-07-28T00:07:00+00:00",
                "reduce_target",
                side="sell",
                fill_qty=0.4,
                fill_px=102.0,
                fee_usd=0.03,
            ),
            _trade_row(
                "2026-07-28T00:07:01+00:00",
                "close",
                side="sell",
                fill_qty=0.6,
                fill_px=102.0,
                fee_usd=0.04,
                exit_reason="take_profit_8pct_margin",
                realized_pnl=1.8,
            ),
            {
                **_regime_row(5),
                "feed_ts": "2026-07-28T00:08:00+00:00",
                "primary_regime": "TREND_DOWN",
            },
        ]
    )
    _write_ledger(ledger, rows)
    database_path = tmp_path / "research.duckdb"
    database = ResearchDatabase(database_path)
    database.ingest_shadow_ledger(ledger)
    for name, revision, primary in (
        ("strict", PINNED_HYPERTRADER_REVISION, "TRANSITION"),
        ("legacy", LEGACY_HYPERTRADER_REVISION, "TREND_UP"),
    ):
        labels = tmp_path / f"{name}.parquet"
        metadata = tmp_path / f"{name}.json"
        _write_labels(labels, metadata, revision=revision, primary=primary)
        database.ingest_hypertrader_labels(labels, metadata)

    with duckdb.connect(str(database_path), read_only=True) as connection:
        trade = connection.execute(
            """
            SELECT lifecycle_number, direction, intent_at, entry_at, exit_at,
                   entry_fill_count, exit_fill_count, entry_quantity,
                   exit_quantity, entry_price, exit_price, gross_pnl_usd,
                   fees_usd, funding_payment_usd, net_pnl_usd, exit_reason,
                   entry_client_order_id, backend_primary_at_entry,
                   strict_primary_at_entry, legacy_primary_at_entry,
                   backend_strict_disagrees, backend_legacy_disagrees
            FROM shadow_completed_trade_attribution
            """
        ).fetchone()

    assert trade is not None
    assert trade[0:2] == (1, "long")
    assert trade[2].astimezone(UTC).isoformat() == "2026-07-28T00:05:10+00:00"
    assert trade[3].astimezone(UTC).isoformat() == "2026-07-28T00:05:20+00:00"
    assert trade[4].astimezone(UTC).isoformat() == "2026-07-28T00:07:01+00:00"
    assert trade[5:10] == (2, 2, 1.0, 1.0, 100.0)
    assert trade[10] == pytest.approx(102.0)
    assert trade[11:15] == pytest.approx((2.0, 0.1, 0.1, 1.8))
    assert trade[15:] == (
        "take_profit_8pct_margin",
        "filled-entry",
        "TREND_UP",
        "TRANSITION",
        "TREND_UP",
        True,
        False,
    )

    summary = database.shadow_trade_attribution_summary()
    expected_counts = {
        "report_only": True,
        "execution_authority": "none",
        "completed_trades": 1,
        "targets": 1,
        "liquidations": 0,
        "unverified_legacy_liquidations": 0,
        "long_trades": 1,
        "short_trades": 0,
        "source_labeled_trades": 1,
        "backend_strict_disagreements": 1,
        "backend_legacy_disagreements": 0,
    }
    assert {key: summary[key] for key in expected_counts} == expected_counts
    assert tuple(
        summary[key]
        for key in (
            "gross_pnl_usd",
            "fees_usd",
            "funding_payment_usd",
            "net_pnl_usd",
        )
    ) == pytest.approx((2.0, 0.1, 0.1, 1.8))

    result = main(
        [
            "--data-root",
            str(tmp_path),
            "research-db-shadow-trades",
            "--database",
            str(database_path),
        ]
    )
    report = json.loads(capsys.readouterr().out)
    assert result == 0
    assert report == {
        "ok": True,
        "database_path": str(database_path),
        **summary,
        "venue": "hyperliquid",
    }


def test_short_liquidation_attribution_includes_partial_fill_and_funding_credit(
    tmp_path: Path,
) -> None:
    """Short liquidation economics must preserve partial exits and funding signs."""
    rows = [_regime_row(minute) for minute in range(5)]
    rows.extend(
        [
            _trade_row(
                "2026-07-28T00:05:10+00:00",
                "submit_entry",
                client_order_id="short-entry",
                side="sell",
            ),
            _trade_row(
                "2026-07-28T00:05:20+00:00",
                "enter_short",
                client_order_id="short-entry",
                side="sell",
                fill_qty=2.0,
                fill_px=100.0,
                fee_usd=1.0,
            ),
            _trade_row(
                "2026-07-28T00:06:00+00:00",
                "funding",
                side="sell",
                funding_payment_usd=-1.0,
            ),
            _trade_row(
                "2026-07-28T00:06:30+00:00",
                "partial_liquidation",
                side="buy",
                fill_qty=0.5,
                fill_px=105.0,
                fee_usd=2.0,
            ),
            _trade_row(
                "2026-07-28T00:07:00+00:00",
                "liquidation",
                side="buy",
                fill_qty=1.5,
                fill_px=110.0,
                fee_usd=3.0,
                exit_reason="isolated_liquidation",
                realized_pnl=-22.5,
                verified_liquidation=True,
            ),
        ]
    )
    ledger = tmp_path / "decisions.jsonl"
    _write_ledger(ledger, rows)
    database_path = tmp_path / "research.duckdb"
    database = ResearchDatabase(database_path)
    database.ingest_shadow_ledger(ledger)

    with duckdb.connect(str(database_path), read_only=True) as connection:
        trade = connection.execute(
            """
            SELECT direction, terminal_action, entry_quantity, exit_quantity,
                   gross_pnl_usd, fees_usd, funding_payment_usd, net_pnl_usd,
                   quantity_reconciled, strict_primary_at_entry,
                   backend_strict_disagrees
            FROM shadow_completed_trade_attribution
            """
        ).fetchone()

    assert trade is not None
    assert trade[0:4] == ("short", "liquidation", 2.0, 2.0)
    assert trade[4:8] == pytest.approx((-17.5, 6.0, -1.0, -22.5))
    assert trade[8:] == (True, None, False)
    summary = database.shadow_trade_attribution_summary()
    assert summary["completed_trades"] == 1
    assert summary["liquidations"] == 1
    assert summary["unverified_legacy_liquidations"] == 0
    assert summary["short_trades"] == 1
    assert summary["net_pnl_usd"] == pytest.approx(-22.5)


def test_incomplete_legacy_liquidation_is_reported_but_not_verified(
    tmp_path: Path,
) -> None:
    """Pre-fix liquidation labels cannot contaminate verified counts."""
    rows = [
        _trade_row(
            "2026-07-28T00:05:20+00:00",
            "enter_long",
            side="buy",
            fill_qty=1.0,
            fill_px=100.0,
        ),
        _trade_row(
            "2026-07-28T00:07:00+00:00",
            "liquidation",
            side="sell",
            fill_qty=1.0,
            fill_px=102.0,
            exit_reason="isolated_mark_liquidation",
            realized_pnl=1.0,
        ),
    ]
    ledger = tmp_path / "decisions.jsonl"
    _write_ledger(ledger, rows)
    database_path = tmp_path / "research.duckdb"
    database = ResearchDatabase(database_path)
    database.ingest_shadow_ledger(ledger)

    with duckdb.connect(str(database_path), read_only=True) as connection:
        evidence_status = connection.execute(
            "SELECT liquidation_evidence_status FROM shadow_completed_trade_attribution"
        ).fetchone()
    summary = database.shadow_trade_attribution_summary()

    assert evidence_status == ("unverified_legacy",)
    assert summary["completed_trades"] == 1
    assert summary["liquidations"] == 0
    assert summary["unverified_legacy_liquidations"] == 1


def test_revision_label_identity_rejects_conflicting_reimport(tmp_path: Path) -> None:
    database_path = tmp_path / "research.duckdb"
    database = ResearchDatabase(database_path)
    labels = tmp_path / "strict.parquet"
    metadata = tmp_path / "strict.json"
    _write_labels(
        labels,
        metadata,
        revision=PINNED_HYPERTRADER_REVISION,
        primary="RANGE",
    )
    database.ingest_hypertrader_labels(labels, metadata)
    _write_labels(
        labels,
        metadata,
        revision=PINNED_HYPERTRADER_REVISION,
        primary="TREND_UP",
    )

    with pytest.raises(ValueError, match="conflicting Hypertrader annotation"):
        database.ingest_hypertrader_labels(labels, metadata)

    with duckdb.connect(str(database_path), read_only=True) as connection:
        count = connection.execute(
            "SELECT count(*) FROM hypertrader_regime_annotations"
        ).fetchone()
    assert count == (1,)


def test_regime_label_import_cli_preserves_source_revision(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    labels = tmp_path / "legacy.parquet"
    metadata = tmp_path / "legacy.json"
    _write_labels(
        labels,
        metadata,
        revision=LEGACY_HYPERTRADER_REVISION,
        primary="TREND_DOWN",
    )

    result = main(
        [
            "--data-root",
            str(tmp_path),
            "research-db-regime-label-import",
            "--labels",
            str(labels),
            "--metadata",
            str(metadata),
        ]
    )
    report = json.loads(capsys.readouterr().out)

    assert result == 0
    assert report["report_only"] is True
    assert report["execution_authority"] == "none"
    assert report["ingest"]["revision"] == LEGACY_HYPERTRADER_REVISION
    assert report["ingest"]["imported_labels"] == 1


def test_regime_comparison_summary_quantifies_backend_and_source_disagreement(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / "decisions.jsonl"
    _write_ledger(ledger, [_regime_row(minute) for minute in range(5)])
    database = ResearchDatabase(tmp_path / "research.duckdb")
    database.ingest_shadow_ledger(ledger)
    for name, revision, primary in (
        ("strict", PINNED_HYPERTRADER_REVISION, "RANGE"),
        ("legacy", LEGACY_HYPERTRADER_REVISION, "TREND_DOWN"),
    ):
        labels = tmp_path / f"{name}.parquet"
        metadata = tmp_path / f"{name}.json"
        _write_labels(labels, metadata, revision=revision, primary=primary)
        database.ingest_hypertrader_labels(labels, metadata)

    summary = database.regime_comparison_summary()

    assert summary == {
        "report_only": True,
        "execution_authority": "none",
        "completed_shadow_5m_bars": 1,
        "compared_bars": 1,
        "unlabeled_completed_bars": 0,
        "strict_compared_bars": 1,
        "legacy_compared_bars": 1,
        "dual_compared_bars": 1,
        "strict_unlabeled_completed_bars": 0,
        "legacy_unlabeled_completed_bars": 0,
        "strict_legacy_disagreements": 1,
        "backend_strict_disagreements": 1,
        "backend_legacy_disagreements": 1,
        "archive_comparable_bars": 0,
        "archive_exact_ohlcv_bars": 0,
        "archive_ohlcv_mismatches": 0,
        "comparison_start_utc": "2026-07-28T00:00:00+00:00",
        "comparison_end_utc": "2026-07-28T00:00:00+00:00",
    }

    result = main(
        [
            "--data-root",
            str(tmp_path),
            "research-db-regime-compare",
            "--database",
            str(tmp_path / "research.duckdb"),
        ]
    )
    assert result == 0


def test_regime_comparison_summary_separates_strict_from_dual_label_coverage(
    tmp_path: Path,
) -> None:
    """Missing legacy history must not make strict-labeled bars look unlabeled."""
    ledger = tmp_path / "decisions.jsonl"
    _write_ledger(ledger, [_regime_row(minute) for minute in range(5)])
    database = ResearchDatabase(tmp_path / "research.duckdb")
    database.ingest_shadow_ledger(ledger)
    labels = tmp_path / "strict.parquet"
    metadata = tmp_path / "strict.json"
    _write_labels(
        labels,
        metadata,
        revision=PINNED_HYPERTRADER_REVISION,
        primary="RANGE",
    )
    database.ingest_hypertrader_labels(labels, metadata)

    summary = database.regime_comparison_summary()

    assert summary["strict_compared_bars"] == 1
    assert summary["legacy_compared_bars"] == 0
    assert summary["dual_compared_bars"] == 0
    assert summary["strict_unlabeled_completed_bars"] == 0
    assert summary["legacy_unlabeled_completed_bars"] == 1
    assert summary["unlabeled_completed_bars"] == 0

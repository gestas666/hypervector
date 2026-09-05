"""Prospective HIP-3 venue-path coverage audit tests."""

from __future__ import annotations

from dataclasses import replace

from pytest import raises

from hypervector.data.hl_events import (
    AssetContextEvent,
    BookLevel,
    L2SnapshotEvent,
    PublicTradeEvent,
    StreamGap,
)
from hypervector.research.hip3_prospective_path_audit import (
    Hip3ProspectivePathAuditConfig,
    build_hip3_prospective_path_audit,
)

_BAR_MS = 15 * 60_000
_START_MS = 1_800_000_000_000
_SYMBOL = "xyz:SKHX"


def test_complete_bar_reports_exact_mark_l2_and_trade_coverage() -> None:
    config = Hip3ProspectivePathAuditConfig(symbol=_SYMBOL)
    marks = tuple(_mark(offset) for offset in range(0, _BAR_MS, 5_000))
    books = tuple(_book(offset) for offset in range(0, _BAR_MS, 10_000))
    trades = (_trade(30_000, 1), _trade(60_000, 2))

    report = build_hip3_prospective_path_audit(
        l2_snapshots=books,
        public_trades=trades,
        asset_contexts=marks,
        stream_gaps=(),
        observed_at_ms=_START_MS + _BAR_MS,
        config=config,
    )

    assert report["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "promotion_authority": "none",
        "runtime_strategy_changed": False,
    }
    assert report["coverage"]["completed_bars"] == 1
    assert report["channels"]["mark"]["complete_bars"] == 1
    assert report["channels"]["mark"]["unique_observations"] == len(marks)
    assert report["channels"]["mark"]["duplicate_observations"] == 0
    assert report["channels"]["mark"]["maximum_observed_gap_ms"] == 5_000
    assert report["channels"]["l2"]["complete_bars"] == 1
    assert report["channels"]["trades"]["bars_with_trades"] == 1
    identity = report["evidence_identity"]
    assert identity["l2"]["rows"] == len(books)
    assert identity["mark"]["rows"] == len(marks)
    assert identity["trades"]["rows"] == len(trades)
    assert identity["completed_bar_l2"] == identity["l2"]
    assert identity["completed_bar_trades"] == identity["trades"]
    assert all(
        len(identity[channel]["sha256"]) == 64
        for channel in ("l2", "mark", "trades", "gaps")
    )
    assert len(identity["material_state_sha256"]) == 64
    assert report["technical_assessment"] == {
        "prospective_bar_path_coverage_resolved": True,
        "unresolved_bars": 0,
        "candle_ohlc_parity_resolved": False,
    }


def test_partial_bar_trade_does_not_change_completed_bar_identity() -> None:
    config = Hip3ProspectivePathAuditConfig(symbol=_SYMBOL)
    marks = tuple(_mark(offset) for offset in range(0, _BAR_MS + 60_000, 5_000))
    books = tuple(_book(offset) for offset in range(0, _BAR_MS + 60_000, 10_000))
    completed = _trade(30_000, 1)
    partial = _trade(_BAR_MS + 30_000, 2)

    report = build_hip3_prospective_path_audit(
        l2_snapshots=books,
        public_trades=(completed, partial),
        asset_contexts=marks,
        stream_gaps=(),
        observed_at_ms=_START_MS + _BAR_MS + 60_000,
        config=config,
    )
    control = build_hip3_prospective_path_audit(
        l2_snapshots=books,
        public_trades=(completed,),
        asset_contexts=marks,
        stream_gaps=(),
        observed_at_ms=_START_MS + _BAR_MS + 60_000,
        config=config,
    )

    assert report["evidence_identity"]["trades"]["rows"] == 2
    assert (
        report["evidence_identity"]["completed_bar_trades"]
        == control["evidence_identity"]["completed_bar_trades"]
    )


def test_partial_bar_book_does_not_change_completed_l2_identity() -> None:
    config = Hip3ProspectivePathAuditConfig(symbol=_SYMBOL)
    marks = tuple(_mark(offset) for offset in range(0, _BAR_MS + 60_000, 5_000))
    completed = tuple(_book(offset) for offset in range(0, _BAR_MS, 10_000))
    partial = _book(_BAR_MS + 30_000)

    report = build_hip3_prospective_path_audit(
        l2_snapshots=completed + (partial,),
        public_trades=(),
        asset_contexts=marks,
        stream_gaps=(),
        observed_at_ms=_START_MS + _BAR_MS + 60_000,
        config=config,
    )
    control = build_hip3_prospective_path_audit(
        l2_snapshots=completed,
        public_trades=(),
        asset_contexts=marks,
        stream_gaps=(),
        observed_at_ms=_START_MS + _BAR_MS + 60_000,
        config=config,
    )

    assert report["evidence_identity"]["l2"]["rows"] == len(completed) + 1
    assert (
        report["evidence_identity"]["completed_bar_l2"]
        == control["evidence_identity"]["completed_bar_l2"]
    )


def test_wrong_channel_source_is_rejected_instead_of_success_shaped() -> None:
    config = Hip3ProspectivePathAuditConfig(symbol=_SYMBOL)
    books = (_book(0), replace(_book(10_000), source="unverified_l2"))

    with raises(ValueError, match="source contract"):
        build_hip3_prospective_path_audit(
            l2_snapshots=books,
            public_trades=(_trade(30_000, 1),),
            asset_contexts=(_mark(0), _mark(5_000)),
            stream_gaps=(),
            observed_at_ms=_START_MS + _BAR_MS,
            config=config,
        )


def test_repeated_trade_payload_uses_earliest_receipt_without_double_counting() -> None:
    """Recorder overlap may duplicate one venue trade with a later receipt only."""
    config = Hip3ProspectivePathAuditConfig(symbol=_SYMBOL)
    original = _trade(30_000, 1)
    repeated = replace(original, received_ts_ns=original.received_ts_ns + 1_000_000)

    report = build_hip3_prospective_path_audit(
        l2_snapshots=tuple(_book(offset) for offset in range(0, _BAR_MS, 10_000)),
        public_trades=(repeated, original),
        asset_contexts=tuple(_mark(offset) for offset in range(0, _BAR_MS, 5_000)),
        stream_gaps=(),
        observed_at_ms=_START_MS + _BAR_MS,
        config=config,
    )

    assert report["channels"]["trades"]["observations"] == 2
    assert report["channels"]["trades"]["unique_observations"] == 1
    assert report["channels"]["trades"]["duplicate_observations"] == 1


def test_repeated_trade_identity_with_changed_economics_is_rejected() -> None:
    """Price, size, side, hash, or participants cannot conflict under one ID."""
    config = Hip3ProspectivePathAuditConfig(symbol=_SYMBOL)
    original = _trade(30_000, 1)

    with raises(ValueError, match="conflicting public trade identity"):
        build_hip3_prospective_path_audit(
            l2_snapshots=tuple(_book(offset) for offset in range(0, _BAR_MS, 10_000)),
            public_trades=(original, replace(original, price=101.0)),
            asset_contexts=tuple(_mark(offset) for offset in range(0, _BAR_MS, 5_000)),
            stream_gaps=(),
            observed_at_ms=_START_MS + _BAR_MS,
            config=config,
        )


def test_future_received_book_cannot_prove_past_path_coverage() -> None:
    config = Hip3ProspectivePathAuditConfig(symbol=_SYMBOL)
    future = (_START_MS + _BAR_MS + 1) * 1_000_000
    books = (_book(0), replace(_book(10_000), received_ts_ns=future))

    with raises(ValueError, match="receipt exceeds observed_at_ms"):
        build_hip3_prospective_path_audit(
            l2_snapshots=books,
            public_trades=(),
            asset_contexts=(_mark(0), _mark(5_000)),
            stream_gaps=(),
            observed_at_ms=_START_MS + _BAR_MS,
            config=config,
        )


def test_bounded_reconnect_is_disclosed_without_overriding_exact_cadence() -> None:
    config = Hip3ProspectivePathAuditConfig(symbol=_SYMBOL)
    marks = tuple(_mark(offset) for offset in range(0, _BAR_MS, 5_000))
    books = tuple(_book(offset) for offset in range(0, _BAR_MS, 10_000))

    report = build_hip3_prospective_path_audit(
        l2_snapshots=books,
        public_trades=(),
        asset_contexts=marks,
        stream_gaps=(_gap(30_000),),
        observed_at_ms=_START_MS + _BAR_MS,
        config=config,
    )

    assert report["channels"]["mark"]["declared_gap_bars"] == 1
    assert report["channels"]["l2"]["declared_gap_bars"] == 1
    assert report["channels"]["mark"]["unbounded_gap_bars"] == 0
    assert report["channels"]["l2"]["unbounded_gap_bars"] == 0
    assert report["technical_assessment"]["prospective_bar_path_coverage_resolved"]


def test_l2_exchange_gap_bounds_do_not_override_exact_mark_receipt_cadence() -> None:
    config = Hip3ProspectivePathAuditConfig(symbol=_SYMBOL)
    marks = tuple(_mark(offset) for offset in range(0, _BAR_MS, 5_000))
    books = tuple(_book(offset) for offset in range(0, _BAR_MS, 10_000))
    gap = replace(
        _gap(30_000),
        previous_exchange_ts_ms=_START_MS + 27_000,
        next_exchange_ts_ms=_START_MS + 33_000,
    )

    report = build_hip3_prospective_path_audit(
        l2_snapshots=books,
        public_trades=(),
        asset_contexts=marks,
        stream_gaps=(gap,),
        observed_at_ms=_START_MS + _BAR_MS,
        config=config,
    )

    assert report["channels"]["mark"]["maximum_observed_gap_ms"] == 5_000
    assert report["channels"]["mark"]["unbounded_gap_bars"] == 0
    assert report["technical_assessment"]["prospective_bar_path_coverage_resolved"]


def _level(price: float) -> BookLevel:
    return BookLevel(price=price, size=1.0, order_count=1)


def _book(offset_ms: int) -> L2SnapshotEvent:
    timestamp = _START_MS + offset_ms
    return L2SnapshotEvent(
        _SYMBOL,
        timestamp,
        timestamp * 1_000_000 + 1_000,
        (_level(99.0),),
        (_level(101.0),),
    )


def _mark(offset_ms: int) -> AssetContextEvent:
    timestamp = _START_MS + offset_ms
    return AssetContextEvent(
        _SYMBOL,
        timestamp,
        timestamp * 1_000_000 + 2_000,
        100.0,
        100.1,
        0.00001,
        10_000.0,
        100.0,
    )


def _trade(offset_ms: int, trade_id: int) -> PublicTradeEvent:
    timestamp = _START_MS + offset_ms
    return PublicTradeEvent(
        _SYMBOL,
        "buy",
        100.0,
        1.0,
        f"0x{trade_id}",
        timestamp,
        timestamp * 1_000_000 + 3_000,
        trade_id,
        "buyer",
        "seller",
    )


def _gap(offset_ms: int) -> StreamGap:
    timestamp = _START_MS + offset_ms
    return StreamGap(
        _SYMBOL,
        "l2Book,activeAssetCtx",
        timestamp * 1_000_000,
        "fixture",
        timestamp - 1_000,
        timestamp + 1_000,
    )

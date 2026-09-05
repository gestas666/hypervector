"""Data-quality attribution for the SPCX cash-open live source."""

from __future__ import annotations

from hypervector.data.hl_events import PublicTradeEvent, StreamGap
from hypervector.research.spcx_cash_open_source_quality import (
    build_spcx_cash_open_source_quality,
)

_BAR_MS = 900_000
_START_MS = 1_787_232_600_000  # 2026-08-20T13:30:00Z
_CASH_BARS = 26
_END_MS = 1_787_281_200_000  # 2026-08-21T03:00:00Z


def test_complete_cash_session_is_separated_from_overnight_no_trade_bars() -> None:
    """Irrelevant overnight sparsity must not be called missing cash-session data."""
    rows = tuple(_trade(index + 1, _START_MS + index * _BAR_MS) for index in range(26))

    report = build_spcx_cash_open_source_quality(
        rows,
        start_ms=_START_MS,
        end_ms=_END_MS,
    )

    assert report["all_hours"]["expected_bars"] == 54
    assert report["all_hours"]["observed_bars"] == 26
    assert report["all_hours"]["missing_bars"] == 28
    assert report["cash_sessions"]["expected_bars"] == _CASH_BARS
    assert report["cash_sessions"]["observed_bars"] == _CASH_BARS
    assert report["cash_sessions"]["missing_bars"] == 0
    assert report["diagnosis"] == "irrelevant_non_cash_no_trade_bars_reject_source"


def test_missing_cash_session_bar_remains_an_explicit_quality_failure() -> None:
    """The diagnostic must not excuse missing evidence inside the cash session."""
    rows = tuple(_trade(index + 1, _START_MS + index * _BAR_MS) for index in range(25))

    report = build_spcx_cash_open_source_quality(
        rows,
        start_ms=_START_MS,
        end_ms=_END_MS,
    )

    assert report["cash_sessions"]["missing_bars"] == 1
    assert report["cash_sessions"]["missing_bar_opens_utc"] == [
        "2026-08-20T19:45:00+00:00"
    ]
    assert report["diagnosis"] == "cash_session_trade_evidence_incomplete"


def test_trade_gap_is_partitioned_by_cash_session_overlap() -> None:
    """Only a stream gap overlapping a required session is a cash-data defect."""
    rows: tuple[PublicTradeEvent | StreamGap, ...] = (
        *(
            _trade(index + 1, _START_MS + index * _BAR_MS)
            for index in range(_CASH_BARS)
        ),
        _gap(
            previous_ms=_START_MS + 2 * _BAR_MS,
            next_ms=_START_MS + 3 * _BAR_MS,
            detected_ms=_START_MS + 3 * _BAR_MS,
        ),
        _gap(
            previous_ms=_START_MS + _CASH_BARS * _BAR_MS,
            next_ms=_START_MS + (_CASH_BARS + 1) * _BAR_MS,
            detected_ms=_START_MS + (_CASH_BARS + 1) * _BAR_MS,
        ),
    )

    report = build_spcx_cash_open_source_quality(
        rows,
        start_ms=_START_MS,
        end_ms=_END_MS,
    )

    assert report["transport"]["declared_trade_gaps"] == 2
    assert report["transport"]["cash_session_overlapping_trade_gaps"] == 1
    assert report["diagnosis"] == "cash_session_trade_transport_gap"


def test_combined_channel_gap_is_not_silently_excluded() -> None:
    """A recorder-wide disconnect containing trades is still a trade gap."""
    rows: tuple[PublicTradeEvent | StreamGap, ...] = (
        *(
            _trade(index + 1, _START_MS + index * _BAR_MS)
            for index in range(_CASH_BARS)
        ),
        _gap(
            previous_ms=_START_MS + 2 * _BAR_MS,
            next_ms=_START_MS + 3 * _BAR_MS,
            detected_ms=_START_MS + 3 * _BAR_MS,
            channel="l2Book,trades,activeAssetCtx",
        ),
    )

    report = build_spcx_cash_open_source_quality(
        rows,
        start_ms=_START_MS,
        end_ms=_END_MS,
    )

    assert report["transport"]["declared_trade_gaps"] == 1
    assert report["transport"]["cash_session_overlapping_trade_gaps"] == 1
    assert (
        report["transport"]["cash_session_overlapping_trade_gap_duration_ms"] == 900_000
    )
    assert report["transport"]["cash_session_overlapping_gaps"] == [
        {
            "start_utc": "2026-08-20T14:00:00+00:00",
            "end_utc": "2026-08-20T14:15:00+00:00",
            "duration_ms": 900_000,
            "channel": "l2Book,trades,activeAssetCtx",
            "reason": "test_gap",
        }
    ]
    assert report["diagnosis"] == "cash_session_trade_transport_gap"


def _trade(trade_id: int, timestamp_ms: int) -> PublicTradeEvent:
    return PublicTradeEvent(
        symbol="xyz:SPCX",
        aggressor_side="buy",
        price=100.0,
        size=1.0,
        transaction_hash=f"0x{trade_id:064x}",
        exchange_ts_ms=timestamp_ms + 1,
        received_ts_ns=(timestamp_ms + 2) * 1_000_000,
        trade_id=trade_id,
        buyer="buyer",
        seller="seller",
    )


def _gap(
    *,
    previous_ms: int,
    next_ms: int,
    detected_ms: int,
    channel: str = "trades",
) -> StreamGap:
    return StreamGap(
        symbol="xyz:SPCX",
        channel=channel,
        reason="test_gap",
        detected_ts_ns=detected_ms * 1_000_000,
        previous_exchange_ts_ms=previous_ms,
        next_exchange_ts_ms=next_ms,
    )

"""Tests for exact prospective cash-open signal reconstruction."""

from __future__ import annotations

from dataclasses import replace
import json

import pandas as pd
import pytest

from hypervector.data.hl_events import PublicTradeEvent
from hypervector.research.hip3_cash_open_prospective import (
    Hip3CashOpenProspectiveSpec,
    build_hip3_cash_open_prospective_report,
)

_INTERVAL_MS = 900_000


def test_report_keeps_frozen_rule_and_reports_zero_entry_session() -> None:
    """A sub-threshold scorable Monday must remain a measured no-entry."""
    trades, start_ms, end_ms = _trade_window(monday_gap_bps=7.15)
    report = build_hip3_cash_open_prospective_report(
        trades=trades,
        start_ms=start_ms,
        end_ms=end_ms,
        observed_at_ms=end_ms + 1_000,
        spec=_spec(),
    )

    assert report["contract"]["execution_authority"] == "none"
    assert report["strategy_identity"]["gap_threshold_bps"] == 20.0
    assert report["coverage"]["scorable_cash_open_decisions"] == 1
    assert report["coverage"]["unscorable_cash_open_decisions"] == 1
    assert report["signals"]["entry_events"] == []
    assert json.dumps(report)
    assert report["strategy_identity"]["closed_session_dates"] == [
        "2026-06-19",
        "2026-07-03",
    ]


def test_report_reconstructs_exact_short_entry_without_tuning() -> None:
    """A gap above the frozen threshold must emit the exact short event."""
    trades, start_ms, end_ms = _trade_window(monday_gap_bps=30.0)
    report = build_hip3_cash_open_prospective_report(
        trades=trades,
        start_ms=start_ms,
        end_ms=end_ms,
        observed_at_ms=end_ms,
        spec=_spec(),
    )

    events = report["signals"]["entry_events"]
    assert len(events) == 1
    assert events[0]["side"] == "short"
    assert events[0]["opening_gap_bps"] == pytest.approx(30.0)


def test_duplicate_receipt_is_deduplicated_but_conflict_fails() -> None:
    """Local duplicate receipts cannot change venue OHLC or hide conflicts."""
    trades, start_ms, end_ms = _trade_window(monday_gap_bps=30.0)
    duplicate = replace(trades[-1], received_ts_ns=trades[-1].received_ts_ns + 1)
    report = build_hip3_cash_open_prospective_report(
        trades=(*trades, duplicate),
        start_ms=start_ms,
        end_ms=end_ms,
        observed_at_ms=end_ms,
        spec=_spec(),
    )
    assert report["source"]["duplicate_trade_rows"] == 1

    conflict = replace(duplicate, price=duplicate.price + 1.0)
    with pytest.raises(ValueError, match="conflicting public trade identity"):
        build_hip3_cash_open_prospective_report(
            trades=(*trades, conflict),
            start_ms=start_ms,
            end_ms=end_ms,
            observed_at_ms=end_ms,
            spec=_spec(),
        )


def _spec() -> Hip3CashOpenProspectiveSpec:
    return Hip3CashOpenProspectiveSpec(
        symbol="xyz:SPCX",
        provider_id="hip3_spcx_cash_open_gap_reversal_bidirectional_15m_research_v1",
        profile_id="spcx_cash_open_gap_reversal_15m_development_v1",
    )


def _trade_window(
    *, monday_gap_bps: float
) -> tuple[tuple[PublicTradeEvent, ...], int, int]:
    start = pd.Timestamp("2026-08-14T00:00:00Z")
    end = pd.Timestamp("2026-08-17T14:00:00Z")
    times = pd.date_range(start, end, freq="15min", inclusive="left")
    prior_close = pd.Timestamp("2026-08-14T19:45:00Z")
    monday_open = pd.Timestamp("2026-08-17T13:30:00Z")
    prices = [100.0] * len(times)
    prices[times.get_loc(prior_close)] = 100.0
    prices[times.get_loc(monday_open)] = 100.0 * (1.0 + monday_gap_bps / 10_000.0)
    trades = tuple(
        _trade(position, int(timestamp.timestamp() * 1_000), price)
        for position, (timestamp, price) in enumerate(zip(times, prices, strict=True))
    )
    return trades, int(start.timestamp() * 1_000), int(end.timestamp() * 1_000)


def _trade(trade_id: int, timestamp_ms: int, price: float) -> PublicTradeEvent:
    return PublicTradeEvent(
        symbol="xyz:SPCX",
        aggressor_side="buy",
        price=price,
        size=1.0,
        transaction_hash=f"0x{trade_id:064x}",
        exchange_ts_ms=timestamp_ms + 1,
        received_ts_ns=(timestamp_ms + 2) * 1_000_000,
        trade_id=trade_id,
        buyer="buyer",
        seller="seller",
    )

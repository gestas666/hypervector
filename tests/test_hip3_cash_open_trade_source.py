"""Receipt-causal public-trade bar source for the SPCX live candidate."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

import pytest
import pandas as pd

from hypervector.data.hl_events import PublicTradeEvent, StreamGap
from hypervector.live.hip3_cash_open_trade_source import (
    Hip3CashOpenTradeBarSource,
)
from hypervector.live.hip3_provider_availability import Hip3ObserverUnavailableError


class _Archive:
    def __init__(self, rows: tuple[object, ...]) -> None:
        self.rows = rows
        self.requested_end: datetime | None = None

    def replay_trade_window(self, start: datetime, end: datetime) -> tuple[object, ...]:
        del start
        self.requested_end = end
        return self.rows


def test_trade_source_requires_only_scheduled_cash_session_bars() -> None:
    """Weekend and overnight no-trade periods are not required strategy bars."""
    friday = pd.date_range(
        "2026-08-14T13:30:00Z",
        "2026-08-14T20:00:00Z",
        freq="15min",
        inclusive="left",
    )
    monday_open = pd.Timestamp("2026-08-17T13:30:00Z")
    expected = friday.append(pd.DatetimeIndex([monday_open])).as_unit("ms")
    rows = tuple(
        _trade(index + 1, int(timestamp.timestamp() * 1_000) + 1, 100.0)
        for index, timestamp in enumerate(expected)
    )
    source = Hip3CashOpenTradeBarSource(
        archive=_Archive(rows),
        symbol="xyz:SPCX",
        capture_start_ms=int(friday[0].timestamp() * 1_000),
    )

    frame = source.completed_bars(
        observed_at_ms=int(
            (monday_open + pd.Timedelta(minutes=15, seconds=5)).timestamp() * 1_000
        ),
        minimum_start_ms=int(friday[0].timestamp() * 1_000),
    )

    pd.testing.assert_index_equal(frame.index, expected, check_names=False)
    assert frame["gap_before_bars"].eq(0).all()


def test_trade_source_marks_combined_channel_gap_on_affected_cash_bar() -> None:
    """Recorder-wide gaps containing trades retain per-bar provenance."""
    opening = pd.Timestamp("2026-08-17T13:30:00Z")
    opening_ms = int(opening.timestamp() * 1_000)
    trade = _trade(1, opening_ms + 1, 100.0)
    gap = StreamGap(
        symbol="xyz:SPCX",
        channel="l2Book,trades,activeAssetCtx",
        detected_ts_ns=(opening_ms + 600_000) * 1_000_000,
        reason="test_disconnect",
        previous_exchange_ts_ms=opening_ms + 300_000,
        next_exchange_ts_ms=opening_ms + 600_000,
    )
    source = Hip3CashOpenTradeBarSource(
        archive=_Archive((trade, gap)),
        symbol="xyz:SPCX",
        capture_start_ms=opening_ms,
    )

    frame = source.completed_bars(
        observed_at_ms=opening_ms + 900_000,
        minimum_start_ms=opening_ms,
    )

    assert frame.loc[opening, "gap_before_bars"] == 1


def test_trade_source_retains_exact_trade_gap_as_bar_provenance() -> None:
    """An exact trade gap is a censored bar, not seven days of unavailability."""
    opening = pd.Timestamp("2026-08-17T13:30:00Z")
    opening_ms = int(opening.timestamp() * 1_000)
    trade = _trade(1, opening_ms + 1, 100.0)
    gap = StreamGap(
        symbol="xyz:SPCX",
        channel="trades",
        detected_ts_ns=(opening_ms + 600_000) * 1_000_000,
        reason="test_disconnect",
        previous_exchange_ts_ms=opening_ms + 300_000,
        next_exchange_ts_ms=opening_ms + 600_000,
    )
    source = Hip3CashOpenTradeBarSource(
        archive=_Archive((trade, gap)),
        symbol="xyz:SPCX",
        capture_start_ms=opening_ms,
    )

    frame = source.completed_bars(
        observed_at_ms=opening_ms + 900_000,
        minimum_start_ms=opening_ms,
    )

    assert frame.loc[opening, "gap_before_bars"] == 1


def test_trade_source_rejects_cross_symbol_gap_identity() -> None:
    """A gap from another market cannot censor SPCX evidence."""
    opening = pd.Timestamp("2026-08-17T13:30:00Z")
    opening_ms = int(opening.timestamp() * 1_000)
    gap = StreamGap(
        symbol="xyz:SP500",
        channel="trades",
        detected_ts_ns=(opening_ms + 600_000) * 1_000_000,
        reason="test_disconnect",
        previous_exchange_ts_ms=opening_ms + 300_000,
        next_exchange_ts_ms=opening_ms + 600_000,
    )
    source = Hip3CashOpenTradeBarSource(
        archive=_Archive((_trade(1, opening_ms + 1, 100.0), gap)),
        symbol="xyz:SPCX",
        capture_start_ms=opening_ms,
    )

    with pytest.raises(ValueError, match="gap identity"):
        source.completed_bars(
            observed_at_ms=opening_ms + 900_000,
            minimum_start_ms=opening_ms,
        )


def test_trade_source_ignores_gap_detected_after_receipt_cutoff() -> None:
    """Future gap receipts cannot contaminate a completed causal prefix."""
    opening = pd.Timestamp("2026-08-17T13:30:00Z")
    opening_ms = int(opening.timestamp() * 1_000)
    boundary_ms = opening_ms + 900_000
    gap = StreamGap(
        symbol="xyz:SPCX",
        channel="trades",
        detected_ts_ns=(boundary_ms + 1) * 1_000_000,
        reason="future_disconnect",
        previous_exchange_ts_ms=opening_ms + 300_000,
        next_exchange_ts_ms=opening_ms + 600_000,
    )
    source = Hip3CashOpenTradeBarSource(
        archive=_Archive((_trade(1, opening_ms + 1, 100.0), gap)),
        symbol="xyz:SPCX",
        capture_start_ms=opening_ms,
    )

    frame = source.completed_bars(
        observed_at_ms=boundary_ms,
        minimum_start_ms=opening_ms,
    )

    assert frame.loc[opening, "gap_before_bars"] == 0


def test_trade_source_marks_missing_required_bar_on_next_cash_bar() -> None:
    """A missing prior close stays absent and censors the next opening bar."""
    friday = pd.date_range(
        "2026-08-14T13:30:00Z",
        "2026-08-14T19:45:00Z",
        freq="15min",
        inclusive="left",
    )
    monday_open = pd.Timestamp("2026-08-17T13:30:00Z")
    observed = friday.append(pd.DatetimeIndex([monday_open]))
    rows = tuple(
        _trade(index + 1, int(timestamp.timestamp() * 1_000) + 1, 100.0)
        for index, timestamp in enumerate(observed)
    )
    source = Hip3CashOpenTradeBarSource(
        archive=_Archive(rows),
        symbol="xyz:SPCX",
        capture_start_ms=int(friday[0].timestamp() * 1_000),
    )

    frame = source.completed_bars(
        observed_at_ms=int(
            (monday_open + pd.Timedelta(minutes=15)).timestamp() * 1_000
        ),
        minimum_start_ms=int(friday[0].timestamp() * 1_000),
    )

    assert pd.Timestamp("2026-08-14T19:45:00Z") not in frame.index
    assert frame.loc[monday_open, "gap_before_bars"] == 1


def test_trade_source_reads_gaps_through_the_receipt_cutoff() -> None:
    """A gap detected just after bar close must be visible before evaluation."""
    opening = pd.Timestamp("2026-08-17T13:30:00Z")
    opening_ms = int(opening.timestamp() * 1_000)
    boundary_ms = opening_ms + 900_000
    observed_ms = boundary_ms + 5_000
    archive = _Archive((_trade(1, opening_ms + 1, 100.0),))
    source = Hip3CashOpenTradeBarSource(
        archive=archive,
        symbol="xyz:SPCX",
        capture_start_ms=opening_ms,
    )

    source.completed_bars(
        observed_at_ms=observed_ms,
        minimum_start_ms=opening_ms,
    )

    assert archive.requested_end == datetime.fromtimestamp(
        observed_ms / 1_000, tz=opening.tz
    )


def test_trade_source_uses_live_early_close_schedule() -> None:
    """A declared half-day must not become missing bars before Monday's open."""
    friday = pd.date_range(
        "2026-11-27T14:30:00Z",
        "2026-11-27T18:00:00Z",
        freq="15min",
        inclusive="left",
    )
    monday_open = pd.Timestamp("2026-11-30T14:30:00Z")
    observed = friday.append(pd.DatetimeIndex([monday_open]))
    rows = tuple(
        _trade(index + 1, int(timestamp.timestamp() * 1_000) + 1, 100.0)
        for index, timestamp in enumerate(observed)
    )
    source = Hip3CashOpenTradeBarSource(
        archive=_Archive(rows),
        symbol="xyz:SPCX",
        capture_start_ms=int(friday[0].timestamp() * 1_000),
    )

    frame = source.completed_bars(
        observed_at_ms=int(
            (monday_open + pd.Timedelta(minutes=15)).timestamp() * 1_000
        ),
        minimum_start_ms=int(friday[0].timestamp() * 1_000),
    )

    assert frame.loc[monday_open, "gap_before_bars"] == 0


def test_trade_source_orders_same_millisecond_by_trade_id_and_deduplicates() -> None:
    """Venue identity, not receipt ordering, must define exact OHLC."""
    opening_ms = int(pd.Timestamp("2026-08-17T13:30:00Z").timestamp() * 1_000)
    first = _trade(1, opening_ms + 1, 100.0)
    second = _trade(2, opening_ms + 1, 101.0)
    duplicate = replace(second, received_ts_ns=second.received_ts_ns + 1)
    source = Hip3CashOpenTradeBarSource(
        archive=_Archive((second, first, duplicate)),
        symbol="xyz:SPCX",
        capture_start_ms=opening_ms,
    )

    frame = source.completed_bars(
        observed_at_ms=opening_ms + 900_000,
        minimum_start_ms=opening_ms,
    )

    assert frame.iloc[0][["open", "close"]].tolist() == [100.0, 101.0]
    assert frame.iloc[0]["public_trade_count"] == 2


def test_trade_source_rejects_conflicts_and_future_receipts() -> None:
    """Conflicting or hindsight-contaminated source evidence fails closed."""
    opening = pd.Timestamp("2026-08-17T13:30:00Z")
    opening_ms = int(opening.timestamp() * 1_000)
    boundary_ms = opening_ms + 900_000
    first = _trade(1, opening_ms + 1, 100.0)
    conflict = replace(first, price=99.0, received_ts_ns=first.received_ts_ns + 1)
    source = Hip3CashOpenTradeBarSource(
        archive=_Archive((first, conflict)),
        symbol="xyz:SPCX",
        capture_start_ms=opening_ms,
    )
    with pytest.raises(ValueError, match="conflicting"):
        source.completed_bars(
            observed_at_ms=boundary_ms,
            minimum_start_ms=opening_ms,
        )

    future = replace(first, received_ts_ns=(boundary_ms + 1) * 1_000_000)
    future_source = Hip3CashOpenTradeBarSource(
        archive=_Archive((future,)),
        symbol="xyz:SPCX",
        capture_start_ms=opening_ms,
    )
    with pytest.raises(Hip3ObserverUnavailableError) as unavailable:
        future_source.completed_bars(
            observed_at_ms=boundary_ms,
            minimum_start_ms=opening_ms,
        )
    assert unavailable.value.reason == "cash_open_trade_rows_unavailable"

    sparse = future_source.completed_bars(
        observed_at_ms=boundary_ms + 900_000,
        minimum_start_ms=opening_ms,
    )
    pd.testing.assert_index_equal(
        sparse.index,
        pd.DatetimeIndex([opening]).as_unit("ms"),
        check_names=False,
    )


def test_trade_source_maps_no_cash_session_trade_to_availability() -> None:
    """Overnight-only trades cannot become an unclassified provider fault."""
    start_ms = int(pd.Timestamp("2026-08-17T00:00:00Z").timestamp() * 1_000)
    opening_ms = int(pd.Timestamp("2026-08-17T13:30:00Z").timestamp() * 1_000)
    source = Hip3CashOpenTradeBarSource(
        archive=_Archive((_trade(1, start_ms + 1, 100.0),)),
        symbol="xyz:SPCX",
        capture_start_ms=start_ms,
    )

    with pytest.raises(Hip3ObserverUnavailableError) as unavailable:
        source.completed_bars(
            observed_at_ms=opening_ms + 900_000,
            minimum_start_ms=start_ms,
        )

    assert unavailable.value.reason == "cash_open_trade_bars_incomplete"


def _trade(trade_id: int, timestamp_ms: int, price: float) -> PublicTradeEvent:
    return PublicTradeEvent(
        symbol="xyz:SPCX",
        aggressor_side="buy",
        price=price,
        size=1.0,
        transaction_hash=f"0x{trade_id:064x}",
        exchange_ts_ms=timestamp_ms,
        received_ts_ns=(timestamp_ms + 1) * 1_000_000,
        trade_id=trade_id,
        buyer="buyer",
        seller="seller",
    )

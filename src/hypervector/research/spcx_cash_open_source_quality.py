"""Attribute SPCX public-trade completeness to cash and non-cash intervals."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from hypervector.data.hl_events import PublicTradeEvent, StreamGap

_BAR_MS = 15 * 60 * 1_000
_CASH_OPEN_MINUTE = 9 * 60 + 30
_CASH_CLOSE_MINUTE = 16 * 60
_SPCX_SYMBOL = "xyz:SPCX"
_TRADE_CHANNEL = "trades"
_NEW_YORK = ZoneInfo("America/New_York")


def build_spcx_cash_open_source_quality(
    rows: Sequence[object],
    *,
    start_ms: int,
    end_ms: int,
) -> dict[str, object]:
    """Build a report that separates cash-session from all-hours completeness."""
    _validate_window(start_ms, end_ms)
    all_opens = tuple(range(start_ms, end_ms, _BAR_MS))
    cash_opens = tuple(open_ms for open_ms in all_opens if _is_cash_bar(open_ms))
    trades = tuple(row for row in rows if _is_spcx_trade(row))
    observed = {_bar_open(row.exchange_ts_ms) for row in trades}
    observed_in_window = observed.intersection(all_opens)
    gaps = tuple(row for row in rows if _is_spcx_trade_gap(row))
    cash_gaps = tuple(gap for gap in gaps if _overlaps_cash_bar(gap, cash_opens))
    cash_gap_records = [_gap_record(gap) for gap in cash_gaps]
    missing_all = tuple(sorted(set(all_opens).difference(observed_in_window)))
    missing_cash = tuple(sorted(set(cash_opens).difference(observed_in_window)))
    return {
        "window": {
            "start_utc": _iso_utc(start_ms),
            "end_utc": _iso_utc(end_ms),
            "bar_interval_minutes": 15,
        },
        "raw_public_trade_rows": len(trades),
        "all_hours": _coverage(all_opens, observed_in_window, missing_all),
        "cash_sessions": {
            **_coverage(cash_opens, observed_in_window, missing_cash),
            "sessions": _session_coverage(cash_opens, observed_in_window),
        },
        "transport": {
            "declared_trade_gaps": len(gaps),
            "cash_session_overlapping_trade_gaps": len(cash_gaps),
            "cash_session_overlapping_trade_gap_duration_ms": sum(
                int(record["duration_ms"]) for record in cash_gap_records
            ),
            "cash_session_overlapping_gaps": cash_gap_records,
        },
        "diagnosis": _diagnosis(missing_all, missing_cash, cash_gaps),
    }


def _validate_window(start_ms: int, end_ms: int) -> None:
    if isinstance(start_ms, bool) or isinstance(end_ms, bool):
        raise TypeError("start_ms and end_ms must be integer epoch milliseconds")
    if start_ms <= 0 or end_ms <= start_ms:
        raise ValueError("cash-open quality window must be positive and ordered")
    if start_ms % _BAR_MS or end_ms % _BAR_MS:
        raise ValueError("cash-open quality window must align to 15-minute bars")


def _is_spcx_trade(row: object) -> bool:
    return (
        isinstance(row, PublicTradeEvent)
        and row.symbol == _SPCX_SYMBOL
        and row.source == "hyperliquid_ws_trades"
    )


def _is_spcx_trade_gap(row: object) -> bool:
    return (
        isinstance(row, StreamGap)
        and row.symbol == _SPCX_SYMBOL
        and _TRADE_CHANNEL in {channel.strip() for channel in row.channel.split(",")}
    )


def _bar_open(timestamp_ms: int) -> int:
    return timestamp_ms - timestamp_ms % _BAR_MS


def _is_cash_bar(open_ms: int) -> bool:
    local = datetime.fromtimestamp(open_ms / 1_000, tz=UTC).astimezone(_NEW_YORK)
    minute = local.hour * 60 + local.minute
    return local.weekday() < 5 and _CASH_OPEN_MINUTE <= minute < _CASH_CLOSE_MINUTE


def _overlaps_cash_bar(gap: StreamGap, cash_opens: Sequence[int]) -> bool:
    detected_ms = gap.detected_ts_ns // 1_000_000
    left = gap.previous_exchange_ts_ms or detected_ms
    right = gap.next_exchange_ts_ms or detected_ms
    lower, upper = sorted((left, right))
    return any(lower < open_ms + _BAR_MS and upper > open_ms for open_ms in cash_opens)


def _gap_record(gap: StreamGap) -> dict[str, object]:
    detected_ms = gap.detected_ts_ns // 1_000_000
    left = gap.previous_exchange_ts_ms or detected_ms
    right = gap.next_exchange_ts_ms or detected_ms
    lower, upper = sorted((left, right))
    return {
        "start_utc": _iso_utc(lower),
        "end_utc": _iso_utc(upper),
        "duration_ms": upper - lower,
        "channel": gap.channel,
        "reason": gap.reason,
    }


def _coverage(
    expected: Sequence[int], observed: set[int], missing: Sequence[int]
) -> dict[str, object]:
    expected_count = len(expected)
    observed_count = len(set(expected).intersection(observed))
    completeness = observed_count / expected_count if expected_count else 1.0
    return {
        "expected_bars": expected_count,
        "observed_bars": observed_count,
        "missing_bars": len(missing),
        "completeness": completeness,
        "missing_bar_opens_utc": [_iso_utc(open_ms) for open_ms in missing],
    }


def _session_coverage(
    cash_opens: Sequence[int], observed: set[int]
) -> list[dict[str, object]]:
    by_date: dict[str, list[int]] = {}
    for open_ms in cash_opens:
        local_date = (
            datetime.fromtimestamp(open_ms / 1_000, tz=UTC).astimezone(_NEW_YORK).date()
        )
        by_date.setdefault(local_date.isoformat(), []).append(open_ms)
    return [_one_session(date, opens, observed) for date, opens in by_date.items()]


def _one_session(
    local_date: str, opens: Sequence[int], observed: set[int]
) -> dict[str, object]:
    missing = tuple(open_ms for open_ms in opens if open_ms not in observed)
    return {
        "new_york_date": local_date,
        "expected_bars": len(opens),
        "observed_bars": len(opens) - len(missing),
        "missing_bars": len(missing),
    }


def _diagnosis(
    missing_all: Sequence[int],
    missing_cash: Sequence[int],
    cash_gaps: Sequence[StreamGap],
) -> str:
    if cash_gaps:
        return "cash_session_trade_transport_gap"
    if missing_cash:
        return "cash_session_trade_evidence_incomplete"
    if missing_all:
        return "irrelevant_non_cash_no_trade_bars_reject_source"
    return "complete_for_current_all_hours_contract"


def _iso_utc(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1_000, tz=UTC).isoformat()

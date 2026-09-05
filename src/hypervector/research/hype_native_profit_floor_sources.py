"""Exact source adapters for the native-HYPE profit-floor transfer."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math

from hypervector.research.hype_native_profit_floor_transfer import (
    FundingCashflow,
    NativeLifecycle,
    ProfitFloorBar,
)

Record = Mapping[str, object]
_MINUTE_MS = 60_000
_PROSPECTIVE_MODE = "hype_native_v54_prospective_lifecycle_report_only"
_RESOLUTION_MODE = "hype_native_v54_exact_post_close_resolution_report_only"


@dataclass(frozen=True)
class PreparedNativeFloorInput:
    """One reconciled lifecycle with completed candles and causal books."""

    lifecycle: NativeLifecycle
    bars: tuple[ProfitFloorBar, ...]
    books: tuple[Record, ...]


def prepare_closed_native_floor_input(
    path_report: Record,
    funded_report: Record,
    asset_records: Sequence[Record],
    cohort_records: Sequence[Record],
    *,
    lifecycle_id: str,
) -> PreparedNativeFloorInput:
    """Prepare one immutable earlier native lifecycle for floor scoring."""
    identity = _mapping(path_report.get("identity"), "path identity")
    _require_hype_long(identity)
    run_id = _text(identity.get("run_id"), "path run id")
    path = _mapping(path_report.get("execution_path"), "execution path")
    entry = _integer(path.get("entry_book_time_ms"), "entry time")
    if _integer(funded_report.get("entry_book_time_ms"), "funded entry") != entry:
        raise ValueError("HYPE floor funded entry differs from path entry")
    exit_time = _integer(funded_report.get("exit_book_time_ms"), "funded exit")
    lifecycle = NativeLifecycle(
        lifecycle_id=lifecycle_id,
        entry_time_ms=entry,
        natural_exit_time_ms=exit_time,
        as_of_ms=exit_time,
        entry_price=_positive(path.get("entry_price"), "entry price"),
        quantity=_positive(path.get("entry_quantity"), "entry quantity"),
        actual_net_after_funding_usd=_number(
            funded_report.get("net_pnl_usd_after_funding"), "funded net PnL"
        ),
        actual_exit_reason=_closed_exit_reason(path, funded_report),
        funding_cashflows=_funding_events(funded_report),
        funding_complete_through_ms=exit_time,
    )
    return _prepared(lifecycle, cohort_records, asset_records, run_id)


def prepare_prospective_native_floor_input(
    status: Record,
    observer_records: Sequence[Record],
    *,
    resolution: Record | None = None,
) -> PreparedNativeFloorInput:
    """Prepare the current prospective lifecycle, exact only after resolution."""
    _require_report_only(status, _PROSPECTIVE_MODE)
    identity = _mapping(status.get("identity"), "prospective identity")
    if identity.get("symbol") != "HYPE":
        raise ValueError("HYPE floor prospective symbol differs")
    run_id = _text(identity.get("run_id"), "prospective run id")
    rows = _records(status.get("lifecycles"), "prospective lifecycles")
    if len(rows) != 1:
        raise ValueError("HYPE floor requires exactly one prospective lifecycle")
    row = rows[0]
    resolved = _prospective_resolution(resolution, identity, row)
    lifecycle = _prospective_lifecycle(run_id, row, resolved)
    return _prepared(lifecycle, observer_records, observer_records, run_id)


def _prospective_lifecycle(
    run_id: str, row: Record, resolved: Record | None
) -> NativeLifecycle:
    entry = _integer(row.get("entry_book_time_ms"), "prospective entry")
    exit_value = row.get("exit_book_time_ms")
    exit_time = None if exit_value is None else _integer(exit_value, "prospective exit")
    as_of = _integer(row.get("current_book_time_ms"), "prospective as-of")
    actual = (
        None
        if resolved is None
        else _number(resolved.get("net_pnl_usd_after_funding"), "resolved net PnL")
    )
    return NativeLifecycle(
        lifecycle_id=f"HYPE:{run_id}:{entry}",
        entry_time_ms=entry,
        natural_exit_time_ms=exit_time,
        as_of_ms=max(as_of, exit_time or as_of),
        entry_price=_positive(row.get("entry_price"), "prospective entry price"),
        quantity=_positive(row.get("entry_quantity"), "prospective quantity"),
        actual_net_after_funding_usd=actual,
        actual_exit_reason=(
            None if exit_time is None else _text(row.get("exit_reason"), "exit reason")
        ),
        funding_cashflows=() if resolved is None else _funding_events(resolved),
        funding_complete_through_ms=exit_time if resolved is not None else None,
    )


def _prospective_resolution(
    resolution: Record | None, identity: Record, lifecycle: Record
) -> Record | None:
    if resolution is None:
        return None
    _require_report_only(resolution, _RESOLUTION_MODE)
    resolved_identity = _mapping(resolution.get("identity"), "resolution identity")
    for field in ("run_id", "symbol"):
        if resolved_identity.get(field) != identity.get(field):
            raise ValueError(f"HYPE floor resolution {field} differs")
    rows = _records(resolution.get("lifecycles"), "resolved lifecycles")
    entry = _integer(lifecycle.get("entry_book_time_ms"), "prospective entry")
    matches = [row for row in rows if row.get("entry_book_time_ms") == entry]
    if len(matches) != 1:
        raise ValueError("HYPE floor resolution lifecycle differs")
    return matches[0]


def _prepared(
    lifecycle: NativeLifecycle,
    candle_records: Sequence[Record],
    book_records: Sequence[Record],
    run_id: str,
) -> PreparedNativeFloorInput:
    bars = _completed_bars(candle_records, run_id, lifecycle)
    books = _normalized_books(book_records, run_id)
    return PreparedNativeFloorInput(lifecycle, bars, books)


def _completed_bars(
    records: Sequence[Record], run_id: str, lifecycle: NativeLifecycle
) -> tuple[ProfitFloorBar, ...]:
    index: dict[int, ProfitFloorBar] = {}
    for event in records:
        if event.get("event_type") != "market_candles" or event.get("run_id") != run_id:
            continue
        values = _mapping(event.get("payload"), "market candle payload")
        if values.get("timeframe") != "1m":
            continue
        symbols = _mapping(values.get("bars"), "market candle symbols")
        for raw in _records(symbols.get("HYPE", []), "HYPE candles"):
            bar = _profit_floor_bar(raw)
            prior = index.get(bar.timestamp_ms)
            if prior is not None and prior != bar:
                raise ValueError("conflicting duplicate HYPE profit-floor candle")
            index[bar.timestamp_ms] = bar
    boundary = lifecycle.natural_exit_time_ms or lifecycle.as_of_ms
    first = lifecycle.entry_time_ms // _MINUTE_MS * _MINUTE_MS + _MINUTE_MS
    last = (boundary - _MINUTE_MS) // _MINUTE_MS * _MINUTE_MS
    return tuple(
        index[value]
        for value in range(first, last + _MINUTE_MS, _MINUTE_MS)
        if value in index
    )


def _normalized_books(records: Sequence[Record], run_id: str) -> tuple[Record, ...]:
    books: list[Record] = []
    for event in records:
        if event.get("run_id") != run_id:
            continue
        if event.get("event_type") == "market_books":
            values = _mapping(event.get("payload"), "market books payload")
            raw = _mapping(
                _mapping(values.get("books"), "market books").get("HYPE"), "HYPE book"
            )
            books.append(_book_record(event, raw, run_id))
        elif event.get("event_type") == "book_observation":
            raw = _mapping(event.get("payload"), "book payload")
            symbol = raw.get("symbol")
            if symbol not in {None, "HYPE"}:
                raise ValueError("HYPE floor asset book symbol differs")
            if symbol is None and not str(event.get("profile_id", "")).lower().endswith(
                "_hype"
            ):
                raise ValueError(
                    "HYPE floor unlabeled asset book lacks profile binding"
                )
            books.append(_book_record(event, raw, run_id))
    return tuple(books)


def _book_record(event: Record, raw: Record, run_id: str) -> dict[str, object]:
    payload = dict(raw)
    payload["symbol"] = "HYPE"
    return {
        "event_type": "book_observation",
        "run_id": run_id,
        "payload": payload,
        "observed_at_utc": event.get("observed_at_utc"),
    }


def _profit_floor_bar(raw: Record) -> ProfitFloorBar:
    return ProfitFloorBar(
        _integer(raw.get("timestamp_ms"), "candle timestamp"),
        _positive(raw.get("open"), "candle open"),
        _positive(raw.get("high"), "candle high"),
        _positive(raw.get("low"), "candle low"),
        _positive(raw.get("close"), "candle close"),
    )


def _funding_events(report: Record) -> tuple[FundingCashflow, ...]:
    return tuple(
        FundingCashflow(
            _integer(row.get("event_ts_ms"), "funding timestamp"),
            _number(row.get("cashflow_usd"), "funding cashflow"),
        )
        for row in _records(report.get("funding_events"), "funding events")
    )


def _closed_exit_reason(path: Record, funded: Record) -> str:
    reason = path.get("exit_reason")
    if isinstance(reason, str) and reason:
        return reason
    if funded.get("exit_basis") == "fixed_horizon_bbo_proxy":
        return "maximum_hold"
    raise ValueError("HYPE floor closed lifecycle lacks an exact exit reason")


def _require_hype_long(identity: Record) -> None:
    if identity.get("symbol") != "HYPE" or identity.get("side") != "long":
        raise ValueError("HYPE floor path identity must be HYPE long")


def _require_report_only(report: Record, mode: str) -> None:
    contract = _mapping(report.get("contract"), "report contract")
    if (
        report.get("mode") != mode
        or contract.get("report_only") is not True
        or contract.get("execution_authority") != "none"
    ):
        raise ValueError("HYPE floor report-only source contract is invalid")


def _records(value: object, label: str) -> tuple[Record, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"HYPE floor {label} must be an object array")
    rows = tuple(value)
    if any(not isinstance(row, Mapping) for row in rows):
        raise ValueError(f"HYPE floor {label} must be an object array")
    return rows  # type: ignore[return-value]


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"HYPE floor {label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"HYPE floor {label} must be non-empty text")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"HYPE floor {label} must be a nonnegative integer")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"HYPE floor {label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"HYPE floor {label} must be finite")
    return result


def _positive(value: object, label: str) -> float:
    result = _number(value, label)
    if result <= 0.0:
        raise ValueError(f"HYPE floor {label} must be positive")
    return result

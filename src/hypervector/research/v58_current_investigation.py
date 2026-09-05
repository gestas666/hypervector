"""Context-aware highest-value investigation for the V58 research loop."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from math import isfinite

from hypervector.research.v58_live_backend_context import LiveBackendContext
from hypervector.research.v58_lifecycle_capture import highest_value_investigation
from hypervector.research.v58_route_opportunity import RouteOpportunityCollection

Record = Mapping[str, object]

_OPEN_NEXT_ACTION = (
    "reconcile_authoritative_close_then_compare_frozen_exit_alternatives"
)
_OPEN_MINIMUM_EVIDENCE = {
    "diagnostic_update": (
        "one technically complete authoritative close with exact exit fill, fees, "
        "funding, completed-path MFE/MAE/giveback, and frozen profit-lock comparisons"
    ),
    "live_change": (
        "a preregistered source-compatible sample covering both configured sides "
        "with positive after-cost and largest-winner-removed results"
    ),
}


def attach_live_closed_lifecycles_to_ledger(
    report: dict[str, object], live_closed: Record
) -> None:
    """Persist exact current-run closes in their matching hypothesis rows."""
    _require_report_only(report)
    if live_closed.get("execution_authority") != "none":
        raise ValueError("V58 live-close evidence has execution authority")
    trades = _records(live_closed.get("trades"), "live-close trades")
    if live_closed.get("closed_lifecycles") != len(trades):
        raise ValueError("V58 live-close lifecycle count is inconsistent")
    ledger = _mutable_rows(report.get("hypothesis_ledger"), "hypothesis ledger")
    grouped: dict[str, list[Record]] = {}
    identities: set[str] = set()
    for trade in trades:
        symbol = _text(trade.get("symbol"), "live-close symbol")
        strategy = _text(trade.get("strategy_id"), "live-close strategy")
        lifecycle = _text(trade.get("lifecycle_id"), "live-close lifecycle")
        if lifecycle in identities:
            raise ValueError("V58 live-close lifecycle is duplicated")
        identities.add(lifecycle)
        grouped.setdefault(f"{strategy}|{symbol}", []).append(trade)
    for route, rows in grouped.items():
        _attach_closed_route(ledger, route, rows)


def attach_live_open_lifecycles_to_ledger(
    report: dict[str, object], live_open: Record
) -> None:
    """Make exact current opens canonical while retaining prior evidence state."""
    _require_report_only(report)
    if live_open.get("execution_authority") != "none":
        raise ValueError("V58 live-open evidence has execution authority")
    if live_open.get("actual_exit_fills_claimed") is not False:
        raise ValueError("V58 live-open evidence claims exit fills")
    trades = _records(live_open.get("trades"), "live-open trades")
    if live_open.get("open_lifecycles") != len(trades):
        raise ValueError("V58 live-open lifecycle count is inconsistent")
    ledger = _mutable_rows(report.get("hypothesis_ledger"), "hypothesis ledger")
    for trade in trades:
        _attach_open_trade(ledger, trade)


def _attach_open_trade(ledger: list[dict[str, object]], trade: Record) -> None:
    symbol = _text(trade.get("symbol"), "live-open symbol")
    strategy = _text(trade.get("strategy_id"), "live-open strategy")
    route = f"{strategy}|{symbol}"
    matches = [row for row in ledger if row.get("route") == route]
    if len(matches) != 1:
        raise ValueError("V58 live-open route is absent or duplicated")
    row = matches[0]
    if "current_live_lifecycle" in row:
        raise ValueError("V58 live-open lifecycle is already attached")
    _archive_capture_state(row)
    resolved = row.get("current_run_resolved_lifecycles", [])
    if not isinstance(resolved, list):
        raise ValueError("V58 resolved live lifecycles must be an array")
    row.update(
        {
            "status": "being_tested",
            "watch_state": "open_protected",
            "evidence_state": "open_exact_live_lifecycle",
            "technical_complete": True,
            "pending_lifecycles": 1,
            "resolved_lifecycles": len(resolved),
            "current_live_lifecycle": _live_summary(trade, symbol),
            "automatic_live_change": False,
        }
    )
    row.setdefault("next_action", _OPEN_NEXT_ACTION)
    row.setdefault("minimum_additional_evidence", dict(_OPEN_MINIMUM_EVIDENCE))


def _attach_closed_route(
    ledger: list[dict[str, object]], route: str, trades: Sequence[Record]
) -> None:
    matches = [row for row in ledger if row.get("route") == route]
    if len(matches) != 1:
        raise ValueError("V58 live-close route is absent or duplicated")
    row = matches[0]
    if "current_run_resolved_lifecycles" in row:
        raise ValueError("V58 live-close lifecycles are already attached")
    _archive_capture_state(row)
    summaries = sorted(
        (_closed_summary(trade) for trade in trades),
        key=lambda value: int(value["exit_time_ms"]),
    )
    row.update(
        {
            "status": "being_tested",
            "watch_state": "resolved_review_due",
            "evidence_state": "resolved_exact_live_lifecycle",
            "technical_complete": True,
            "pending_lifecycles": 0,
            "resolved_lifecycles": len(summaries),
            "current_run_resolved_lifecycles": summaries,
            "automatic_live_change": False,
        }
    )


def _archive_capture_state(row: dict[str, object]) -> None:
    if "historical_capture_state" in row:
        return
    row["historical_capture_state"] = {
        key: row.get(key)
        for key in (
            "watch_state",
            "evidence_state",
            "technical_complete",
            "pending_lifecycles",
            "resolved_lifecycles",
        )
    }


def _live_summary(trade: Record, symbol: str) -> dict[str, object]:
    lifecycle = _text(trade.get("lifecycle_id"), "live-open lifecycle id")
    if not lifecycle.startswith(f"{symbol}:"):
        raise ValueError("V58 live-open lifecycle identity differs")
    side = _text(trade.get("side"), "live-open side")
    if side not in {"long", "short"}:
        raise ValueError("V58 live-open side is invalid")
    if trade.get("actual_entry_fill_claim") is not True:
        raise ValueError("V58 live-open entry fill is not exact")
    if trade.get("actual_exit_fill_claim") is not False:
        raise ValueError("V58 live-open trade claims an exit fill")
    return {
        "state": "open_protected",
        "lifecycle_id": lifecycle,
        "side": side,
        "actual_entry_fill_claim": True,
        "actual_exit_fill_claim": False,
        "entry_price": _positive_number(trade.get("entry_price"), "entry price"),
        "entry_size": _positive_number(trade.get("entry_size"), "entry size"),
        "entry_time_ms": _positive_integer(trade.get("entry_time_ms"), "entry time"),
        **_live_path_context(trade),
        "marked_net_pnl_usd": _number(trade.get("marked_net_pnl_usd"), "marked PnL"),
        "protective_stop_oid": _positive_integer(
            trade.get("protective_stop_oid"), "protective stop oid"
        ),
        "protective_stop_trigger_price": _positive_number(
            trade.get("protective_stop_trigger_price"), "protective stop price"
        ),
        "maximum_hold_seconds": _positive_integer(
            trade.get("maximum_hold_seconds"), "maximum hold"
        ),
        "deadline_timestamp_ms": _positive_integer(
            trade.get("deadline_timestamp_ms"), "hold deadline"
        ),
        "profit_lock_policy": _text(trade.get("profit_lock_policy"), "profit lock"),
        "source": "active_live_checkpoint",
    }


def _live_path_context(trade: Record) -> dict[str, object]:
    execution = _mapping(trade.get("entry_execution_quality"), "entry execution")
    path = _mapping(trade.get("actual_completed_path"), "completed path")
    protection = _mapping(trade.get("profit_protection_estimate"), "profit protection")
    challenger = _mapping(trade.get("profit_lock_challenger"), "lock challenger")
    if execution.get("measurement_scope") != "actual_venue_entry_fill":
        raise ValueError("V58 live-open entry execution scope differs")
    if path.get("measurement_scope") != "actual_fill_completed_candle_path":
        raise ValueError("V58 live-open completed path scope differs")
    if path.get("continuous_path_claim") is not False:
        raise ValueError("V58 live-open path claims continuous coverage")
    if protection.get("actual_exit_fill_claim") is not False:
        raise ValueError("V58 live-open protection claims an exit fill")
    if challenger.get("execution_authority") != "none":
        raise ValueError("V58 live-open lock challenger has authority")
    if challenger.get("actual_exit_fill_claim") is not False:
        raise ValueError("V58 live-open lock challenger claims an exit fill")
    _text(challenger.get("status"), "lock challenger status")
    _mapping(challenger.get("policies"), "lock challenger policies")
    return {
        "entry_execution_quality": dict(execution),
        "actual_completed_path": dict(path),
        "profit_protection_estimate": dict(protection),
        "profit_lock_challenger": dict(challenger),
    }


def _closed_summary(trade: Record) -> dict[str, object]:
    symbol = _text(trade.get("symbol"), "live-close symbol")
    lifecycle = _text(trade.get("lifecycle_id"), "live-close lifecycle id")
    if not lifecycle.startswith(f"{symbol}:"):
        raise ValueError("V58 live-close lifecycle identity differs")
    side = _text(trade.get("side"), "live-close side")
    if side not in {"long", "short"}:
        raise ValueError("V58 live-close side is invalid")
    exact = (
        trade.get("actual_entry_fill_claim") is True
        and trade.get("actual_exit_fill_claim") is True
        and trade.get("technical_complete") is True
    )
    if not exact:
        raise ValueError("V58 live-close fill or technical evidence is incomplete")
    entry_time = _positive_integer(trade.get("entry_time_ms"), "entry time")
    exit_time = _positive_integer(trade.get("exit_time_ms"), "exit time")
    if exit_time < entry_time:
        raise ValueError("V58 live-close timestamps are inconsistent")
    capture = _closed_hold_capture(trade)
    profit_lock = _closed_profit_lock(trade)
    return {
        "lifecycle_id": lifecycle,
        "side": side,
        "actual_entry_fill_claim": True,
        "actual_exit_fill_claim": True,
        "entry_price": _positive_number(trade.get("entry_price"), "entry price"),
        "entry_time_ms": entry_time,
        "exit_price": _positive_number(trade.get("exit_price"), "exit price"),
        "exit_time_ms": exit_time,
        "exit_reason": _text(trade.get("exit_reason"), "exit reason"),
        "net_pnl_usd": _number(trade.get("net_pnl_usd"), "net PnL"),
        "fees_usd": _nonnegative_number(trade.get("fees_usd"), "fees"),
        "funding_usd": _number(trade.get("funding_usd"), "funding"),
        "completed_hold_capture": capture,
        "profit_lock_challenger": profit_lock,
        "technical_complete": True,
        "source": "active_live_checkpoint",
    }


def _closed_hold_capture(trade: Record) -> dict[str, object]:
    capture = _mapping(trade.get("completed_hold_capture"), "closed hold capture")
    if capture.get("status") != "resolved":
        raise ValueError("V58 live-close hold capture is unresolved")
    _positive_integer(capture.get("completed_bars"), "closed hold bars")
    for key in (
        "maximum_favorable_excursion_bps",
        "maximum_adverse_excursion_bps",
        "peak_giveback_bps",
    ):
        _nonnegative_number(capture.get(key), f"closed hold {key}")
    return dict(capture)


def _closed_profit_lock(trade: Record) -> dict[str, object]:
    challenger = _mapping(
        trade.get("profit_lock_challenger"), "closed profit-lock challenger"
    )
    if challenger.get("execution_authority") != "none":
        raise ValueError("V58 live-close profit lock has authority")
    if challenger.get("actual_exit_fill_claim") is not True:
        raise ValueError("V58 live-close profit lock lacks an actual exit")
    _text(challenger.get("status"), "closed profit-lock status")
    policies = _mapping(challenger.get("policies"), "closed profit-lock policies")
    if not policies:
        raise ValueError("V58 live-close profit-lock policies are empty")
    return dict(challenger)


def _require_report_only(report: Record) -> None:
    contract = report.get("contract")
    if not isinstance(contract, Mapping):
        raise ValueError("V58 report contract is invalid")
    expected = {
        "report_only": True,
        "execution_authority": "none",
        "automatic_live_change": False,
        "runtime_strategy_changed": False,
    }
    if any(contract.get(key) != value for key, value in expected.items()):
        raise ValueError("V58 report authority differs")


def _records(value: object, label: str) -> tuple[Record, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"V58 {label} must be an array")
    if any(not isinstance(row, Mapping) for row in value):
        raise ValueError(f"V58 {label} rows must be mappings")
    return tuple(value)  # type: ignore[return-value]


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"V58 {label} must be a mapping")
    return value


def _mutable_rows(value: object, label: str) -> list[dict[str, object]]:
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError(f"V58 {label} must contain mutable mappings")
    return value  # type: ignore[return-value]


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"V58 {label} must be non-empty text")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"V58 {label} must be numeric")
    number = float(value)
    if not isfinite(number):
        raise ValueError(f"V58 {label} must be finite")
    return number


def _positive_number(value: object, label: str) -> float:
    number = _number(value, label)
    if number <= 0:
        raise ValueError(f"V58 {label} must be positive")
    return number


def _nonnegative_number(value: object, label: str) -> float:
    number = _number(value, label)
    if number < 0:
        raise ValueError(f"V58 {label} must be nonnegative")
    return number


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"V58 {label} must be a positive integer")
    return value


def refresh_current_investigation(
    report: dict[str, object],
    lifecycles: Sequence[object],
    opportunities: RouteOpportunityCollection,
    backend: LiveBackendContext,
) -> None:
    """Prioritize actual open capital and exclude completed review tasks."""
    report["highest_value_next_investigation"] = highest_value_investigation(
        lifecycles,
        opportunities.opportunities,
        reviewed_routes=_reviewed_routes(report),
        live_open_lifecycles=backend.open_lifecycles,
    )


def _reviewed_routes(report: Mapping[str, object]) -> frozenset[str]:
    ledger = report.get("hypothesis_ledger")
    if not isinstance(ledger, Sequence) or isinstance(ledger, (str, bytes)):
        raise ValueError("V58 hypothesis ledger must be an array")
    reviewed: set[str] = set()
    for row in ledger:
        if not isinstance(row, Mapping):
            raise ValueError("V58 hypothesis ledger row must be a mapping")
        if row.get("review_status") == "reviewed_no_live_change":
            route = row.get("route")
            if not isinstance(route, str) or not route:
                raise ValueError("V58 reviewed hypothesis route is invalid")
            reviewed.add(route)
    return frozenset(reviewed)

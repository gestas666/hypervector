"""Lifecycle identity and accounting checks for v39 forward evidence."""

from __future__ import annotations

from collections.abc import Mapping
import math

from hypervector.research.cohort_trade_performance import build_trade_performance

Record = Mapping[str, object]

_SIDES = ("long", "short")
_COUNT_FIELDS = ("closed_trades", "wins", "losses", "breakeven")
_SUMMARY_FIELDS = (
    *_COUNT_FIELDS,
    "win_rate_pct",
    "net_pnl_usd",
    "entry_margin_used_usd",
    "net_return_on_margin_pct",
    "mean_trade_return_on_margin_pct",
    "profit_factor",
    "fees_usd",
    "funding_usd",
    "mean_trade_net_pnl_usd",
    "median_trade_net_pnl_usd",
    "median_trade_return_on_margin_pct",
    "largest_winner_usd",
    "largest_winner_share_of_gross_profit_pct",
    "net_pnl_excluding_largest_winner_usd",
    "maximum_closed_sequence_drawdown_usd",
    "gross_market_pnl_usd",
    "fees_as_pct_of_positive_gross_market_pnl",
)
_TOLERANCE = 1e-9


def validated_open_rows(
    section: Record,
    expected: tuple[str, ...],
    run_id: str,
) -> dict[tuple[str, str], tuple[Record, ...]]:
    """Validate and group every declared open lifecycle."""
    rows = _records(section.get("trades"), "open reflection trades")
    declared = _nonnegative_integer(section.get("open_lifecycles"), "open lifecycles")
    if declared != len(rows):
        raise ValueError("open lifecycle count does not reconcile")
    grouped: dict[tuple[str, str], list[Record]] = {}
    lifecycles: set[str] = set()
    symbols: set[str] = set()
    for row in rows:
        route, symbol, side, lifecycle = _validated_identity(row, expected, run_id)
        if lifecycle in lifecycles or symbol in symbols:
            raise ValueError("open reflection lifecycle identity is duplicated")
        _require_mark_identity(row, symbol, side)
        lifecycles.add(lifecycle)
        symbols.add(symbol)
        grouped.setdefault((route, side), []).append(row)
    return {key: tuple(values) for key, values in grouped.items()}


def require_current_trade_evidence(
    reflections: Record,
    current: Record,
    expected: tuple[str, ...],
    run_id: str,
    profile_fingerprint: str,
) -> None:
    """Reconcile current-run aggregates to their exact lifecycle rows."""
    rows = _records(reflections.get("trades"), "closed reflection trades")
    current_rows = [
        row for row in rows if _text(row.get("source_run_id"), "source run") == run_id
    ]
    total = _mapping(current.get("total"), "current-run total")
    declared = _nonnegative_integer(total.get("closed_trades"), "closed trades")
    if declared != len(current_rows):
        raise ValueError("current-run closed lifecycle count does not reconcile")
    lifecycles: set[str] = set()
    for row in current_rows:
        _, _, _, lifecycle = _validated_identity(row, expected, run_id)
        if _text(row.get("source_profile_fingerprint"), "profile fingerprint") != (
            profile_fingerprint
        ):
            raise ValueError("closed lifecycle profile fingerprint does not match v39")
        if lifecycle in lifecycles:
            raise ValueError("closed reflection lifecycle identity is duplicated")
        lifecycles.add(lifecycle)
    rebuilt = build_trade_performance(current_rows, current_run_id=run_id)
    expected_current = _mapping(rebuilt.get("current_run"), "rebuilt current run")
    _require_performance_tree(current, expected_current, expected)


def _require_performance_tree(
    actual: Record,
    expected: Record,
    routes: tuple[str, ...],
) -> None:
    _require_summary(
        _mapping(actual.get("total"), "current total"),
        _mapping(expected.get("total"), "rebuilt total"),
        "total",
    )
    actual_routes = _mapping(actual.get("by_provider_symbol"), "current routes")
    expected_routes = _mapping(expected.get("by_provider_symbol"), "rebuilt routes")
    if set(actual_routes) != set(expected_routes) or not set(actual_routes).issubset(
        routes
    ):
        raise ValueError("current-run performance routes do not reconcile")
    for route in expected_routes:
        _require_route_tree(
            _mapping(actual_routes[route], f"current {route}"),
            _mapping(expected_routes[route], f"rebuilt {route}"),
            route,
        )


def _require_route_tree(actual: Record, expected: Record, route: str) -> None:
    _require_summary(actual, expected, route)
    actual_sides = _mapping(actual.get("by_side"), f"current {route} sides")
    expected_sides = _mapping(expected.get("by_side"), f"rebuilt {route} sides")
    if set(actual_sides) != set(expected_sides):
        raise ValueError("current-run performance sides do not reconcile")
    for side in expected_sides:
        _require_summary(
            _mapping(actual_sides[side], f"current {route} {side}"),
            _mapping(expected_sides[side], f"rebuilt {route} {side}"),
            f"{route} {side}",
        )


def _require_summary(actual: Record, expected: Record, label: str) -> None:
    for field in _SUMMARY_FIELDS:
        expected_value = expected.get(field)
        actual_value = actual.get(field)
        if field in _COUNT_FIELDS:
            matches = _nonnegative_integer(actual_value, field) == expected_value
        elif expected_value is None:
            matches = actual_value is None
        else:
            matches = math.isclose(
                _number(actual_value, field),
                _number(expected_value, field),
                abs_tol=_TOLERANCE,
            )
        if not matches:
            raise ValueError(f"performance summary does not reconcile: {label} {field}")


def _validated_identity(
    row: Record,
    expected: tuple[str, ...],
    run_id: str,
) -> tuple[str, str, str, str]:
    symbol = _text(row.get("symbol"), "symbol")
    route = f"{_text(row.get('strategy_id'), 'strategy id')}|{symbol}"
    if route not in expected:
        raise ValueError("reflection contains a non-v39 route")
    if _text(row.get("source_run_id"), "source run") != run_id:
        raise ValueError("reflection source run does not match current run")
    side = _side(row.get("side"))
    lifecycle = _text(row.get("lifecycle_id"), "lifecycle id")
    _require_lifecycle_symbol(lifecycle, symbol, row.get("entry_oid"))
    return route, symbol, side, lifecycle


def _require_lifecycle_symbol(
    lifecycle: str,
    symbol: str,
    entry_oid: object,
) -> None:
    identity_symbol, separator, oid = lifecycle.rpartition(":")
    if separator != ":" or identity_symbol != symbol or not oid.isdigit():
        raise ValueError("lifecycle identity does not match symbol")
    if entry_oid is not None and oid != str(
        _nonnegative_integer(entry_oid, "entry oid")
    ):
        raise ValueError("lifecycle identity does not match entry oid")


def _require_mark_identity(row: Record, symbol: str, side: str) -> None:
    marked = _mapping(row.get("marked_economics"), "open marked economics")
    matches = (
        marked.get("symbol") == symbol
        and marked.get("side") == side
        and marked.get("status") == "provisional_open"
    )
    if not matches:
        raise ValueError("open marked economics identity does not match lifecycle")


def _records(value: object, label: str) -> list[Record]:
    if not isinstance(value, list) or not all(
        isinstance(row, Mapping) for row in value
    ):
        raise ValueError(f"{label} must be an array of objects")
    return value


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _side(value: object) -> str:
    side = _text(value, "side")
    if side not in _SIDES:
        raise ValueError("side must be long or short")
    return side


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _nonnegative_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result

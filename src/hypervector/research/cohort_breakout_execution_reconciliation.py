"""Exact source-profile fills reconciled against breakout policy proxies."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from math import isclose, isfinite

from hypervector.research.cohort_breakout_policy_models import (
    BreakoutPolicyForwardSpec,
)

Record = Mapping[str, object]
_IDENTITY_FIELDS = ("oid", "venue_timestamp_ms", "price", "size", "direction")


def reconcile_breakout_execution(
    records: Sequence[Record],
    lifecycles: Sequence[Record],
    *,
    spec: BreakoutPolicyForwardSpec,
) -> tuple[list[dict[str, object]], dict[str, int]]:
    """Attach exact recorded fills without converting proxies into live claims."""
    fills = _projected_fills(records, spec)
    reconciled = [_reconcile_lifecycle(row, fills, spec) for row in lifecycles]
    statuses = [str(row["actual_execution"]["status"]) for row in reconciled]
    return reconciled, {
        "matched_entries": sum(value in {"open", "resolved"} for value in statuses),
        "resolved_actual": statuses.count("resolved"),
        "open_actual": statuses.count("open"),
        "not_executed_source_profile": statuses.count("not_executed_source_profile"),
        "not_executed_or_withheld": statuses.count("not_executed_or_withheld"),
    }


def _projected_fills(
    records: Sequence[Record], spec: BreakoutPolicyForwardSpec
) -> tuple[dict[str, object], ...]:
    unique: dict[tuple[str, int], dict[str, object]] = {}
    for row in records:
        if row.get("run_id") != spec.source_run_id:
            continue
        if row.get("event_type") != "cohort_snapshot":
            continue
        for fill in _fill_rows(row):
            if not _in_scope(fill, spec):
                continue
            identity = (_text(fill, "symbol"), _integer(fill, "trade_id"))
            unique[identity] = _merge_fill(unique.get(identity), fill)
    return tuple(unique.values())


def _fill_rows(row: Record) -> tuple[Record, ...]:
    payload = row.get("payload")
    if not isinstance(payload, Mapping):
        raise ValueError("cohort snapshot payload must be an object")
    fills = payload.get("recent_fills", [])
    if not isinstance(fills, list) or not all(
        isinstance(value, Mapping) for value in fills
    ):
        raise ValueError("cohort snapshot recent_fills must be an object list")
    return tuple(value for value in fills if isinstance(value, Mapping))


def _in_scope(fill: Record, spec: BreakoutPolicyForwardSpec) -> bool:
    return (
        fill.get("origin_run_id") == spec.source_run_id
        and fill.get("strategy_id") == spec.source_strategy_id
        and fill.get("symbol") in spec.symbols
    )


def _merge_fill(
    existing: Mapping[str, object] | None, incoming: Record
) -> dict[str, object]:
    if existing is None:
        return dict(incoming)
    for field in _IDENTITY_FIELDS:
        if existing.get(field) != incoming.get(field):
            raise ValueError(f"repeated projected fill changed {field}")
    return dict(existing) | {
        key: value for key, value in incoming.items() if value is not None
    }


def _reconcile_lifecycle(
    lifecycle: Record,
    fills: Sequence[Record],
    spec: BreakoutPolicyForwardSpec,
) -> dict[str, object]:
    symbol = _text(lifecycle, "symbol")
    if symbol not in spec.source_execution_symbols:
        return dict(lifecycle) | {
            "actual_execution": {"status": "not_executed_source_profile"}
        }
    entry = _matching_entry(lifecycle, fills, spec)
    if entry is None:
        return dict(lifecycle) | {
            "actual_execution": {"status": "not_executed_or_withheld"}
        }
    close = _matching_close(entry, fills)
    actual = (
        _open_actual(entry)
        if close is None
        else _closed_actual(entry, close, lifecycle)
    )
    return dict(lifecycle) | {"actual_execution": actual}


def _matching_entry(
    lifecycle: Record,
    fills: Sequence[Record],
    spec: BreakoutPolicyForwardSpec,
) -> Record | None:
    signal_time = _integer(lifecycle, "signal_time_ms")
    deadline = signal_time + spec.maximum_entry_delay_seconds * 1_000
    matches = [
        fill
        for fill in fills
        if fill.get("operation") == "entry"
        and fill.get("symbol") == lifecycle.get("symbol")
        and _direction(fill) == lifecycle.get("side")
        and signal_time <= _integer(fill, "venue_timestamp_ms") <= deadline
        and _same_price(fill.get("expected_price"), lifecycle.get("entry_price"))
    ]
    if len(matches) > 1:
        raise ValueError("multiple actual entries match one breakout lifecycle")
    return matches[0] if matches else None


def _matching_close(entry: Record, fills: Sequence[Record]) -> Record | None:
    entry_time = _integer(entry, "venue_timestamp_ms")
    matches = [
        fill
        for fill in fills
        if _direction(fill).startswith("close_")
        and fill.get("symbol") == entry.get("symbol")
        and fill.get("entry_venue_timestamp_ms") == entry_time
    ]
    if len(matches) > 1:
        raise ValueError("multiple actual closes match one breakout entry")
    return matches[0] if matches else None


def _open_actual(entry: Record) -> dict[str, object]:
    return {
        "status": "open",
        "entry_oid": _integer(entry, "oid"),
        "entry_venue_timestamp_ms": _integer(entry, "venue_timestamp_ms"),
        "entry_price": _number(entry, "price"),
        "size": _number(entry, "size"),
        "entry_fee_usd": _number(entry, "fee_usd"),
        "entry_slippage_bps": _optional_number(entry, "slippage_bps"),
    }


def _closed_actual(
    entry: Record, close: Record, lifecycle: Record
) -> dict[str, object]:
    entry_price = _number(entry, "price")
    size = _number(entry, "size")
    net_pnl = _number(close, "net_pnl_usd")
    net_return = net_pnl / (entry_price * size) * 10_000.0
    proxy = _optional_number(lifecycle, "estimated_net_return_bps")
    return _open_actual(entry) | {
        "status": "resolved",
        "exit_oid": _integer(close, "oid"),
        "exit_venue_timestamp_ms": _integer(close, "venue_timestamp_ms"),
        "exit_price": _number(close, "price"),
        "exit_reason": _text(close, "exit_reason"),
        "fees_usd": _number(close, "lifecycle_fees_usd"),
        "funding_usd": _number(close, "lifecycle_funding_usd"),
        "net_pnl_usd": net_pnl,
        "net_return_bps": net_return,
        "net_return_delta_vs_proxy_bps": (
            net_return - proxy if proxy is not None else None
        ),
        "holding_time_ms": _integer(close, "holding_time_ms"),
    }


def _direction(fill: Record) -> str:
    value = _text(fill, "direction").lower().replace(" ", "_")
    if value not in {"open_long", "open_short", "close_long", "close_short"}:
        raise ValueError(f"unsupported projected fill direction: {value}")
    return value.removeprefix("open_") if value.startswith("open_") else value


def _same_price(left: object, right: object) -> bool:
    if left is None or right is None:
        return False
    return isclose(
        _raw_number(left, "expected price"),
        _raw_number(right, "entry price"),
        abs_tol=1e-9,
    )


def _text(row: Record, key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be non-empty text")
    return value


def _integer(row: Record, key: str) -> int:
    value = row.get(key)
    if type(value) is not int:
        raise ValueError(f"{key} must be an integer")
    return value


def _number(row: Record, key: str) -> float:
    return _raw_number(row.get(key), key)


def _optional_number(row: Record, key: str) -> float | None:
    value = row.get(key)
    return None if value is None else _raw_number(value, key)


def _raw_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result

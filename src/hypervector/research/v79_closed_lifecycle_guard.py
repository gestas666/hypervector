"""Exact closed-lifecycle reconciliation for V79 monitoring acceptance."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math

from hypervector.live.multi_asset_live_config import MultiAssetLiveConfig

Record = Mapping[str, object]
FillKey = tuple[str, int]
_EXIT_OPERATIONS = frozenset({"protective_stop", "reduce_only_close", "target"})
_SIZE_TOLERANCE = 0.000_000_001


@dataclass(frozen=True)
class ClosedLifecycleValidation:
    """V79 closed-lifecycle rejection reasons and resolved trade count."""

    reasons: tuple[str, ...]
    closed_trades: int


@dataclass(frozen=True)
class _FillAggregate:
    size: float
    price: float
    fees_usd: float
    closed_pnl_usd: float
    venue_timestamp_ms: int


def validate_v79_closed_lifecycles(
    audit: Record,
    config: MultiAssetLiveConfig,
) -> ClosedLifecycleValidation:
    """Reconcile every closed trade with its exact entry and exit fill legs."""
    execution = _mapping(audit.get("execution"), "audit execution")
    fills = _record_list(execution.get("fill_details"), "fill details")
    declared = _nonnegative_int(execution.get("closed_trades"), "closed trades")
    reflections = audit.get("trade_reflections")
    if reflections is None:
        reasons = (
            ["closed_lifecycle_projection_mismatch"]
            if declared > 0 or _has_exit(fills)
            else []
        )
        return ClosedLifecycleValidation(tuple(reasons), declared)
    section = _mapping(reflections, "trade reflections")
    trades = _record_list(section.get("trades"), "reflected trades")
    reflected = _nonnegative_int(section.get("closed_trades"), "reflected count")
    reasons = _projection_reasons(declared, reflected, len(trades))
    fill_index = _fill_index(fills)
    source_run_ids = _history_run_ids(execution)
    used_entries: set[FillKey] = set()
    used_exits: set[FillKey] = set()
    lifecycle_ids: set[str] = set()
    for trade in trades:
        reason, entry_key, exit_key = _trade_reason(
            trade, fill_index, config, source_run_ids
        )
        lifecycle = _lifecycle_label(trade)
        if reason or lifecycle in lifecycle_ids:
            reasons.append(f"closed_lifecycle_invalid:{lifecycle}")
        lifecycle_ids.add(lifecycle)
        if entry_key is not None:
            used_entries.add(entry_key)
        if exit_key is not None:
            used_exits.add(exit_key)
    reasons.extend(_summary_reasons(execution, trades))
    reasons.extend(_unlinked_fill_reasons(audit, fills, used_entries, used_exits))
    return ClosedLifecycleValidation(tuple(dict.fromkeys(reasons)), len(trades))


def _projection_reasons(declared: int, reflected: int, count: int) -> list[str]:
    if declared == reflected == count:
        return []
    return ["closed_lifecycle_projection_mismatch"]


def _trade_reason(
    trade: Record,
    fill_index: Mapping[FillKey, tuple[Record, ...]],
    config: MultiAssetLiveConfig,
    source_run_ids: frozenset[str],
) -> tuple[bool, FillKey | None, FillKey | None]:
    symbol = _text_or_none(trade.get("symbol"))
    strategy = _text_or_none(trade.get("strategy_id"))
    side = _text_or_none(trade.get("side"))
    entry_oid = _positive_int(trade.get("entry_oid"))
    exit_oid = _positive_int(trade.get("exit_oid"))
    if None in {symbol, strategy, side, entry_oid, exit_oid}:
        return True, None, None
    entry_key = (str(symbol), int(entry_oid))
    exit_key = (str(symbol), int(exit_oid))
    identity_ok = _trade_identity_matches(
        trade,
        config,
        source_run_ids,
        str(symbol),
        str(strategy),
        str(side),
        int(entry_oid),
        int(exit_oid),
    )
    economics_ok = _trade_economics_match(
        trade,
        fill_index.get(entry_key, ()),
        fill_index.get(exit_key, ()),
        str(strategy),
    )
    return not (identity_ok and economics_ok), entry_key, exit_key


def _trade_identity_matches(
    trade: Record,
    config: MultiAssetLiveConfig,
    source_run_ids: frozenset[str],
    symbol: str,
    strategy: str,
    side: str,
    entry_oid: int,
    exit_oid: int,
) -> bool:
    controller = _text_or_none(trade.get("exit_controller_strategy_id"))
    expected_cross = controller != strategy
    return (
        (strategy, symbol, side) in config.executable_provider_directions
        and entry_oid != exit_oid
        and trade.get("lifecycle_id") == f"{symbol}:{entry_oid}"
        and trade.get("entry_strategy_id") == strategy
        and trade.get("source_run_id") in source_run_ids
        and trade.get("source_profile_fingerprint") == config.profile_fingerprint
        and trade.get("cross_provider_exit") is expected_cross
        and controller is not None
        and _text_or_none(trade.get("exit_reason")) is not None
    )


def _trade_economics_match(
    trade: Record,
    entry_fills: Sequence[Record],
    exit_fills: Sequence[Record],
    strategy: str,
) -> bool:
    entry = _mapping_or_none(trade.get("entry"))
    exit_leg = _mapping_or_none(trade.get("exit"))
    entry_aggregate = _aggregate(entry_fills)
    exit_aggregate = _aggregate(exit_fills)
    if any(
        value is None for value in (entry, exit_leg, entry_aggregate, exit_aggregate)
    ):
        return False
    assert entry is not None and exit_leg is not None
    assert entry_aggregate is not None and exit_aggregate is not None
    if not _fill_roles_match(trade, entry_fills, exit_fills, strategy):
        return False
    return _legs_and_totals_match(
        trade, entry, exit_leg, entry_aggregate, exit_aggregate
    )


def _fill_roles_match(
    trade: Record,
    entry_fills: Sequence[Record],
    exit_fills: Sequence[Record],
    strategy: str,
) -> bool:
    controller = trade.get("exit_controller_strategy_id")
    reason = trade.get("exit_reason")
    source_run_id = trade.get("source_run_id")
    return (
        bool(entry_fills)
        and bool(exit_fills)
        and all(row.get("operation") == "entry" for row in entry_fills)
        and all(row.get("origin_run_id") == source_run_id for row in entry_fills)
        and all(row.get("operation") in _EXIT_OPERATIONS for row in exit_fills)
        and len({row.get("operation") for row in exit_fills}) == 1
        and all(
            row.get("strategy_id") == strategy for row in (*entry_fills, *exit_fills)
        )
        and all(row.get("exit_controller_id") == controller for row in exit_fills)
        and all(row.get("exit_reason") == reason for row in exit_fills)
    )


def _legs_and_totals_match(
    trade: Record,
    entry: Record,
    exit_leg: Record,
    entry_fill: _FillAggregate,
    exit_fill: _FillAggregate,
) -> bool:
    entry_time = _nonnegative_int_or_none(entry.get("venue_timestamp_ms"))
    exit_time = _nonnegative_int_or_none(exit_leg.get("venue_timestamp_ms"))
    fees = _finite_or_none(trade.get("fees_usd"))
    funding = _finite_or_none(trade.get("funding_usd"))
    net_pnl = _finite_or_none(trade.get("net_pnl_usd"))
    holding = _nonnegative_int_or_none(trade.get("holding_time_ms"))
    if None in {entry_time, exit_time, fees, funding, net_pnl, holding}:
        return False
    assert entry_time is not None and exit_time is not None
    expected_fees = entry_fill.fees_usd + exit_fill.fees_usd
    expected_net = exit_fill.closed_pnl_usd - expected_fees + float(funding)
    return (
        exit_time >= entry_time
        and holding == exit_time - entry_time
        and _leg_matches(entry, entry_fill)
        and _leg_matches(exit_leg, exit_fill)
        and math.isclose(entry_fill.size, exit_fill.size, abs_tol=_SIZE_TOLERANCE)
        and math.isclose(float(fees), expected_fees, abs_tol=1e-9)
        and math.isclose(float(net_pnl), expected_net, abs_tol=1e-9)
    )


def _leg_matches(leg: Record, fill: _FillAggregate) -> bool:
    price = _positive_float(leg.get("price"))
    size = _positive_float(leg.get("size"))
    timestamp = _nonnegative_int_or_none(leg.get("venue_timestamp_ms"))
    return (
        price is not None
        and size is not None
        and timestamp == fill.venue_timestamp_ms
        and math.isclose(price, fill.price, rel_tol=1e-12, abs_tol=1e-9)
        and math.isclose(size, fill.size, abs_tol=_SIZE_TOLERANCE)
    )


def _summary_reasons(execution: Record, trades: Sequence[Record]) -> list[str]:
    values = tuple(_finite_or_none(trade.get("net_pnl_usd")) for trade in trades)
    fees = tuple(_finite_or_none(trade.get("fees_usd")) for trade in trades)
    funding = tuple(_finite_or_none(trade.get("funding_usd")) for trade in trades)
    observed = (
        _finite_or_none(execution.get("net_pnl_usd")),
        _finite_or_none(execution.get("fees_usd")),
        _finite_or_none(execution.get("funding_usd")),
        _nonnegative_int_or_none(execution.get("wins")),
        _nonnegative_int_or_none(execution.get("losses")),
    )
    if None in (*values, *fees, *funding, *observed):
        return ["closed_lifecycle_summary_mismatch"]
    net_pnl, observed_fees, observed_funding, wins, losses = observed
    exact = (
        _close(float(net_pnl), sum(float(value) for value in values))
        and _close(float(observed_fees), sum(float(value) for value in fees))
        and _close(float(observed_funding), sum(float(value) for value in funding))
        and wins == sum(float(value) > 0.0 for value in values)
        and losses == sum(float(value) < 0.0 for value in values)
    )
    return [] if exact else ["closed_lifecycle_summary_mismatch"]


def _unlinked_fill_reasons(
    audit: Record,
    fills: Sequence[Record],
    closed_entries: set[FillKey],
    closed_exits: set[FillKey],
) -> list[str]:
    open_entries = _open_entry_keys(audit)
    for fill in fills:
        key = _fill_key(fill)
        operation = fill.get("operation")
        if operation == "entry" and key not in closed_entries | open_entries:
            return ["execution_fill_lifecycle_unlinked"]
        if operation in _EXIT_OPERATIONS and key not in closed_exits:
            return ["execution_fill_lifecycle_unlinked"]
    return []


def _open_entry_keys(audit: Record) -> set[FillKey]:
    value = audit.get("open_trade_reflections")
    if not isinstance(value, Mapping) or not isinstance(value.get("trades"), list):
        return set()
    output: set[FillKey] = set()
    for trade in value["trades"]:
        if not isinstance(trade, Mapping):
            continue
        symbol = _text_or_none(trade.get("symbol"))
        lifecycle = _text_or_none(trade.get("lifecycle_id"))
        if symbol is None or lifecycle is None:
            continue
        prefix = f"{symbol}:"
        oid = (
            _positive_int_text(lifecycle[len(prefix) :])
            if lifecycle.startswith(prefix)
            else None
        )
        if oid is not None:
            output.add((symbol, oid))
    return output


def _fill_index(fills: Sequence[Record]) -> dict[FillKey, tuple[Record, ...]]:
    grouped: dict[FillKey, list[Record]] = {}
    for fill in fills:
        grouped.setdefault(_fill_key(fill), []).append(fill)
    return {key: tuple(rows) for key, rows in grouped.items()}


def _history_run_ids(execution: Record) -> frozenset[str]:
    value = execution.get("history_run_ids")
    if not isinstance(value, list) or any(
        not isinstance(run_id, str) or not run_id.strip() for run_id in value
    ):
        return frozenset()
    return frozenset(value)


def _fill_key(fill: Record) -> FillKey:
    symbol = _text_or_none(fill.get("symbol"))
    oid = _positive_int(fill.get("oid"))
    if symbol is None or oid is None:
        return ("invalid", -1)
    return symbol, oid


def _aggregate(fills: Sequence[Record]) -> _FillAggregate | None:
    parsed = [
        (
            _positive_float(fill.get("price")),
            _positive_float(fill.get("size")),
            _nonnegative_float(fill.get("fee_usd")),
            _finite_or_none(fill.get("closed_pnl_usd")),
            _nonnegative_int_or_none(fill.get("venue_timestamp_ms")),
        )
        for fill in fills
    ]
    if not parsed or any(None in row for row in parsed):
        return None
    total_size = sum(float(row[1]) for row in parsed)
    return _FillAggregate(
        total_size,
        sum(float(row[0]) * float(row[1]) for row in parsed) / total_size,
        sum(float(row[2]) for row in parsed),
        sum(float(row[3]) for row in parsed),
        min(int(row[4]) for row in parsed),
    )


def _has_exit(fills: Sequence[Record]) -> bool:
    return any(fill.get("operation") in _EXIT_OPERATIONS for fill in fills)


def _lifecycle_label(trade: Record) -> str:
    value = _text_or_none(trade.get("lifecycle_id"))
    return value or "unknown"


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _mapping_or_none(value: object) -> Record | None:
    return value if isinstance(value, Mapping) else None


def _record_list(value: object, label: str) -> tuple[Record, ...]:
    if not isinstance(value, list) or any(
        not isinstance(row, Mapping) for row in value
    ):
        raise ValueError(f"{label} must be an array of objects")
    return tuple(value)


def _text_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _positive_int(value: object) -> int | None:
    valid = isinstance(value, int) and not isinstance(value, bool) and value > 0
    return value if valid else None


def _positive_int_text(value: str) -> int | None:
    if not value.isdecimal():
        return None
    parsed = int(value)
    return parsed if parsed > 0 else None


def _nonnegative_int(value: object, label: str) -> int:
    parsed = _nonnegative_int_or_none(value)
    if parsed is None:
        raise ValueError(f"{label} must be a nonnegative integer")
    return parsed


def _nonnegative_int_or_none(value: object) -> int | None:
    valid = isinstance(value, int) and not isinstance(value, bool) and value >= 0
    return value if valid else None


def _finite_or_none(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    parsed = float(value)
    return parsed if math.isfinite(parsed) else None


def _positive_float(value: object) -> float | None:
    parsed = _finite_or_none(value)
    return parsed if parsed is not None and parsed > 0.0 else None


def _nonnegative_float(value: object) -> float | None:
    parsed = _finite_or_none(value)
    return parsed if parsed is not None and parsed >= 0.0 else None


def _close(left: float, right: float) -> bool:
    return math.isfinite(left) and math.isclose(left, right, abs_tol=1e-9)

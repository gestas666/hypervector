"""Direction validation for V79 attributed execution fills."""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
import math

Record = Mapping[str, object]
RouteDirection = tuple[str, str, str]

_POSITION_DIRECTION = {
    ("entry", "Open Long", "B"): "long",
    ("entry", "Open Short", "A"): "short",
    ("protective_stop", "Close Long", "A"): "long",
    ("protective_stop", "Close Short", "B"): "short",
    ("reduce_only_close", "Close Long", "A"): "long",
    ("reduce_only_close", "Close Short", "B"): "short",
    ("target", "Close Long", "A"): "long",
    ("target", "Close Short", "B"): "short",
}


def fill_direction_matches_route(
    fill: Record,
    route_directions: Collection[RouteDirection],
) -> bool:
    """Return whether operation, venue direction, side, and route agree exactly."""
    strategy = fill.get("strategy_id")
    symbol = fill.get("symbol")
    operation = fill.get("operation")
    direction = fill.get("direction")
    side = fill.get("side")
    if not all(
        isinstance(value, str)
        for value in (strategy, symbol, operation, direction, side)
    ):
        return False
    position_direction = _POSITION_DIRECTION.get((operation, direction, side))
    return (
        position_direction is not None
        and (
            strategy,
            symbol,
            position_direction,
        )
        in route_directions
    )


def fill_run_provenance_matches(
    current_run_id: object,
    history_run_ids: object,
    fills: Sequence[Record],
    current_run_fills: int,
) -> bool:
    """Reconcile every fill origin and the current-run count to history scope."""
    if not isinstance(current_run_id, str) or not current_run_id.strip():
        return False
    if not isinstance(history_run_ids, list) or any(
        not isinstance(run_id, str) or not run_id.strip() for run_id in history_run_ids
    ):
        return False
    history = set(history_run_ids)
    origins = tuple(fill.get("origin_run_id") for fill in fills)
    return (
        len(history) == len(history_run_ids)
        and current_run_id in history
        and all(
            isinstance(origin, str) and bool(origin.strip()) and origin in history
            for origin in origins
        )
        and current_run_fills == sum(origin == current_run_id for origin in origins)
    )


def open_lifecycle_entry_matches(
    reflection: Record,
    fills: Sequence[Record],
    history_run_ids: object,
) -> bool:
    """Return whether one open reflection matches its exact entry-fill aggregate."""
    identity = _open_lifecycle_identity(reflection)
    if identity is None or not isinstance(history_run_ids, list):
        return False
    symbol, strategy, side, source_run_id, entry_oid = identity
    if source_run_id not in history_run_ids:
        return False
    matches = tuple(
        fill
        for fill in fills
        if fill.get("symbol") == symbol and fill.get("oid") == entry_oid
    )
    if not _entry_fill_roles_match(matches, strategy, side, source_run_id):
        return False
    entry = reflection.get("entry")
    if not isinstance(entry, Mapping):
        return False
    prices = tuple(_positive_float(fill.get("price")) for fill in matches)
    sizes = tuple(_positive_float(fill.get("size")) for fill in matches)
    timestamps = tuple(
        _nonnegative_int(fill.get("venue_timestamp_ms")) for fill in matches
    )
    observed = (
        _positive_float(entry.get("price")),
        _positive_float(entry.get("size")),
        _nonnegative_int(entry.get("venue_timestamp_ms")),
    )
    if None in (*prices, *sizes, *timestamps, *observed):
        return False
    total_size = sum(float(size) for size in sizes)
    average_price = (
        sum(
            float(price) * float(size)
            for price, size in zip(prices, sizes, strict=True)
        )
        / total_size
    )
    return (
        math.isclose(float(observed[0]), average_price, rel_tol=1e-12, abs_tol=1e-9)
        and math.isclose(float(observed[1]), total_size, abs_tol=1e-9)
        and observed[2] == min(int(value) for value in timestamps)
    )


def _open_lifecycle_identity(
    reflection: Record,
) -> tuple[str, str, str, str, int] | None:
    symbol = reflection.get("symbol")
    strategy = reflection.get("strategy_id")
    side = reflection.get("side")
    source_run_id = reflection.get("source_run_id")
    lifecycle = reflection.get("lifecycle_id")
    if not all(
        isinstance(value, str) and value.strip()
        for value in (
            symbol,
            strategy,
            source_run_id,
            lifecycle,
        )
    ) or side not in {"long", "short"}:
        return None
    prefix = f"{symbol}:"
    oid_text = lifecycle[len(prefix) :] if lifecycle.startswith(prefix) else ""
    if not oid_text.isdecimal() or int(oid_text) < 1:
        return None
    return symbol, strategy, side, source_run_id, int(oid_text)


def _entry_fill_roles_match(
    fills: Sequence[Record], strategy: str, side: str, source_run_id: str
) -> bool:
    venue_side = "B" if side == "long" else "A"
    direction = "Open Long" if side == "long" else "Open Short"
    trade_ids = tuple(_positive_int(fill.get("trade_id")) for fill in fills)
    return (
        bool(fills)
        and None not in trade_ids
        and len(set(trade_ids)) == len(trade_ids)
        and all(fill.get("operation") == "entry" for fill in fills)
        and all(fill.get("strategy_id") == strategy for fill in fills)
        and all(fill.get("origin_run_id") == source_run_id for fill in fills)
        and all(fill.get("side") == venue_side for fill in fills)
        and all(fill.get("direction") == direction for fill in fills)
    )


def _positive_int(value: object) -> int | None:
    valid = isinstance(value, int) and not isinstance(value, bool) and value > 0
    return value if valid else None


def _nonnegative_int(value: object) -> int | None:
    valid = isinstance(value, int) and not isinstance(value, bool) and value >= 0
    return value if valid else None


def _positive_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    parsed = float(value)
    return parsed if math.isfinite(parsed) and parsed > 0.0 else None

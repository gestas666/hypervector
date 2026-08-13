"""Provisional open-position economics for cohort live-run audits."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from hypervector.research.cohort_live_audit_values import (
    event_rows,
    mapping,
    mapping_list,
    number,
    object_list,
    payload,
    positive_int,
    text,
)

Record = Mapping[str, object]


def open_position_summary(
    records: Sequence[Record],
    journals: Mapping[str, Mapping[str, object]],
) -> list[dict[str, object]]:
    """Project open exposure with costs from only its active lifecycle."""
    snapshots = event_rows(records, "cohort_snapshot")
    if not snapshots:
        return []
    assets = object_list(payload(snapshots[-1]), "assets")
    return [
        _open_position(asset, _active_lifecycle(asset, journals))
        for asset in assets
        if number(asset.get("position_size_signed"), "position size") != 0.0
    ]


def _active_lifecycle(
    asset: Record,
    journals: Mapping[str, Mapping[str, object]],
) -> Record:
    symbol = text(asset.get("symbol"), "position symbol")
    journal = mapping(journals.get(symbol), f"{symbol} journal")
    lifecycles = mapping_list(
        journal.get("open_lifecycles"),
        f"{symbol} open lifecycles",
    )
    if len(lifecycles) != 1:
        raise ValueError(f"{symbol} open position requires exactly one lifecycle")
    return lifecycles[0]


def _open_position(asset: Record, lifecycle: Record) -> dict[str, object]:
    symbol = text(asset.get("symbol"), "position symbol")
    size = number(asset.get("position_size_signed"), f"{symbol} position size")
    side = text(asset.get("position_side"), f"{symbol} position side")
    expected_side = "long" if size > 0.0 else "short"
    if side != expected_side:
        raise ValueError(f"{symbol} position side conflicts with signed size")
    entry = _positive(asset, "entry_price", symbol)
    market_reference = _market_reference(asset, symbol)
    notional = _nonnegative(asset, "position_value_usd", symbol)
    mark = _position_mark(size, notional, symbol)
    liquidation = _positive(asset, "liquidation_price", symbol)
    liquidation_distance = abs(liquidation - mark) / mark * 100.0
    margin = _nonnegative(asset, "margin_used_usd", symbol)
    unrealized = number(asset.get("unrealized_pnl_usd"), f"{symbol} unrealized PnL")
    economics = _lifecycle_economics(asset, lifecycle, symbol, unrealized)
    return {
        "symbol": symbol,
        "side": side,
        **_active_target_field(asset, symbol),
        "size_signed": size,
        "entry_price": entry,
        "mark_price": mark,
        "market_reference_price": market_reference,
        "mark_price_source": "venue_position_value_div_size",
        "market_reference_skew_bps": (market_reference / mark - 1.0) * 10_000.0,
        "liquidation_price": liquidation,
        "liquidation_distance_pct": liquidation_distance,
        "margin_used_usd": margin,
        "position_value_usd": notional,
        "unrealized_pnl_usd": unrealized,
        **economics,
        "cost_scope": "active_lifecycle",
        "leverage": positive_int(asset.get("leverage"), f"{symbol} leverage"),
        "status": "provisional_open",
    }


def _active_target_field(asset: Record, symbol: str) -> dict[str, object]:
    target = _active_target_order(asset, symbol)
    return {} if target is None else {"target_order": target}


def _active_target_order(asset: Record, symbol: str) -> dict[str, object] | None:
    oid = asset.get("target_oid")
    price = asset.get("target_price")
    if oid is None and price is None:
        return None
    if oid is None or price is None:
        raise ValueError(f"{symbol} active target requires both identity and price")
    return {
        "oid": positive_int(oid, f"{symbol} target oid"),
        "limit_price": _positive(asset, "target_price", symbol),
    }


def _market_reference(asset: Record, symbol: str) -> float:
    value = asset.get("market_reference_price", asset.get("mark_price"))
    parsed = number(value, f"{symbol} market reference price")
    if parsed <= 0.0:
        raise ValueError(f"{symbol} market reference price must be positive")
    return parsed


def _position_mark(size: float, notional: float, symbol: str) -> float:
    if notional <= 0.0:
        raise ValueError(f"{symbol} open position value must be positive")
    return notional / abs(size)


def _lifecycle_economics(
    asset: Record,
    lifecycle: Record,
    symbol: str,
    unrealized: float,
) -> dict[str, float]:
    fees = _nonnegative(lifecycle, "fees_usd", symbol)
    funding = number(lifecycle.get("funding_usd"), f"{symbol} funding")
    realized = number(
        lifecycle.get("closed_pnl_before_friction_usd", 0.0),
        f"{symbol} active realized PnL",
    )
    return {
        "fees_usd": fees,
        "funding_usd": funding,
        "realized_pnl_usd": realized,
        "active_lifecycle_marked_net_pnl_usd": realized + unrealized - fees + funding,
        "profile_history_fees_usd": _nonnegative(asset, "fees_net_usd", symbol),
        "profile_history_funding_usd": number(
            asset.get("funding_net_usd"), f"{symbol} funding"
        ),
        "profile_history_realized_pnl_usd": number(
            asset.get("realized_pnl_usd"), f"{symbol} realized PnL"
        ),
    }


def _positive(asset: Record, key: str, symbol: str) -> float:
    value = number(asset.get(key), f"{symbol} {key}")
    if value <= 0.0:
        raise ValueError(f"{symbol} {key} must be positive")
    return value


def _nonnegative(asset: Record, key: str, symbol: str) -> float:
    value = number(asset.get(key), f"{symbol} {key}")
    if value < 0.0:
        raise ValueError(f"{symbol} {key} must be nonnegative")
    return value

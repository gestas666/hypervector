"""Execution-incapable multi-asset venue, ledger, and sizing preflight."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
import math
from typing import Protocol

from hypervector.live.hyperliquid_protocol import (
    Hip3MarketFeeMetadata,
    HyperliquidBookSnapshot,
    HyperliquidOpenOrder,
    HyperliquidVenuePreflight,
)
from hypervector.live.multi_asset_preflight_fees import preflight_fee_payload
from hypervector.live.multi_asset_live_config import (
    AssetLiveConfig,
    MultiAssetLiveConfig,
)
from hypervector.research.market_depth_fill import DepthLevel, walk_market_order

_BOOK_DEPTH_LEVELS = 20
_FINGERPRINT_LENGTH = 64


@dataclass(frozen=True)
class AssetLedgerExpectation:
    """Last durable backend position and owned-order identity for one asset."""

    position_size_signed: float
    owned_order_ids: frozenset[int]

    def __post_init__(self) -> None:
        """Reject malformed ledger truth before comparing it with the venue."""
        if not math.isfinite(self.position_size_signed):
            raise ValueError("ledger position size must be finite")
        if any(isinstance(oid, bool) or oid <= 0 for oid in self.owned_order_ids):
            raise ValueError("ledger owned order ids must be positive integers")


class MultiAssetReadOnlyReaderProtocol(Protocol):
    """Public-data surface required for one asset preflight."""

    def preflight(
        self,
        *,
        expected_max_leverage: int,
        requested_leverage: int | None = None,
    ) -> HyperliquidVenuePreflight:
        """Return current metadata, account, fee, mark, and position facts.

        With ``requested_leverage`` only a venue maximum below it refuses.
        """
        ...

    def book_snapshot(self, *, depth_levels: int) -> HyperliquidBookSnapshot:
        """Return one exact finite public order book."""
        ...

    def open_orders(self) -> tuple[HyperliquidOpenOrder, ...]:
        """Return current venue orders for only this asset."""
        ...

    def hip3_fee_metadata(self) -> Hip3MarketFeeMetadata:
        """Return exact fee modifiers for one namespaced HIP-3 market."""
        ...


def collect_multi_asset_read_only_preflight(
    *,
    config: MultiAssetLiveConfig,
    readers: Mapping[str, MultiAssetReadOnlyReaderProtocol],
    ledger_expectations: Mapping[str, AssetLedgerExpectation],
    active_profile_id: str,
    active_profile_fingerprint: str,
    observed_at: datetime,
    sizing_reference_equity_usd: float | None = None,
) -> dict[str, object]:
    """Collect current public venue truth and fail-closed transition evidence."""
    now = _validated_time(observed_at)
    sizing_reference = _validated_sizing_reference(sizing_reference_equity_usd)
    _validate_identity(active_profile_id, active_profile_fingerprint)
    _require_exact_coverage(config, readers, ledger_expectations)
    assets = tuple(
        _asset_report(
            asset,
            readers[asset.symbol],
            ledger_expectations[asset.symbol],
            sizing_reference,
        )
        for asset in config.assets
    )
    return {
        "schema_version": 1,
        "observed_at_utc": now.isoformat(),
        "identity": _identity(
            config,
            active_profile_id,
            active_profile_fingerprint,
        ),
        "authority": _authority(),
        "portfolio": _portfolio(config, assets, sizing_reference),
        "assets": assets,
        "limitations": _limitations(),
    }


def _asset_report(
    asset: AssetLiveConfig,
    reader: MultiAssetReadOnlyReaderProtocol,
    ledger: AssetLedgerExpectation,
    sizing_reference_equity_usd: float | None,
) -> dict[str, object]:
    maximum_leverage = _integer_leverage(asset.venue_max_leverage)
    preflight = reader.preflight(
        expected_max_leverage=maximum_leverage,
        requested_leverage=requested_market_leverage(asset),
    )
    if preflight.market.symbol != asset.symbol:
        raise ValueError(f"{asset.symbol} venue reader returned another symbol")
    book = reader.book_snapshot(depth_levels=_BOOK_DEPTH_LEVELS)
    orders = reader.open_orders()
    fee_metadata = preflight.hip3_fee_metadata
    if ":" in asset.symbol and fee_metadata is None:
        fee_metadata = reader.hip3_fee_metadata()
    fees = preflight_fee_payload(
        symbol=asset.symbol,
        fees=preflight.fees,
        hip3_metadata=fee_metadata,
    )
    sizing = _sizing(asset, preflight, sizing_reference_equity_usd)
    depth = _visible_depth(book, float(sizing["planned_notional_usd"]))
    reconciliation = _ledger_reconciliation(preflight, orders, ledger)
    return {
        "symbol": asset.symbol,
        "venue": _venue(preflight, fees),
        "position": _position(preflight),
        "open_orders": tuple(_order(order) for order in orders),
        "protection": _protection(preflight, orders),
        "ledger_reconciliation": reconciliation,
        "sizing": sizing,
        "visible_depth": depth,
        "sizing_technically_ready": _asset_sizing_ready(sizing, depth, fees),
    }


def _sizing(
    asset: AssetLiveConfig,
    preflight: HyperliquidVenuePreflight,
    sizing_reference_equity_usd: float | None,
) -> dict[str, object]:
    reference = (
        preflight.account_value_usd
        if sizing_reference_equity_usd is None
        else sizing_reference_equity_usd
    )
    margin = reference * asset.margin_fraction
    planned = min(margin * asset.leverage, asset.max_notional_usd)
    minimum = preflight.mark_price * preflight.size_step
    return {
        "actual_account_value_usd": preflight.account_value_usd,
        "withdrawable_usd": preflight.withdrawable_usd,
        "sizing_reference_equity_usd": reference,
        "margin_fraction": asset.margin_fraction,
        "leverage": asset.leverage,
        "max_notional_usd": asset.max_notional_usd,
        "planned_margin_usd": planned / asset.leverage,
        "planned_notional_usd": planned,
        "minimum_lot_notional_usd": minimum,
        "above_minimum_lot": planned >= minimum,
    }


def _visible_depth(book: HyperliquidBookSnapshot, notional: float) -> dict[str, object]:
    if notional <= 0.0 or not math.isfinite(notional):
        raise ValueError("planned notional must be positive and finite")
    quantity = notional / book.mid_price
    bids = tuple(DepthLevel(level.price, level.size) for level in book.bids)
    asks = tuple(DepthLevel(level.price, level.size) for level in book.asks)
    buy = walk_market_order(asks, side="buy", quantity=quantity)
    sell = walk_market_order(bids, side="sell", quantity=quantity)
    return {
        "book_timestamp_ms": book.exchange_timestamp_ms,
        "depth_levels_requested": _BOOK_DEPTH_LEVELS,
        "mid_price": book.mid_price,
        "spread_bps": book.spread_bps,
        "planned_quantity": quantity,
        "buy_complete": buy.complete,
        "buy_visible_cost_bps": (
            (buy.vwap / book.mid_price - 1.0) * 10_000.0 if buy.complete else None
        ),
        "sell_complete": sell.complete,
        "sell_visible_cost_bps": (
            (1.0 - sell.vwap / book.mid_price) * 10_000.0 if sell.complete else None
        ),
        "fills_assumed": False,
    }


def _ledger_reconciliation(
    preflight: HyperliquidVenuePreflight,
    orders: tuple[HyperliquidOpenOrder, ...],
    ledger: AssetLedgerExpectation,
) -> dict[str, object]:
    tolerance = max(preflight.size_step / 2.0, 1e-12)
    position_matches = math.isclose(
        preflight.position.size_signed,
        ledger.position_size_signed,
        rel_tol=0.0,
        abs_tol=tolerance,
    )
    venue_oids = frozenset(order.oid for order in orders)
    orders_match = venue_oids == ledger.owned_order_ids
    return {
        "expected_position_size_signed": ledger.position_size_signed,
        "expected_owned_order_ids": tuple(sorted(ledger.owned_order_ids)),
        "venue_owned_order_ids": tuple(sorted(venue_oids)),
        "position_matches": position_matches,
        "orders_match": orders_match,
        "matches": position_matches and orders_match,
    }


def _protection(
    preflight: HyperliquidVenuePreflight,
    orders: tuple[HyperliquidOpenOrder, ...],
) -> dict[str, object]:
    size = preflight.position.size_signed
    if size == 0.0:
        return {
            "status": "not_applicable_flat",
            "qualified_stop_order_ids": (),
            "covered_size": 0.0,
            "full_reduce_only_stop_coverage": None,
        }
    expected_side = "A" if size > 0.0 else "B"
    qualified = tuple(
        order
        for order in orders
        if _is_qualified_stop(order, expected_side, preflight.mark_price)
    )
    covered = sum(order.size for order in qualified)
    tolerance = max(preflight.size_step / 2.0, 1e-12)
    full = covered + tolerance >= abs(size)
    return {
        "status": "protected" if full else "unprotected_or_partial",
        "qualified_stop_order_ids": tuple(order.oid for order in qualified),
        "covered_size": covered,
        "full_reduce_only_stop_coverage": full,
    }


def _is_qualified_stop(
    order: HyperliquidOpenOrder,
    expected_side: str,
    mark_price: float,
) -> bool:
    if not order.reduce_only or not order.is_trigger or order.side != expected_side:
        return False
    if order.trigger_price is None:
        return False
    if expected_side == "A":
        return order.trigger_price < mark_price
    return order.trigger_price > mark_price


def _portfolio(
    config: MultiAssetLiveConfig,
    assets: tuple[dict[str, object], ...],
    sizing_reference_equity_usd: float | None,
) -> dict[str, object]:
    blocking = tuple(
        str(asset["symbol"]) for asset in assets if _asset_has_exposure_or_orders(asset)
    )
    ledger_reconciled = all(
        bool(_mapping(asset["ledger_reconciliation"])["matches"]) for asset in assets
    )
    sizing_ready = all(bool(asset["sizing_technically_ready"]) for asset in assets)
    flat = not blocking
    executable_symbols = _executable_asset_symbols(config)
    margin_fraction = maximum_executable_margin_fraction(config)
    reasons = _portfolio_reasons(blocking, ledger_reconciled, sizing_ready)
    reference = (
        min(_asset_actual_equity(asset) for asset in assets)
        if sizing_reference_equity_usd is None
        else sizing_reference_equity_usd
    )
    return {
        "configured_assets": len(config.assets),
        "maximum_positions": config.maximum_positions,
        "unused_capacity_slots": max(
            config.maximum_positions - len(executable_symbols),
            0,
        ),
        "maximum_configured_margin_fraction": margin_fraction,
        "sizing_reference_equity_usd": reference,
        "sizing_reference_source": (
            "actual_account"
            if sizing_reference_equity_usd is None
            else "explicit_scenario"
        ),
        "open_positions": sum(_asset_has_position(asset) for asset in assets),
        "open_orders": sum(len(_orders(asset)) for asset in assets),
        "flat_no_orders": flat,
        "transition_blocking_assets": blocking,
        "ledger_reconciled": ledger_reconciled,
        "sizing_technically_ready": sizing_ready,
        "technically_ready_for_profile_transition": not reasons,
        "readiness_reasons": reasons,
        "performance_gate": False,
        "balance_gate": False,
    }


def maximum_executable_margin_fraction(config: MultiAssetLiveConfig) -> float:
    """Return the reachable concurrent margin fraction under current authority."""
    executable = _executable_asset_symbols(config)
    fractions = sorted(
        (
            asset.margin_fraction
            for asset in config.assets
            if asset.symbol in executable
        ),
        reverse=True,
    )
    return sum(fractions[: config.maximum_positions])


def _executable_asset_symbols(config: MultiAssetLiveConfig) -> frozenset[str]:
    return frozenset(pair[1] for pair in config.executable_provider_symbols)


def _portfolio_reasons(
    blocking: tuple[str, ...],
    ledger_reconciled: bool,
    sizing_ready: bool,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if blocking:
        reasons.append("venue is not flat with no open orders")
    if not ledger_reconciled:
        reasons.append("backend ledger and venue position/order identity differ")
    if not sizing_ready:
        reasons.append(
            "planned sizing lacks minimum-lot, visible-depth, or effective fee support"
        )
    return tuple(reasons)


def _asset_sizing_ready(
    sizing: Mapping[str, object],
    depth: Mapping[str, object],
    fees: Mapping[str, object],
) -> bool:
    return (
        sizing["above_minimum_lot"] is True
        and depth["buy_complete"] is True
        and depth["sell_complete"] is True
        and str(fees["effective_fee_status"]).startswith("resolved_")
    )


def _asset_actual_equity(asset: Mapping[str, object]) -> float:
    sizing = _mapping(asset["sizing"])
    return float(sizing["actual_account_value_usd"])


def _asset_has_exposure_or_orders(asset: Mapping[str, object]) -> bool:
    return _asset_has_position(asset) or bool(_orders(asset))


def _asset_has_position(asset: Mapping[str, object]) -> bool:
    return float(_mapping(asset["position"])["size_signed"]) != 0.0


def _orders(asset: Mapping[str, object]) -> tuple[object, ...]:
    raw = asset["open_orders"]
    if not isinstance(raw, tuple):
        raise ValueError("asset open orders must be a tuple")
    return raw


def _venue(
    preflight: HyperliquidVenuePreflight,
    fees: Mapping[str, object],
) -> dict[str, object]:
    return {
        "mark_price": preflight.mark_price,
        "size_decimals": preflight.market.size_decimals,
        "size_step": preflight.size_step,
        "price_tick": preflight.price_tick,
        "venue_max_leverage": preflight.market.max_leverage,
        **fees,
        "account_abstraction_mode": preflight.account_abstraction_mode,
    }


def _position(preflight: HyperliquidVenuePreflight) -> dict[str, object]:
    position = preflight.position
    return {
        "size_signed": position.size_signed,
        "entry_price": position.entry_price,
        "liquidation_price": position.liquidation_price,
        "margin_used_usd": position.margin_used_usd,
        "position_value_usd": position.position_value_usd,
        "unrealized_pnl_usd": position.unrealized_pnl_usd,
        "leverage_type": position.leverage_type,
        "leverage": position.leverage,
    }


def _order(order: HyperliquidOpenOrder) -> dict[str, object]:
    return {
        "oid": order.oid,
        "size": order.size,
        "original_size": order.original_size,
        "side": order.side,
        "reduce_only": order.reduce_only,
        "is_trigger": order.is_trigger,
        "trigger_price": order.trigger_price,
        "order_type": order.order_type,
        "timestamp_ms": order.timestamp_ms,
        "limit_price": order.limit_price,
    }


def _identity(
    config: MultiAssetLiveConfig,
    active_profile_id: str,
    active_profile_fingerprint: str,
) -> dict[str, object]:
    return {
        "active_profile_id": active_profile_id,
        "active_profile_fingerprint": active_profile_fingerprint,
        "candidate_profile_id": config.profile_id,
        "candidate_profile_fingerprint": config.profile_fingerprint,
        "candidate_source_path": str(config.source_path),
        "candidate_differs_from_active": (
            config.profile_fingerprint != active_profile_fingerprint
        ),
        "network": config.network,
        "margin_mode": config.margin_mode,
    }


def _authority() -> dict[str, object]:
    return {
        "execution_authority": "none",
        "execution_client_constructed": False,
        "signing_key_required": False,
        "operation": "multi_asset_read_only_preflight",
    }


def _require_exact_coverage(
    config: MultiAssetLiveConfig,
    readers: Mapping[str, MultiAssetReadOnlyReaderProtocol],
    expectations: Mapping[str, AssetLedgerExpectation],
) -> None:
    expected = set(config.symbols)
    if set(readers) != expected:
        raise ValueError("multi-asset preflight reader coverage differs from config")
    if set(expectations) != expected:
        raise ValueError("multi-asset preflight ledger coverage differs from config")


def _validated_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("preflight observed_at must be timezone-aware")
    return value.astimezone(UTC)


def _validated_sizing_reference(value: float | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not math.isfinite(value) or value <= 0.0:
        raise ValueError("sizing reference equity must be positive and finite")
    return float(value)


def _validate_identity(profile_id: str, fingerprint: str) -> None:
    if not profile_id or profile_id != profile_id.strip():
        raise ValueError("active profile id must be non-empty and trimmed")
    if len(fingerprint) != _FINGERPRINT_LENGTH or any(
        character not in "0123456789abcdef" for character in fingerprint
    ):
        raise ValueError("active profile fingerprint must be lowercase sha256")


def requested_market_leverage(asset: AssetLiveConfig) -> int:
    """Return the leverage an asset requests, rounded up to the venue's integer grid."""
    return math.ceil(asset.leverage)


def _integer_leverage(value: float) -> int:
    if not math.isfinite(value) or value <= 0.0 or not value.is_integer():
        raise ValueError("venue maximum leverage must be a positive integer")
    return int(value)


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("preflight nested payload must be a mapping")
    return value


def _limitations() -> tuple[str, ...]:
    return (
        "one point-in-time public book does not estimate queue position or latency",
        "visible depth can cancel before a later IOC reaches the venue",
        "a technically ready profile is not a profit or performance forecast",
        "profile transition still requires explicit live-risk authorization",
    )

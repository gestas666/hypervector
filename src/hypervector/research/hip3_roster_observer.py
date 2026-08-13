"""Execution-incapable checkpoint projection for qualified HIP-3 markets."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Protocol

from hypervector.live.hyperliquid_protocol import (
    Hip3MarketFeeMetadata,
    SolBookLevel,
    SolBookSnapshot,
    SolOpenOrder,
    SolVenuePreflight,
)
from hypervector.research.hip3_fee_model import Hip3FeeInputs, effective_hip3_fees


@dataclass(frozen=True)
class Hip3MarketSpec:
    """One exact active HIP-3 symbol and its venue leverage ceiling."""

    symbol: str
    expected_max_leverage: int


ACTIVE_HIP3_MARKETS = (
    Hip3MarketSpec("xyz:SP500", 50),
    Hip3MarketSpec("xyz:SPCX", 20),
    Hip3MarketSpec("xyz:SNDK", 10),
    Hip3MarketSpec("xyz:GOLD", 25),
    Hip3MarketSpec("xyz:BRENTOIL", 20),
)


class Hip3ReaderProtocol(Protocol):
    """Read-only venue surface required by the roster observer."""

    def preflight(self, *, expected_max_leverage: int) -> SolVenuePreflight:
        """Return current venue, account, and fee truth."""
        ...

    def book_snapshot(self, *, depth_levels: int) -> SolBookSnapshot:
        """Return one exact two-sided order book."""
        ...

    def open_orders(self) -> tuple[SolOpenOrder, ...]:
        """Return open orders for only the bound symbol."""
        ...

    def hip3_fee_metadata(self) -> Hip3MarketFeeMetadata:
        """Return exact market-level fee modifiers."""
        ...


class Hip3RosterObserver:
    """Collect one fail-closed, report-only HIP-3 roster checkpoint."""

    def __init__(
        self,
        *,
        readers: Mapping[str, Hip3ReaderProtocol],
        markets: tuple[Hip3MarketSpec, ...] = ACTIVE_HIP3_MARKETS,
    ) -> None:
        _validate_reader_roster(readers, markets)
        self._readers = dict(readers)
        self._markets = markets

    def snapshot(self, observed_at: datetime) -> dict[str, object]:
        """Read every market or raise without publishing partial success."""
        timestamp = _utc_timestamp(observed_at)
        rows = [self._market_snapshot(spec) for spec in self._markets]
        return {
            "schema_version": 1,
            "mode": "hip3_roster_observer_checkpoint",
            "status": "available",
            "observed_at_utc": timestamp,
            "active_symbols": [spec.symbol for spec in self._markets],
            "markets": rows,
            "requested_aliases": _requested_aliases(),
            "execution_authority": "none",
            "report_only": True,
            "automatic_promotion": False,
            "runtime_strategy_changed": False,
            "signing_client_constructed": False,
        }

    def _market_snapshot(self, spec: Hip3MarketSpec) -> dict[str, object]:
        reader = self._readers[spec.symbol]
        preflight = reader.preflight(expected_max_leverage=spec.expected_max_leverage)
        if preflight.market.symbol != spec.symbol:
            raise ValueError(f"{spec.symbol} reader returned {preflight.market.symbol}")
        book = reader.book_snapshot(depth_levels=20)
        orders = reader.open_orders()
        fee_metadata = reader.hip3_fee_metadata()
        return {
            "symbol": spec.symbol,
            "venue_namespace": spec.symbol.partition(":")[0],
            "venue": _venue_payload(preflight, fee_metadata),
            "book": _book_payload(book),
            "account": _account_payload(preflight, orders),
        }


def unavailable_hip3_roster_checkpoint(
    *,
    observed_at: datetime,
    error: Exception,
) -> dict[str, object]:
    """Build an explicit unavailable state without numeric fallback values."""
    return {
        "schema_version": 1,
        "mode": "hip3_roster_observer_checkpoint",
        "status": "unavailable",
        "observed_at_utc": _utc_timestamp(observed_at),
        "active_symbols": [spec.symbol for spec in ACTIVE_HIP3_MARKETS],
        "markets": None,
        "requested_aliases": _requested_aliases(),
        "error": {"type": type(error).__name__, "message": str(error)},
        "execution_authority": "none",
        "report_only": True,
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "signing_client_constructed": False,
    }


def _validate_reader_roster(
    readers: Mapping[str, Hip3ReaderProtocol],
    markets: tuple[Hip3MarketSpec, ...],
) -> None:
    expected = {spec.symbol for spec in markets}
    if not markets or len(expected) != len(markets):
        raise ValueError("HIP-3 market specifications must be non-empty and unique")
    actual = set(readers)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValueError(
            f"HIP-3 reader roster mismatch: missing={missing}, extra={extra}"
        )


def _venue_payload(
    preflight: SolVenuePreflight,
    metadata: Hip3MarketFeeMetadata,
) -> dict[str, object]:
    fees = _fee_payload(preflight, metadata)
    return {
        "mark_price": preflight.mark_price,
        "price_tick": preflight.price_tick,
        "size_step": preflight.size_step,
        "size_decimals": preflight.market.size_decimals,
        "max_leverage": preflight.market.max_leverage,
        **fees,
        "account_abstraction_mode": preflight.account_abstraction_mode,
    }


def _fee_payload(
    preflight: SolVenuePreflight,
    metadata: Hip3MarketFeeMetadata,
) -> dict[str, object]:
    common = {
        "account_base_maker_fee_rate": preflight.fees.maker_rate,
        "account_base_taker_fee_rate": preflight.fees.taker_rate,
        "active_referral_discount": preflight.fees.active_referral_discount,
        "deployer_fee_scale": metadata.deployer_fee_scale,
        "growth_mode": metadata.growth_mode,
        "collateral_token_index": metadata.collateral_token_index,
        "aligned_quote_status": "unresolved_conservative_false",
    }
    if metadata.growth_mode is None:
        return {
            **common,
            "effective_fee_status": "unresolved_growth_mode",
            "maker_fee_rate": None,
            "taker_fee_rate": None,
            "fee_formula_source": None,
        }
    inputs = Hip3FeeInputs(
        account_maker_rate=preflight.fees.maker_rate,
        account_taker_rate=preflight.fees.taker_rate,
        active_referral_discount=preflight.fees.active_referral_discount,
        deployer_fee_scale=metadata.deployer_fee_scale,
        growth_mode=metadata.growth_mode,
        aligned_quote=False,
        aligned_quote_status="unresolved_conservative_false",
        evidence_label="live_official_sdk_hip3_observer",
    )
    effective = effective_hip3_fees(inputs)
    return {
        **common,
        "effective_fee_status": "resolved",
        "maker_fee_rate": effective.effective_maker_rate,
        "taker_fee_rate": effective.effective_taker_rate,
        "fee_formula_source": effective.formula_source,
    }


def _book_payload(book: SolBookSnapshot) -> dict[str, object]:
    return {
        "exchange_timestamp_ms": book.exchange_timestamp_ms,
        "mid_price": book.mid_price,
        "spread_bps": book.spread_bps,
        "level_count": {"bids": len(book.bids), "asks": len(book.asks)},
        "depth_5": _depth_window(book, 5),
        "depth_20": _depth_window(book, 20),
        "bids": [asdict(level) for level in book.bids],
        "asks": [asdict(level) for level in book.asks],
    }


def _depth_window(book: SolBookSnapshot, levels: int) -> dict[str, float]:
    bids = book.bids[:levels]
    asks = book.asks[:levels]
    bid_depth = _depth(bids)
    ask_depth = _depth(asks)
    denominator = bid_depth + ask_depth
    return {
        "bid_base": bid_depth,
        "ask_base": ask_depth,
        "order_pressure": (bid_depth - ask_depth) / denominator,
    }


def _depth(levels: tuple[SolBookLevel, ...]) -> float:
    return sum(level.size for level in levels)


def _account_payload(
    preflight: SolVenuePreflight,
    orders: tuple[SolOpenOrder, ...],
) -> dict[str, object]:
    return {
        "account_value_usd": preflight.account_value_usd,
        "withdrawable_usd": preflight.withdrawable_usd,
        "position": asdict(preflight.position),
        "open_order_count": len(orders),
        "open_orders": [asdict(order) for order in orders],
    }


def _requested_aliases() -> dict[str, dict[str, object]]:
    return {
        "WTIOIL": {
            "status": "historical_only",
            "live_symbol": None,
            "historical_symbol": "cash:WTI",
            "active_alternative": "xyz:BRENTOIL",
            "equivalence_assumed": False,
        }
    }


def _utc_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("HIP-3 observer timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat()

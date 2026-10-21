"""Execution-incapable checkpoint projection for a configured HIP-3 market roster.

The roster is supplied by the caller (a cohort profile's HIP-3 assets or an
explicit operator list); nothing here names a market.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import math
from typing import Protocol

from hypervector.live.hyperliquid_protocol import (
    Hip3MarketFeeMetadata,
    HyperliquidBookLevel,
    HyperliquidBookSnapshot,
    HyperliquidOpenOrder,
    HyperliquidVenuePreflight,
)
from hypervector.research.hip3_fee_model import Hip3FeeInputs, effective_hip3_fees


@dataclass(frozen=True)
class Hip3MarketSpec:
    """One exact HIP-3 symbol and the venue leverage ceiling it must report."""

    symbol: str
    expected_max_leverage: int

    def __post_init__(self) -> None:
        """Reject a malformed identity or leverage ceiling."""
        if not isinstance(self.symbol, str) or ":" not in self.symbol:
            raise ValueError("HIP-3 market symbol must be dex:ASSET")
        leverage = self.expected_max_leverage
        if isinstance(leverage, bool) or not isinstance(leverage, int) or leverage < 1:
            raise ValueError("HIP-3 expected_max_leverage must be a positive integer")


class Hip3ReaderProtocol(Protocol):
    """Read-only venue surface required by the roster observer."""

    def preflight(self, *, expected_max_leverage: int) -> HyperliquidVenuePreflight:
        """Return current venue, account, and fee truth."""
        ...

    def book_snapshot(self, *, depth_levels: int) -> HyperliquidBookSnapshot:
        """Return one exact two-sided order book."""
        ...

    def open_orders(self) -> tuple[HyperliquidOpenOrder, ...]:
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
        markets: tuple[Hip3MarketSpec, ...],
        funding_source: Callable[[], Mapping[str, float | None]] | None = None,
    ) -> None:
        """Bind the exact reader roster and optional unsigned funding source."""
        _validate_reader_roster(readers, markets)
        self._readers = dict(readers)
        self._markets = markets
        self._funding_source = funding_source

    def snapshot(self, observed_at: datetime) -> dict[str, object]:
        """Read every market or raise without publishing partial success."""
        timestamp = _utc_timestamp(observed_at)
        funding = self._funding_source() if self._funding_source is not None else None
        if self._funding_source is not None and not isinstance(funding, Mapping):
            raise ValueError("HIP-3 funding source must return a mapping")
        if funding is not None and set(funding) != {
            spec.symbol for spec in self._markets
        }:
            raise ValueError("HIP-3 funding roster mismatch")
        rows = [self._market_snapshot(spec, funding) for spec in self._markets]
        return {
            "schema_version": 1,
            "mode": "hip3_roster_observer_checkpoint",
            "status": "available",
            "observed_at_utc": timestamp,
            "active_symbols": [spec.symbol for spec in self._markets],
            "markets": rows,
            "execution_authority": "none",
            "report_only": True,
            "automatic_promotion": False,
            "runtime_strategy_changed": False,
            "signing_client_constructed": False,
        }

    def _market_snapshot(
        self,
        spec: Hip3MarketSpec,
        funding: Mapping[str, float | None] | None,
    ) -> dict[str, object]:
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
            "venue": {
                **_venue_payload(preflight, fee_metadata),
                **_funding_payload(spec.symbol, funding),
            },
            "book": _book_payload(book),
            "account": _account_payload(preflight, orders),
        }


def _funding_payload(
    symbol: str,
    funding: Mapping[str, float | None] | None,
) -> dict[str, object]:
    rate = funding[symbol] if funding is not None else None
    if rate is not None and (
        isinstance(rate, bool)
        or not isinstance(rate, (int, float))
        or not math.isfinite(rate)
    ):
        raise ValueError(f"{symbol} funding must be a finite number or unavailable")
    status = "unconfigured" if funding is None else "unavailable"
    return {
        "funding_rate_hourly": rate,
        "funding_status": "available" if rate is not None else status,
        "funding_source": "hyperliquid_info_metaAndAssetCtxs"
        if funding is not None
        else None,
    }


def unavailable_hip3_roster_checkpoint(
    *,
    observed_at: datetime,
    error: Exception,
    symbols: tuple[str, ...] = (),
) -> dict[str, object]:
    """Build an explicit unavailable state without numeric fallback values."""
    return {
        "schema_version": 1,
        "mode": "hip3_roster_observer_checkpoint",
        "status": "unavailable",
        "observed_at_utc": _utc_timestamp(observed_at),
        "active_symbols": list(symbols),
        "markets": None,
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
    preflight: HyperliquidVenuePreflight,
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
    preflight: HyperliquidVenuePreflight,
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
    if metadata.deployer_fee_scale is None:
        return {
            **common,
            "effective_fee_status": "unresolved_deployer_fee_scale",
            "maker_fee_rate": None,
            "taker_fee_rate": None,
            "fee_formula_source": None,
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


def _book_payload(book: HyperliquidBookSnapshot) -> dict[str, object]:
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


def _depth_window(book: HyperliquidBookSnapshot, levels: int) -> dict[str, float]:
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


def _depth(levels: tuple[HyperliquidBookLevel, ...]) -> float:
    return sum(level.size for level in levels)


def _account_payload(
    preflight: HyperliquidVenuePreflight,
    orders: tuple[HyperliquidOpenOrder, ...],
) -> dict[str, object]:
    return {
        "account_value_usd": preflight.account_value_usd,
        "withdrawable_usd": preflight.withdrawable_usd,
        "position": asdict(preflight.position),
        "open_order_count": len(orders),
        "open_orders": [asdict(order) for order in orders],
    }


def _utc_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("HIP-3 observer timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat()

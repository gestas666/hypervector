"""Explicit metadata, timing and order records for a signing-incapable SDK replay."""

from dataclasses import dataclass
from decimal import Decimal

from hypervector.live.hyperliquid_hip3_fee_parsing import parse_hip3_market_fee_metadata
from hypervector.live.hyperliquid_perp_parsing import parse_market_for_symbol
from hypervector.live.hyperliquid_protocol import SolMarketMetadata
from hypervector.live.hyperliquid_sol_parsing import parse_fees
from hypervector.live.multi_asset_preflight_fees import preflight_fee_payload
from hypervector.live.perp_venue_identity import parse_perp_venue_identity
from hypervector.research.native_replay_events import require_clock


@dataclass(frozen=True)
class ReplaySdkTiming:
    """Declared delays: arrival from dispatch, then receipt delays from execution."""

    arrival_delay_ms: int
    response_delay_ms: int
    fill_visible_delay_ms: int
    order_visible_delay_ms: int
    mutation_response_ms: int

    def __post_init__(self) -> None:
        """Reject malformed clocks rather than silently correcting a timing scenario."""
        for name in self.__dataclass_fields__:
            require_clock(getattr(self, name), name)


@dataclass(frozen=True)
class ReplayMarket:
    """Native parsed precision and effective account fees for one declared market."""

    metadata: SolMarketMetadata
    perp_dex: str
    maker_rate: Decimal
    taker_rate: Decimal


def replay_market(symbol: str, metadata: object, dexes: object, fees: object) -> ReplayMarket:
    """Reuse the exact native metadata/fee readers, including HIP-3 modifiers."""
    dex = parse_perp_venue_identity(symbol).perp_dex
    market = parse_market_for_symbol(metadata, symbol)
    hip3 = (
        parse_hip3_market_fee_metadata(metadata=metadata, dexes=dexes, symbol=symbol, perp_dex=dex)
        if dex
        else None
    )
    effective = preflight_fee_payload(symbol=symbol, fees=parse_fees(fees), hip3_metadata=hip3)
    rates = [effective[f"effective_{side}_fee_rate"] for side in ("maker", "taker")]
    if any(type(rate) not in (int, float) for rate in rates):
        raise ValueError(f"offline replay needs resolved effective fees for {symbol}")
    return ReplayMarket(market, dex, *(Decimal(str(rate)) for rate in rates))


@dataclass(frozen=True)
class ReplayOrderRecord:
    """One shared order identity with separate acceptance and terminal visibility."""

    oid: int
    client_id: str
    symbol: str
    is_buy: bool
    quantity: Decimal
    remaining: Decimal
    limit_price: Decimal
    trigger_price: Decimal | None
    reduce_only: bool
    resting: bool
    created_ms: int
    opened_visible_ms: int
    status: str
    status_ms: int
    changed_visible_ms: int
    triggered_ms: int | None = None
    matched_ms: int | None = None
    previous: "ReplayOrderRecord | None" = None

    def visible_revision(self, observed_ms: int) -> "ReplayOrderRecord":
        """Retain every prior partial update until the newer revision is observable."""
        row = self
        while observed_ms < row.changed_visible_ms and row.previous is not None:
            row = row.previous
        return row

    def wire(self, observed_ms: int) -> dict[str, object]:
        """Return a detached native order object without leaking a future terminal size."""
        row = self.visible_revision(observed_ms)
        if row is not self:
            return row.wire(observed_ms)
        remaining = self.remaining if observed_ms >= self.changed_visible_ms else self.quantity
        return {
            "coin": self.symbol,
            "oid": self.oid,
            "sz": str(remaining),
            "origSz": str(self.quantity),
            "side": "B" if self.is_buy else "A",
            "reduceOnly": self.reduce_only,
            "isTrigger": self.trigger_price is not None,
            "triggerPx": str(self.trigger_price) if self.trigger_price is not None else "0.0",
            "limitPx": str(self.limit_price),
            "orderType": "Stop Market"
            if self.trigger_price is not None or self.triggered_ms is not None
            else "Limit",
            "timestamp": self.triggered_ms if self.triggered_ms is not None else self.created_ms,
            "tif": "Gtc" if self.triggered_ms is not None else None,
            "cloid": self.client_id,
        }

    def visible_open(self, observed_ms: int) -> bool:
        """Retain a stale accepted open order until its terminal update becomes observable."""
        row = self.visible_revision(observed_ms)
        if row is not self:
            return row.visible_open(observed_ms)
        return (
            self.resting
            and self.opened_visible_ms <= observed_ms
            and (self.status == "open" or observed_ms < self.changed_visible_ms)
        )

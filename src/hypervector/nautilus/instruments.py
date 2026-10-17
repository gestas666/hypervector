"""Build the Phase 2 sim ``CryptoPerpetual`` for an export symbol.

Geometry (price/size precision, venue max leverage) comes from
:func:`hypervector.nautilus.venue_spec.resolve_venue_spec`; fee rates come
from the export cost model and margins from the sim leverage. BTC without
cached venue metadata keeps the historical stub geometry so BTC results stay
continuous.
"""

from __future__ import annotations

from decimal import Decimal

from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.instruments import CryptoPerpetual
from nautilus_trader.model.objects import Currency, Money, Price, Quantity

from hypervector.nautilus.bars import synthetic_btc_perp_instrument
from hypervector.nautilus.venue_spec import VenueInstrumentSpec

# Hyperliquid minimum order value.
_MIN_NOTIONAL_USD = 10.0


def _increment(decimals: int) -> str:
    if decimals <= 0:
        return "1"
    return f"{Decimal(1).scaleb(-decimals):.{decimals}f}"


def perp_instrument_from_spec(
    spec: VenueInstrumentSpec,
    *,
    venue: str,
    maker_fee: Decimal,
    taker_fee: Decimal,
    margin_init: Decimal,
    margin_maint: Decimal,
) -> CryptoPerpetual:
    """Linear USDT-settled perpetual with venue geometry and explicit costs."""
    if spec.source == "builtin_btc_stub":
        return synthetic_btc_perp_instrument(
            venue=venue,
            maker_fee=maker_fee,
            taker_fee=taker_fee,
            margin_init=margin_init,
            margin_maint=margin_maint,
        )
    price_increment = Price.from_str(_increment(spec.price_decimals))
    size_increment = Quantity.from_str(_increment(spec.size_decimals))
    base = Currency.from_str(spec.coin, strict=False)
    return CryptoPerpetual(
        instrument_id=InstrumentId(
            symbol=Symbol(spec.instrument_symbol), venue=Venue(venue)
        ),
        raw_symbol=Symbol(spec.instrument_symbol),
        base_currency=base,
        quote_currency=USDT,
        settlement_currency=USDT,
        is_inverse=False,
        price_precision=spec.price_decimals,
        size_precision=spec.size_decimals,
        price_increment=price_increment,
        size_increment=size_increment,
        max_quantity=None,
        min_quantity=size_increment,
        max_notional=None,
        min_notional=Money(_MIN_NOTIONAL_USD, USDT),
        max_price=None,
        min_price=price_increment,
        margin_init=Decimal(margin_init),
        margin_maint=Decimal(margin_maint),
        maker_fee=Decimal(maker_fee),
        taker_fee=Decimal(taker_fee),
        ts_event=0,
        ts_init=0,
    )

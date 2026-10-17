"""Hyperliquid perp geometry for the Phase 2 sim instrument (import-light).

Resolves an export symbol to price/size precision and venue max leverage
without importing NautilusTrader, so ``nautilus check`` can predict whether
``nautilus run`` supports a bundle.

Resolution order:

1. Venue metadata cached in the export (``meta.instrument`` or
   ``meta.venue_meta``) in Hyperliquid ``meta.universe`` shape:
   ``{"szDecimals": int, "maxLeverage": number}`` (snake_case aliases
   ``size_decimals`` / ``max_leverage`` and an optional explicit
   ``price_decimals`` are accepted).
2. The built-in charter table (``SRS_HV1_VENUE_SPEC``) for the majors.
3. Otherwise :class:`UnsupportedNautilusSymbol` — never a guessed geometry.

Leverage is always capped by the charter: BTC 40x, ETH 25x, SOL 20x, any
other perp at most 15x (the charter's altcoin ceiling), even when cached
metadata claims more.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Mapping

from hypervector.nautilus.errors import UnsupportedNautilusSymbol

# Hyperliquid perps: price decimals <= MAX_DECIMALS - szDecimals.
HL_PERP_MAX_DECIMALS = 6

# SRS_HV1_VENUE_SPEC caps; non-majors are capped at the altcoin ceiling.
CHARTER_MAX_LEVERAGE: dict[str, float] = {"BTC": 40.0, "ETH": 25.0, "SOL": 20.0}
ALTCOIN_MAX_LEVERAGE = 15.0

# Built-in venue geometry: coin -> (szDecimals, maxLeverage).
_BUILTIN_VENUE: dict[str, tuple[int, float]] = {
    "BTC": (5, 40.0),
    "ETH": (4, 25.0),
    "SOL": (2, 20.0),
    "HYPE": (2, 10.0),
}

# The historical BTC stub geometry (0.1 price / 0.001 size) is kept so BTC
# results stay continuous; it is coarser than the venue's szDecimals=5.
_BTC_STUB_PRICE_DECIMALS = 1
_BTC_STUB_SIZE_DECIMALS = 3

# Research aliases carry a trailing perp marker and/or quote currency
# (``ETHUSDT``, ``BTC-USD``, ``kPEPE-PERP``); only these suffixes are stripped.
_PERP_SUFFIXES = ("-PERP", "PERP")
_QUOTE_SUFFIXES = ("-USDT", "USDT", "-USD", "USD")
# Hyperliquid 1000x contracts keep a lowercase ``k`` (``kPEPE``).
_THOUSAND_COIN = re.compile(r"^k[A-Z0-9]+$")


@dataclass(frozen=True)
class VenueInstrumentSpec:
    """Instrument geometry + leverage for one Hyperliquid perp in the sim."""

    coin: str
    instrument_symbol: str
    price_decimals: int
    size_decimals: int
    venue_max_leverage: float
    source: str
    leverage_capped_by_charter: bool = False

    @property
    def maintenance_rate(self) -> float:
        """Hyperliquid maintenance rate: half the max-leverage initial rate."""
        return 0.5 / float(self.venue_max_leverage)

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["maintenance_rate"] = self.maintenance_rate
        return out


def _strip_suffix(value: str, suffixes: tuple[str, ...]) -> str:
    for suffix in suffixes:
        if value.endswith(suffix) and len(value) > len(suffix):
            return value[: -len(suffix)]
    return value


def venue_coin_name(symbol: str) -> str:
    """Hyperliquid venue coin for a research symbol (one key for export and run).

    ``ETHUSDT`` / ``ETH-USD`` / ``ETH-PERP`` -> ``ETH``; ``kPEPE-PERP`` ->
    ``kPEPE`` (1000x contracts keep their lowercase ``k``); HIP-3
    ``dex:ASSET`` names are returned as written (less a ``-PERP`` suffix).
    Only a trailing perp marker and a trailing quote currency are removed, so
    a coin that merely contains ``USD`` (``SUSDE``) is never altered.
    """
    raw = str(symbol).strip()
    if ":" in raw:
        return _strip_suffix(raw, ("-PERP", "-perp"))
    coin = _strip_suffix(_strip_suffix(raw.upper(), _PERP_SUFFIXES), _QUOTE_SUFFIXES)
    if raw[:1] == "k" and raw[1 : len(coin)] == coin[1:]:
        thousand = "k" + coin[1:]
        if _THOUSAND_COIN.fullmatch(thousand):
            return thousand
    return coin


def research_symbol_to_instrument(symbol: str) -> str:
    """Research symbol -> Nautilus instrument symbol (``BTCUSDT`` -> ``BTC-PERP``)."""
    return f"{coin_for_symbol(symbol)}-PERP"


def coin_for_symbol(symbol: str) -> str:
    """Upper-case venue coin key used for metadata lookup."""
    return venue_coin_name(symbol).upper()


def charter_max_leverage(coin: str) -> float:
    return CHARTER_MAX_LEVERAGE.get(coin.upper(), ALTCOIN_MAX_LEVERAGE)


def resolve_venue_spec(
    symbol: str,
    meta: Mapping[str, Any] | None = None,
) -> VenueInstrumentSpec:
    """Resolve price/size precision and venue max leverage for ``symbol``.

    Raises :class:`UnsupportedNautilusSymbol` when neither the export nor the
    built-in table knows the asset, or the cached metadata is malformed.
    """
    raw_symbol = str(symbol or "").strip()
    if not raw_symbol:
        raise UnsupportedNautilusSymbol(raw_symbol, "empty symbol")
    instrument_symbol = research_symbol_to_instrument(raw_symbol)
    coin = instrument_symbol.removesuffix("-PERP")
    cap = charter_max_leverage(coin)

    cached = _cached_venue_meta(meta)
    if cached is not None:
        return _spec_from_cached(raw_symbol, coin, instrument_symbol, cached, cap)

    if coin == "BTC":
        return VenueInstrumentSpec(
            coin="BTC",
            instrument_symbol="BTC-PERP",
            price_decimals=_BTC_STUB_PRICE_DECIMALS,
            size_decimals=_BTC_STUB_SIZE_DECIMALS,
            venue_max_leverage=CHARTER_MAX_LEVERAGE["BTC"],
            source="builtin_btc_stub",
        )

    builtin = _BUILTIN_VENUE.get(coin)
    if builtin is None:
        raise UnsupportedNautilusSymbol(
            raw_symbol,
            "no venue metadata: cache the Hyperliquid universe entry "
            "({'szDecimals', 'maxLeverage'}) in the export meta.instrument; "
            f"built-in symbols are {sorted(_BUILTIN_VENUE)}",
        )
    size_decimals, venue_max = builtin
    return VenueInstrumentSpec(
        coin=coin,
        instrument_symbol=instrument_symbol,
        price_decimals=max(0, HL_PERP_MAX_DECIMALS - size_decimals),
        size_decimals=size_decimals,
        venue_max_leverage=min(venue_max, cap),
        source="builtin_venue_spec",
        leverage_capped_by_charter=venue_max > cap,
    )


def _cached_venue_meta(meta: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    if not meta:
        return None
    for key in ("instrument", "venue_meta"):
        value = meta.get(key)
        if isinstance(value, Mapping) and value:
            return value
    return None


def _first(cached: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if cached.get(key) is not None:
            return cached[key]
    return None


def _spec_from_cached(
    raw_symbol: str,
    coin: str,
    instrument_symbol: str,
    cached: Mapping[str, Any],
    cap: float,
) -> VenueInstrumentSpec:
    name = _first(cached, "name", "coin")
    if name is not None and str(name).strip().upper() != coin:
        raise UnsupportedNautilusSymbol(
            raw_symbol,
            f"cached venue metadata is for {name!r}, not {coin!r}",
        )
    size_raw = _first(cached, "szDecimals", "size_decimals", "sz_decimals")
    lev_raw = _first(cached, "maxLeverage", "max_leverage")
    if size_raw is None or lev_raw is None:
        raise UnsupportedNautilusSymbol(
            raw_symbol,
            "cached venue metadata needs szDecimals and maxLeverage",
        )
    try:
        size_decimals = int(size_raw)
        venue_max = float(lev_raw)
    except (TypeError, ValueError) as exc:
        raise UnsupportedNautilusSymbol(
            raw_symbol, f"cached venue metadata is not numeric: {exc}"
        ) from exc
    if size_decimals != float(size_raw) or not 0 <= size_decimals <= 8:
        raise UnsupportedNautilusSymbol(
            raw_symbol, f"szDecimals must be an integer in 0..8, got {size_raw!r}"
        )
    if not venue_max > 0:
        raise UnsupportedNautilusSymbol(
            raw_symbol, f"maxLeverage must be positive, got {lev_raw!r}"
        )
    price_raw = _first(cached, "price_decimals", "pxDecimals")
    if price_raw is None:
        price_decimals = max(0, HL_PERP_MAX_DECIMALS - size_decimals)
    else:
        try:
            price_decimals = int(price_raw)
        except (TypeError, ValueError) as exc:
            raise UnsupportedNautilusSymbol(
                raw_symbol, f"price_decimals is not an integer: {exc}"
            ) from exc
        if not 0 <= price_decimals <= 9:
            raise UnsupportedNautilusSymbol(
                raw_symbol, f"price_decimals must be in 0..9, got {price_raw!r}"
            )
    return VenueInstrumentSpec(
        coin=coin,
        instrument_symbol=instrument_symbol,
        price_decimals=price_decimals,
        size_decimals=size_decimals,
        venue_max_leverage=min(venue_max, cap),
        source="export_meta",
        leverage_capped_by_charter=venue_max > cap,
    )

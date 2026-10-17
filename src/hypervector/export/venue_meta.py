"""Offline Hyperliquid venue metadata for export bundles (never the network).

``nautilus run`` needs an instrument geometry for every symbol outside its
built-in table (BTC, ETH, SOL, HYPE): the coin's Hyperliquid ``meta.universe``
entry (``szDecimals``, ``maxLeverage``) in the bundle's ``meta.instrument``.

Exporters copy that entry from a cached ``/info`` response under the data
root when one is there:

* core perps: ``<data_root>/cache/venue/hyperliquid/meta.json``
  (``{"type": "meta"}``);
* HIP-3 ``dex:ASSET``: ``<data_root>/cache/venue/hyperliquid/meta_<dex>.json``
  (``{"type": "meta", "dex": "<dex>"}``).

Either file may hold the ``meta`` object, the ``metaAndAssetCtxs`` pair or a
bare universe list. Names match exactly (Hyperliquid coins are case-sensitive:
``kPEPE``). Nothing is fetched; when no entry is cached the exporter omits
``meta.instrument`` and writes ``meta.instrument_note`` saying how to supply it.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping

#: Data-root-relative directory of cached Hyperliquid ``/info`` meta responses.
VENUE_META_DIR = Path("cache") / "venue" / "hyperliquid"
#: Export meta key carrying the explanation when ``meta.instrument`` is omitted.
INSTRUMENT_NOTE_KEY = "instrument_note"
_INSTRUMENT_KEYS = ("instrument", "venue_meta")
_MAX_SIZE_DECIMALS = 8
_MAX_PRICE_DECIMALS = 9


def venue_coin(symbol: str) -> str | None:
    """Hyperliquid venue name for a research symbol (``kPEPE-PERP`` -> ``kPEPE``)."""
    from hypervector.data.hl import hl_coin

    try:
        coin = hl_coin(str(symbol))
    except ValueError:
        return None
    return coin or None


def _candidate_coins(symbol: str) -> list[str]:
    # The symbol as written wins (venue names are exact), then its HL alias.
    raw = str(symbol).strip()
    alias = venue_coin(raw)
    return [name for name in dict.fromkeys((raw, alias)) if name]


def needs_instrument_meta(symbol: str) -> bool:
    """True when ``nautilus run`` has no built-in geometry for ``symbol``."""
    from hypervector.nautilus.errors import UnsupportedNautilusSymbol
    from hypervector.nautilus.venue_spec import resolve_venue_spec

    try:
        resolve_venue_spec(symbol, None)
    except UnsupportedNautilusSymbol:
        return True
    return False


def venue_meta_path(data_root: Path | str, coin: str) -> Path:
    """Cache file that holds ``coin``'s universe entry (per HIP-3 dex)."""
    directory = Path(data_root) / VENUE_META_DIR
    if ":" in coin:
        return directory / f"meta_{coin.split(':', 1)[0]}.json"
    return directory / "meta.json"


def _universe(payload: Any) -> list[Any]:
    if (
        isinstance(payload, list)
        and len(payload) == 2
        and isinstance(payload[0], Mapping)
        and "universe" in payload[0]
    ):
        payload = payload[0]  # metaAndAssetCtxs: [meta, asset contexts]
    if isinstance(payload, Mapping):
        payload = payload.get("universe")
    return list(payload) if isinstance(payload, list) else []


def _names(coin: str) -> tuple[str, ...]:
    # A dex meta lists its assets either namespaced or bare.
    return (coin, coin.split(":", 1)[1]) if ":" in coin else (coin,)


def _size_decimals(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(float(value)) or float(value) != int(value):
        return None
    number = int(value)
    return number if 0 <= number <= _MAX_SIZE_DECIMALS else None


def _max_leverage(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if math.isfinite(float(value)) and value > 0 else None


def _instrument(
    entry: Mapping[str, Any], coin: str, source: str
) -> dict[str, Any] | None:
    size = _size_decimals(entry.get("szDecimals"))
    leverage = _max_leverage(entry.get("maxLeverage"))
    if size is None or leverage is None:
        return None
    out: dict[str, Any] = {
        "name": coin,
        "szDecimals": size,
        "maxLeverage": leverage,
        "source": source,
    }
    for key in ("price_decimals", "pxDecimals"):
        price = entry.get(key)
        if price is None:
            continue
        if (
            not isinstance(price, bool)
            and isinstance(price, int)
            and 0 <= price <= _MAX_PRICE_DECIMALS
        ):
            out["price_decimals"] = price
        break
    return out


def cached_instrument_meta(
    data_root: Path | str, symbol: str
) -> tuple[dict[str, Any] | None, str]:
    """The cached universe entry for ``symbol`` and a reason when there is none."""
    coins = _candidate_coins(symbol)
    if not coins or venue_coin(symbol) is None:
        return None, f"{symbol!r} is not a Hyperliquid venue name"
    reason = ""
    for coin in coins:
        path = venue_meta_path(data_root, coin)
        if not path.is_file():
            reason = reason or f"no cached venue metadata at {path}"
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            reason = reason or (
                f"cached venue metadata at {path} is unreadable ({type(exc).__name__})"
            )
            continue
        names = _names(coin)
        source = f"data_root:{(VENUE_META_DIR / path.name).as_posix()}"
        for entry in _universe(payload):
            if isinstance(entry, Mapping) and entry.get("name") in names:
                instrument = _instrument(entry, coin, source)
                if instrument is None:
                    return None, (
                        f"the {coin!r} entry in {path} needs an integer szDecimals "
                        "(0..8) and a positive maxLeverage"
                    )
                return instrument, ""
        reason = reason or f"{path} has no universe entry named {coin!r}"
    return None, reason


def instrument_note(symbol: str, reason: str, data_root: Path | str | None) -> str:
    """How to give ``nautilus run`` the geometry it needs for ``symbol``."""
    coin = venue_coin(symbol) or str(symbol)
    if data_root is None:
        where = f"<data-root>/{VENUE_META_DIR.as_posix()}/meta.json"
    else:
        where = str(venue_meta_path(data_root, coin))
    request = (
        f'{{"type": "meta", "dex": "{coin.split(":", 1)[0]}"}}'
        if ":" in coin
        else '{"type": "meta"}'
    )
    return (
        f"meta.instrument omitted ({reason}). 'nautilus run' has no built-in "
        f"geometry for {coin!r}: add its Hyperliquid meta.universe entry "
        f'({{"name": "{coin}", "szDecimals": <int>, "maxLeverage": <number>}}, '
        "optional price_decimals) as meta.instrument in this bundle's meta.json, "
        f"or save the Hyperliquid /info {request} response as {where} and "
        "re-export."
    )


def with_instrument_meta(
    meta: Mapping[str, Any], data_root: Path | str | None
) -> dict[str, Any]:
    """``meta`` plus ``instrument`` (or an ``instrument_note``) when it needs one.

    Caller-supplied ``instrument``/``venue_meta`` and built-in symbols are left
    as they are, so BTC keeps its historical stub geometry.
    """
    out = dict(meta)
    symbol = out.get("symbol")
    if not symbol or any(
        isinstance(out.get(key), Mapping) and out.get(key) for key in _INSTRUMENT_KEYS
    ):
        return out
    if not needs_instrument_meta(str(symbol)):
        return out
    if data_root is None:
        instrument, reason = None, "no data root to read cached venue metadata from"
    else:
        instrument, reason = cached_instrument_meta(data_root, str(symbol))
    if instrument is not None:
        out["instrument"] = instrument
        out.pop(INSTRUMENT_NOTE_KEY, None)
    else:
        out[INSTRUMENT_NOTE_KEY] = instrument_note(str(symbol), reason, data_root)
    return out

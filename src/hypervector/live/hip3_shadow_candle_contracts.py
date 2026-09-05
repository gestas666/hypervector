"""Exact first-observed candle identities for HIP-3 shadow evidence."""

from __future__ import annotations

from hypervector.live.hip3_breakout_shadow_specs import HIP3_SHADOW_SPECS
from hypervector.live.hip3_shadow_candle_storage import ShadowCandleContract

_INDEX_SYMBOLS = frozenset({"xyz:SP500", "xyz:SPCX"})
_REVISION_FIELDS = ("open", "high", "low", "close", "volume")
_INTERVALS = {"1m": 60_000, "15m": 900_000}


def hip3_shadow_candle_contract(symbol: str, timeframe: str) -> ShadowCandleContract:
    """Return the exact durable source contract for one shadow cadence."""
    _require_symbol(symbol)
    interval = _INTERVALS.get(timeframe)
    if interval is None:
        raise ValueError("HIP-3 shadow candle timeframe is unsupported")
    token = symbol.removeprefix("xyz:").lower()
    suffix = (
        "candle_observation" if timeframe == "15m" else "profit_lock_candle_observation"
    )
    return ShadowCandleContract(
        symbol=symbol,
        source=f"hyperliquid_public_candleSnapshot_{timeframe}",
        event_type=f"{token}_hip3_breakout_shadow_{suffix}",
        interval_ms=interval,
        maximum_observation_delay_ms=15_000,
        revision_tolerant_fields=_REVISION_FIELDS if symbol in _INDEX_SYMBOLS else (),
    )


def _require_symbol(symbol: str) -> None:
    if symbol not in {spec.symbol for spec in HIP3_SHADOW_SPECS}:
        raise ValueError("HIP-3 shadow candle symbol has no exact shadow spec")

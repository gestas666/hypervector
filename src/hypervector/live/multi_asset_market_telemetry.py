"""Bounded completed-candle payloads for the shared cohort ledger."""

from __future__ import annotations

from collections.abc import Mapping

from hypervector.live.multi_asset_intent_poller import CohortMarketBar


def unseen_market_candle_payload(
    *,
    symbols: tuple[str, ...],
    bars: Mapping[str, tuple[CohortMarketBar, ...]],
    boundaries: Mapping[str, int],
) -> tuple[dict[str, object] | None, dict[str, int]]:
    """Return new completed bars and the boundaries valid after publication."""
    if set(bars) != set(symbols):
        raise ValueError("market candle symbols differ from cohort configuration")
    next_boundaries = dict(boundaries)
    payload_bars: dict[str, list[dict[str, object]]] = {}
    for symbol in symbols:
        fresh = _fresh_symbol_bars(symbol, bars[symbol], boundaries.get(symbol))
        if not fresh:
            continue
        payload_bars[symbol] = [_bar_payload(bar) for bar in fresh]
        next_boundaries[symbol] = fresh[-1].timestamp_ms
    if not payload_bars:
        return None, next_boundaries
    return {"timeframe": "1m", "bars": payload_bars}, next_boundaries


def _fresh_symbol_bars(
    symbol: str,
    bars: tuple[CohortMarketBar, ...],
    boundary: int | None,
) -> tuple[CohortMarketBar, ...]:
    prior = -1
    for bar in bars:
        if bar.symbol != symbol:
            raise ValueError("market candle carries incorrect symbol identity")
        if bar.timestamp_ms <= prior:
            raise ValueError("market candle timestamps must be strictly increasing")
        prior = bar.timestamp_ms
    return tuple(bar for bar in bars if boundary is None or bar.timestamp_ms > boundary)


def _bar_payload(bar: CohortMarketBar) -> dict[str, object]:
    return {
        "timestamp_ms": bar.timestamp_ms,
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "volume": bar.volume,
    }

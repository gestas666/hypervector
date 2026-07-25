"""Backend-owned market telemetry payloads for read-only consumers."""

from __future__ import annotations

import math

import pandas as pd

from hypervector.paper.book import BookMicrostructure, BookSnapshot
from hypervector.strategies.indicators import bbwp, rsi


def bar_telemetry_payload(
    frame: pd.DataFrame,
    record: dict[str, object],
) -> dict[str, object]:
    """Return measured OHLCV and causal technical values for the latest bar."""
    close = frame["close"].astype(float)
    rsi_value = _finite_or_none(rsi(close, 14).iloc[-1])
    bbwp_series, _ = bbwp(close, bb_length=20, lookback=180)
    return {
        "high": float(record["high"]),
        "low": float(record["low"]),
        "volume": float(record["volume"]),
        "rsi": rsi_value,
        "bbwp_percentile": _finite_or_none(bbwp_series.iloc[-1]),
    }


def book_telemetry_payload(
    *,
    snapshot: BookSnapshot,
    metrics: BookMicrostructure,
    run_id: str,
    export_id: str,
    strategy_name: str,
    execution_mode: str,
    timeframe: str,
) -> dict[str, object]:
    """Serialize one measured L2 observation without execution authority."""
    timestamp_ms = snapshot.ts_exchange_ms or snapshot.ts_recv_ms
    feed_ts = pd.Timestamp(timestamp_ms, unit="ms", tz="UTC").isoformat()
    return {
        "feed_ts": feed_ts,
        "run_id": run_id,
        "export_id": export_id,
        "strategy_name": strategy_name,
        "symbol": snapshot.symbol,
        "timeframe": timeframe,
        "action": "book_observation",
        "source": snapshot.source,
        "exchange_ts_ms": snapshot.ts_exchange_ms,
        "recv_ts_ms": snapshot.ts_recv_ms,
        "mid_px": metrics.mid_price,
        "spread_bps": metrics.spread_bps,
        "bid_depth": metrics.bid_depth,
        "ask_depth": metrics.ask_depth,
        "bid_depth_ratio": metrics.bid_depth_ratio,
        "opi": metrics.order_pressure_index,
        "bids": [_level_payload(level.price, level.size) for level in snapshot.bids[:5]],
        "asks": [_level_payload(level.price, level.size) for level in snapshot.asks[:5]],
        "execution_mode": execution_mode,
        "submitted": False,
        "place_attempted": False,
    }


def _level_payload(price: float, size: float) -> dict[str, float]:
    return {"price": float(price), "size": float(size)}


def _finite_or_none(value: object) -> float | None:
    number = float(value)
    return number if math.isfinite(number) else None

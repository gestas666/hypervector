"""Hyperliquid candle fetch — max available HL history first (SRS_HV1_DATA_HL_FIRST).

Uses public POST https://api.hyperliquid.xyz/info candleSnapshot (no API key).
HL 1m retention is typically only a few days; longer windows still request the
full range and keep whatever HL returns (recent tail is the usual result).
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

import pandas as pd
import requests

from hypervector.data.provenance import normalize_ohlcv

if TYPE_CHECKING:
    from hypervector.paper.book import BookSnapshot

logger = logging.getLogger(__name__)

HL_INFO_URL = "https://api.hyperliquid.xyz/info"
# HL candleSnapshot pages: walk forward in ~1d chunks
_CHUNK_MS = 24 * 60 * 60 * 1000
_INTERVAL_MS = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "1h": 3_600_000}
_SLEEP_S = 0.05


def hl_coin(symbol: str) -> str:
    """Map research symbol to HL coin id (BTC-PERP → BTC)."""
    s = symbol.upper().replace("-PERP", "").replace("USDT", "").replace("USD", "")
    return s or "BTC"


def bars_from_hl_payload(raw: list[dict[str, Any]], *, source: str = "hl") -> pd.DataFrame:
    """Parse candleSnapshot JSON list into OHLCV + source."""
    rows: list[dict[str, Any]] = []
    for item in raw:
        try:
            rows.append(
                {
                    "timestamp": pd.to_datetime(int(item["t"]), unit="ms", utc=True),
                    "open": float(item["o"]),
                    "high": float(item["h"]),
                    "low": float(item["l"]),
                    "close": float(item["c"]),
                    "volume": float(item.get("v") or 0.0),
                    "source": source,
                }
            )
        except (KeyError, TypeError, ValueError):
            continue
    if not rows:
        return normalize_ohlcv(
            pd.DataFrame(
                columns=["timestamp", "open", "high", "low", "close", "volume", "source"]
            ),
            source=source,
        )
    return normalize_ohlcv(pd.DataFrame(rows), source=source)


def fetch_hl_ohlcv(
    symbol: str,
    timeframe: str,
    lookback_days: int,
    *,
    session: requests.Session | None = None,
    end_ms: int | None = None,
) -> pd.DataFrame:
    """Fetch HL candles for [now - lookback, now]. Empty frame if nothing returned."""
    if timeframe not in _INTERVAL_MS:
        raise ValueError(f"unsupported HL timeframe: {timeframe}")
    coin = hl_coin(symbol)
    end = end_ms if end_ms is not None else int(time.time() * 1000)
    start = end - int(lookback_days * 24 * 60 * 60 * 1000)
    sess = session or requests.Session()
    out_raw: list[dict[str, Any]] = []
    cursor = start
    empty_streak = 0

    while cursor < end:
        chunk_end = min(cursor + _CHUNK_MS, end)
        payload = {
            "type": "candleSnapshot",
            "req": {
                "coin": coin,
                "interval": timeframe,
                "startTime": int(cursor),
                "endTime": int(chunk_end),
            },
        }
        resp = sess.post(HL_INFO_URL, json=payload, timeout=30)
        resp.raise_for_status()
        raw = resp.json()
        if not isinstance(raw, list) or not raw:
            empty_streak += 1
            cursor = chunk_end + _INTERVAL_MS[timeframe]
            # Long lookbacks often empty early; jump toward recent retention window
            if empty_streak >= 3 and not out_raw:
                probe = max(start, end - 5 * _CHUNK_MS)
                if cursor < probe:
                    cursor = probe
                    empty_streak = 0
                    continue
            if empty_streak >= 8:
                break
            time.sleep(_SLEEP_S)
            continue
        empty_streak = 0
        out_raw.extend(raw)
        last_t = int(raw[-1]["t"])
        if last_t <= cursor:
            break
        cursor = last_t + _INTERVAL_MS[timeframe]
        time.sleep(_SLEEP_S)

    df = bars_from_hl_payload(out_raw, source="hl")
    if len(df):
        ts = pd.to_datetime(df["timestamp"], utc=True)
        mask = (ts >= pd.to_datetime(start, unit="ms", utc=True)) & (
            ts <= pd.to_datetime(end, unit="ms", utc=True)
        )
        df = df.loc[mask].drop_duplicates(subset=["timestamp"]).reset_index(drop=True)
    logger.info("HL %s %s lookback=%sd → %d bars", coin, timeframe, lookback_days, len(df))
    return df


def fetch_hl_l2_book(
    symbol: str,
    *,
    session: requests.Session | None = None,
) -> BookSnapshot:
    """Fetch HL public L2 book (info type ``l2Book``) as a BookSnapshot.

    POST body: ``{"type": "l2Book", "coin": <hl_coin>}``.
    Raises ``RuntimeError`` on HTTP or parse failure.
    """
    # Deferred import avoids data↔paper cycle at module load
    from hypervector.paper.book import parse_hl_l2_payload

    coin = hl_coin(symbol)
    sess = session or requests.Session()
    payload = {"type": "l2Book", "coin": coin}
    try:
        resp = sess.post(HL_INFO_URL, json=payload, timeout=30)
        resp.raise_for_status()
        raw = resp.json()
    except Exception as exc:  # noqa: BLE001 — wrap all transport failures
        raise RuntimeError(f"HL l2Book fetch failed for {coin}: {exc}") from exc

    ts_recv_ms = time.time() * 1000.0
    try:
        return parse_hl_l2_payload(
            raw,
            symbol=symbol,
            ts_recv_ms=ts_recv_ms,
            source="hl_rest_l2",
        )
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"HL l2Book parse failed for {coin}: {exc}") from exc

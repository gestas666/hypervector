"""Binance then Bybit public kline backfill (SRS_HV1_DATA_BACKFILL).

Price-path assistance only — not Hyperliquid microstructure. No API keys.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import pandas as pd
import requests

from hypervector.data.provenance import normalize_ohlcv

logger = logging.getLogger(__name__)

BINANCE_KLINE_ENDPOINTS: list[tuple[str, str]] = [
    ("binance_vision_spot", "https://data-api.binance.vision/api/v3/klines"),
    ("binance_us_spot", "https://api.binance.us/api/v3/klines"),
    ("binance_spot", "https://api.binance.com/api/v3/klines"),
    ("binance_fapi", "https://fapi.binance.com/fapi/v1/klines"),
]

BYBIT_KLINE_URL = "https://api.bybit.com/v5/market/kline"
_BATCH = 1000
_SLEEP_S = 0.2

_TF_BINANCE = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1h"}
_TF_BYBIT = {"1m": "1", "5m": "5", "15m": "15", "1h": "60"}
_INTERVAL_MS = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "1h": 3_600_000}


def binance_symbol(symbol: str) -> str:
    s = symbol.upper().replace("-PERP", "")
    if s.endswith("USDT"):
        return s
    if s in ("BTC", "ETH", "SOL"):
        return f"{s}USDT"
    return f"{s}USDT"


def bybit_symbol(symbol: str) -> str:
    return binance_symbol(symbol)


def bars_from_binance_klines(
    raw: list[list[Any]], *, source: str = "binance"
) -> pd.DataFrame:
    """Parse Binance/fapi kline arrays into OHLCV."""
    rows: list[dict[str, Any]] = []
    for k in raw:
        try:
            rows.append(
                {
                    "timestamp": pd.to_datetime(int(k[0]), unit="ms", utc=True),
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                    "source": source,
                }
            )
        except (IndexError, TypeError, ValueError):
            continue
    if not rows:
        return normalize_ohlcv(
            pd.DataFrame(
                columns=[
                    "timestamp",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "source",
                ]
            ),
            source=source,
        )
    return normalize_ohlcv(pd.DataFrame(rows), source=source)


def bars_from_bybit_list(
    raw: list[list[Any]], *, source: str = "bybit"
) -> pd.DataFrame:
    """Parse Bybit v5 kline list (often newest-first): [start, open, high, low, close, volume, ...]."""
    rows: list[dict[str, Any]] = []
    for k in raw:
        try:
            rows.append(
                {
                    "timestamp": pd.to_datetime(int(k[0]), unit="ms", utc=True),
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                    "source": source,
                }
            )
        except (IndexError, TypeError, ValueError):
            continue
    if not rows:
        return normalize_ohlcv(
            pd.DataFrame(
                columns=[
                    "timestamp",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "source",
                ]
            ),
            source=source,
        )
    return normalize_ohlcv(pd.DataFrame(rows), source=source)


def _pick_binance_endpoint(
    sess: requests.Session, symbol: str, interval: str, probe_start: int
) -> str:
    for name, url in BINANCE_KLINE_ENDPOINTS:
        try:
            r = sess.get(
                url,
                params={
                    "symbol": symbol,
                    "interval": interval,
                    "startTime": probe_start,
                    "limit": 5,
                },
                timeout=20,
            )
            if r.ok and isinstance(r.json(), list) and r.json():
                logger.info("Binance endpoint selected: %s", name)
                return url
        except requests.RequestException:
            continue
    raise RuntimeError("no Binance kline endpoint available")


def fetch_binance_ohlcv(
    symbol: str,
    timeframe: str,
    lookback_days: int,
    *,
    session: requests.Session | None = None,
    end_ms: int | None = None,
) -> pd.DataFrame:
    if timeframe not in _TF_BINANCE:
        raise ValueError(f"unsupported Binance timeframe: {timeframe}")
    pair = binance_symbol(symbol)
    interval = _TF_BINANCE[timeframe]
    end = end_ms if end_ms is not None else int(time.time() * 1000)
    start = end - int(lookback_days * 24 * 60 * 60 * 1000)
    sess = session or requests.Session()
    url = _pick_binance_endpoint(sess, pair, interval, max(start, end - 3_600_000))
    raw_all: list[list[Any]] = []
    cursor = start
    while cursor < end:
        r = sess.get(
            url,
            params={
                "symbol": pair,
                "interval": interval,
                "startTime": cursor,
                "endTime": end,
                "limit": _BATCH,
            },
            timeout=30,
        )
        r.raise_for_status()
        page = r.json()
        if not isinstance(page, list) or not page:
            break
        raw_all.extend(page)
        last = int(page[-1][0])
        if last <= cursor:
            break
        cursor = last + _INTERVAL_MS[timeframe]
        if len(page) < _BATCH:
            break
        time.sleep(_SLEEP_S)

    df = bars_from_binance_klines(raw_all, source="binance")
    if len(df):
        df = df.drop_duplicates(subset=["timestamp"]).reset_index(drop=True)
    logger.info(
        "Binance %s %s lookback=%sd → %d bars", pair, timeframe, lookback_days, len(df)
    )
    return df


def fetch_bybit_ohlcv(
    symbol: str,
    timeframe: str,
    lookback_days: int,
    *,
    session: requests.Session | None = None,
    end_ms: int | None = None,
) -> pd.DataFrame:
    if timeframe not in _TF_BYBIT:
        raise ValueError(f"unsupported Bybit timeframe: {timeframe}")
    pair = bybit_symbol(symbol)
    interval = _TF_BYBIT[timeframe]
    end = end_ms if end_ms is not None else int(time.time() * 1000)
    start = end - int(lookback_days * 24 * 60 * 60 * 1000)
    sess = session or requests.Session()
    raw_all: list[list[Any]] = []
    # Bybit returns newest first; page backward from end
    cursor_end = end
    while cursor_end > start:
        r = sess.get(
            BYBIT_KLINE_URL,
            params={
                "category": "linear",
                "symbol": pair,
                "interval": interval,
                "start": start,
                "end": cursor_end,
                "limit": _BATCH,
            },
            timeout=30,
        )
        r.raise_for_status()
        body = r.json()
        if body.get("retCode") not in (0, "0", None):
            raise RuntimeError(f"Bybit error: {body.get('retMsg')}")
        page = (body.get("result") or {}).get("list") or []
        if not page:
            break
        raw_all.extend(page)
        # list is newest-first; oldest in this page is last element
        oldest = int(page[-1][0])
        if oldest >= cursor_end:
            break
        cursor_end = oldest - 1
        if len(page) < _BATCH:
            break
        time.sleep(_SLEEP_S)

    df = bars_from_bybit_list(raw_all, source="bybit")
    if len(df):
        ts = pd.to_datetime(df["timestamp"], utc=True)
        t0 = pd.to_datetime(start, unit="ms", utc=True)
        t1 = pd.to_datetime(end, unit="ms", utc=True)
        df = (
            df.loc[(ts >= t0) & (ts <= t1)]
            .drop_duplicates(subset=["timestamp"])
            .reset_index(drop=True)
        )
    logger.info(
        "Bybit %s %s lookback=%sd → %d bars", pair, timeframe, lookback_days, len(df)
    )
    return df

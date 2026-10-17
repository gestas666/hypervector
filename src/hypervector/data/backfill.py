"""Binance then Bybit public kline backfill (SRS_HV1_DATA_BACKFILL).

Price-path assistance only — not Hyperliquid microstructure. No API keys.
"""

from __future__ import annotations

import logging
import re
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


class BackfillUnavailable(RuntimeError):
    """The venue lists no instrument equivalent to the requested HL symbol.

    Distinct from transport or server failures: retrying cannot help, so the
    history pipeline records it and keeps the HL candles it already has.
    """


# HL 1000x contracts (kPEPE, kSHIB, kBONK, ...) quote 1000 units, like the
# venues' 1000PEPEUSDT perps; the 1-unit spot pairs would be 1000x off in price.
_THOUSAND_COIN = re.compile(r"^k([A-Z0-9]+)$")
# Endpoint answers that mean "this endpoint is unusable here", not "no symbol".
_ENDPOINT_BLOCKED_STATUSES = frozenset({401, 403, 451})
_BYBIT_INVALID_SYMBOL_CODES = frozenset({10001})


def binance_symbol(symbol: str) -> str:
    raw = symbol.strip()
    if ":" in raw:
        raise BackfillUnavailable(f"HIP-3 symbol {raw} has no Binance/Bybit equivalent")
    base = raw.replace("-PERP", "").replace("-perp", "")
    thousand = _THOUSAND_COIN.fullmatch(base.removesuffix("USDT"))
    if thousand is not None:
        return f"1000{thousand.group(1)}USDT"
    s = base.upper()
    if s.endswith("USDT"):
        return s
    return f"{s}USDT"


def bybit_symbol(symbol: str) -> str:
    return binance_symbol(symbol)


def bars_from_binance_klines(raw: list[list[object]], *, source: str = "binance") -> pd.DataFrame:
    """Parse Binance kline arrays with the shared venue-array contract."""
    return _bars_from_klines(raw, source=source)


def bars_from_bybit_list(raw: list[list[object]], *, source: str = "bybit") -> pd.DataFrame:
    """Parse Bybit kline arrays with the shared venue-array contract."""
    return _bars_from_klines(raw, source=source)


def _pick_binance_endpoint(
    sess: requests.Session, symbol: str, interval: str, probe_start: int
) -> str:
    """Return the first endpoint serving ``symbol``.

    Raises :class:`BackfillUnavailable` only when every reachable endpoint
    rejected the symbol (HTTP 400/404 or no klines); a transport error, 429 or
    5xx on any endpoint keeps the plain ``RuntimeError`` so outages stay loud.
    """
    rejected: list[str] = []
    failed: list[str] = []
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
        except requests.RequestException as exc:
            failed.append(f"{name}: {type(exc).__name__}")
            continue
        if r.ok:
            try:
                body = r.json()
            except ValueError:
                failed.append(f"{name}: non-JSON body")
                continue
            if isinstance(body, list) and body:
                logger.info("Binance endpoint selected: %s", name)
                return url
            rejected.append(f"{name}: no klines")
        elif r.status_code in (400, 404):
            rejected.append(f"{name}: HTTP {r.status_code}")
        elif r.status_code in _ENDPOINT_BLOCKED_STATUSES:
            continue
        else:
            failed.append(f"{name}: HTTP {r.status_code}")
    detail = "; ".join(failed + rejected) or "all endpoints blocked"
    if rejected and not failed:
        raise BackfillUnavailable(f"Binance lists no klines for {symbol} ({detail})")
    raise RuntimeError(f"no Binance kline endpoint available for {symbol}: {detail}")


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
        code = body.get("retCode")
        if code not in (0, "0", None):
            message = str(body.get("retMsg"))
            if _bybit_rejects_symbol(code, message):
                raise BackfillUnavailable(f"Bybit lists no {pair}: {message}")
            raise RuntimeError(f"Bybit error: {message}")
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


def _bybit_rejects_symbol(code: object, message: str) -> bool:
    try:
        numeric = int(str(code))
    except ValueError:
        return False
    return numeric in _BYBIT_INVALID_SYMBOL_CODES and "symbol" in message.lower()


def _bars_from_klines(
    raw: list[list[object]], *, source: str
) -> pd.DataFrame:
    """Parse the shared REST array layout, validating every retained row."""
    rows: list[dict[str, object]] = []
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

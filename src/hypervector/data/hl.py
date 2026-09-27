"""Hyperliquid candle fetch — max available HL history first (SRS_HV1_DATA_HL_FIRST).

Uses public POST https://api.hyperliquid.xyz/info candleSnapshot (no API key).
HL 1m retention is typically only a few days; longer windows still request the
full range and keep whatever HL returns (recent tail is the usual result).
"""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import pandas as pd
import requests

from hypervector.data.oxa_api import validate_hip3_symbol
from hypervector.data.provenance import normalize_ohlcv

if TYPE_CHECKING:
    from hypervector.paper.book import BookSnapshot

logger = logging.getLogger(__name__)

HL_INFO_URL = "https://api.hyperliquid.xyz/info"
# HL candleSnapshot pages: walk forward in ~1d chunks
_CHUNK_MS = 24 * 60 * 60 * 1000
_FUNDING_CADENCE_MS = 60 * 60 * 1000
_FUNDING_MAX_PAGES = 100
_INTERVAL_MS = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "1h": 3_600_000}
_SLEEP_S = 0.05
_MILLIS_PER_DAY = 24 * 60 * 60 * 1000
_SNAPSHOT_RETRY_DELAYS = (1.0, 2.0, 4.0)
_SNAPSHOT_TIMEOUT_SECONDS = 30
_SNAPSHOT_RETRYABLE_HTTP_STATUSES = frozenset({429, 500, 502, 503, 504})
_MAX_RETRY_AFTER_SECONDS = 15.0


def hl_coin(symbol: str) -> str:
    """Map native aliases while preserving an exact HIP-3 ``dex:ASSET`` name."""
    raw = symbol.strip()
    if ":" in raw:
        validate_hip3_symbol(raw)
        return raw
    s = raw.upper().replace("-PERP", "").replace("USDT", "").replace("USD", "")
    return s or "BTC"


def bars_from_hl_payload(
    raw: list[dict[str, Any]], *, source: str = "hl"
) -> pd.DataFrame:
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


def funding_from_hl_payload(raw: list[dict[str, Any]]) -> pd.DataFrame:
    """Parse public funding-history rows into UTC hourly observations."""
    rows: list[dict[str, Any]] = []
    for item in raw:
        try:
            timestamp = pd.to_datetime(int(item["time"]), unit="ms", utc=True).floor(
                "h"
            )
            rate = float(item["fundingRate"])
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if not math.isfinite(rate):
            continue
        rows.append(
            {
                "timestamp": timestamp,
                "funding_rate": rate,
                "source": "hl_funding_history",
            }
        )
    columns = ["timestamp", "funding_rate", "source"]
    if not rows:
        return pd.DataFrame(columns=columns)
    return (
        pd.DataFrame(rows, columns=columns)
        .sort_values("timestamp")
        .drop_duplicates(subset=["timestamp"], keep="last")
        .reset_index(drop=True)
    )


def fetch_hl_funding_history(
    symbol: str,
    *,
    start_time: pd.Timestamp,
    end_time: pd.Timestamp,
    session: requests.Session | None = None,
) -> pd.DataFrame:
    """Fetch complete public Hyperliquid funding rows for an inclusive interval."""
    pages = fetch_hl_funding_pages(
        symbol,
        start_time=start_time,
        end_time=end_time,
        session=session,
    )
    raw = [row for page in pages for row in page]
    return funding_from_hl_payload(raw)


def fetch_hl_funding_pages(
    symbol: str,
    *,
    start_time: pd.Timestamp,
    end_time: pd.Timestamp,
    session: requests.Session | None = None,
) -> tuple[tuple[dict[str, Any], ...], ...]:
    """Return complete raw funding pages for immutable evidence storage."""
    start_ms = _timestamp_millis(start_time)
    end_ms = _timestamp_millis(end_time)
    if end_ms < start_ms:
        raise ValueError("funding-history end_time must not precede start_time")
    sess = session or requests.Session()
    pages = _fetch_hl_funding_pages(sess, hl_coin(symbol), start_ms, end_ms)
    return tuple(tuple(page) for page in pages)


def _fetch_hl_funding_pages(
    session: requests.Session, coin: str, start_ms: int, end_ms: int
) -> list[list[dict[str, Any]]]:
    pages: list[list[dict[str, Any]]] = []
    cursor = start_ms
    for _ in range(_FUNDING_MAX_PAGES):
        page = _request_hl_funding_page(session, coin, cursor, end_ms)
        if not page:
            return pages
        last_ms = _last_funding_ms(page)
        if last_ms < cursor:
            raise RuntimeError("HL funding-history page did not advance")
        pages.append(page)
        if last_ms >= end_ms - _FUNDING_CADENCE_MS:
            return pages
        cursor = last_ms + 1
    raise RuntimeError("HL funding-history max pages exhausted before end coverage")


def _request_hl_funding_page(
    session: requests.Session, coin: str, start_ms: int, end_ms: int
) -> list[dict[str, Any]]:
    payload = {
        "type": "fundingHistory",
        "coin": coin,
        "startTime": int(start_ms),
        "endTime": end_ms,
    }
    response = session.post(HL_INFO_URL, json=payload, timeout=30)
    response.raise_for_status()
    raw = response.json()
    if not isinstance(raw, list):
        raise RuntimeError("HL fundingHistory response must be a list")
    if not all(isinstance(row, dict) for row in raw):
        raise RuntimeError("HL fundingHistory rows must be objects")
    return raw


def _last_funding_ms(raw: list[dict[str, Any]]) -> int:
    try:
        return max(int(row["time"]) for row in raw)
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("HL fundingHistory row has invalid time") from exc


def _timestamp_millis(value: pd.Timestamp) -> int:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    return int(timestamp.value // 1_000_000)


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
    logger.info(
        "HL %s %s lookback=%sd → %d bars", coin, timeframe, lookback_days, len(df)
    )
    return df


def fetch_hl_ohlcv_snapshot(
    symbol: str,
    timeframe: str,
    lookback_days: float,
    *,
    session: requests.Session | None = None,
    end_ms: int | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    timeout: float | tuple[float, float] = _SNAPSHOT_TIMEOUT_SECONDS,
    stop_check: Callable[[], None] | None = None,
) -> pd.DataFrame:
    """Fetch one bounded recent candle snapshot for latency-sensitive polling.

    ``timeout`` is passed to every attempt as given. ``stop_check``, when
    supplied, runs before every attempt and after every failed one, and an
    exception it raises abandons the read, so a stopping caller never waits out
    the retry ladder. Callers that pass neither keep the 30 s ladder unchanged.
    """
    if timeframe not in _INTERVAL_MS:
        raise ValueError(f"unsupported HL timeframe: {timeframe}")
    if isinstance(lookback_days, bool) or lookback_days <= 0.0:
        raise ValueError("HL snapshot lookback_days must be positive")
    end = end_ms if end_ms is not None else int(time.time() * 1000)
    start = end - int(float(lookback_days) * _MILLIS_PER_DAY)
    payload = {
        "type": "candleSnapshot",
        "req": {
            "coin": hl_coin(symbol),
            "interval": timeframe,
            "startTime": start,
            "endTime": end,
        },
    }
    response = _request_hl_candle_snapshot(
        session or requests.Session(),
        payload,
        sleep_fn,
        timeout=timeout,
        stop_check=stop_check,
    )
    try:
        raw = response.json()
    except ValueError as exc:
        # A gateway that rewrites the body still returns 200; classify it as the
        # transport degradation it is so the cohort degrades and still runs its
        # unconditional deadline exits, instead of hard-exiting the backend.
        raise requests.exceptions.InvalidJSONError(
            "HL candleSnapshot response is not JSON", response=response
        ) from exc
    if not isinstance(raw, list):
        raise requests.exceptions.InvalidJSONError(
            "HL candleSnapshot response must be a list", response=response
        )
    frame = bars_from_hl_payload(raw, source="hl")
    return _bounded_candle_frame(frame, start, end)


def _request_hl_candle_snapshot(
    session: requests.Session,
    payload: dict[str, object],
    sleep_fn: Callable[[float], None],
    *,
    timeout: float | tuple[float, float] = _SNAPSHOT_TIMEOUT_SECONDS,
    stop_check: Callable[[], None] | None = None,
) -> requests.Response:
    attempts = len(_SNAPSHOT_RETRY_DELAYS) + 1
    for attempt in range(attempts):
        _run_stop_check(stop_check)
        try:
            response = session.post(HL_INFO_URL, json=payload, timeout=timeout)
        except requests.RequestException as exc:
            # Raised from here, a stop keeps the transport failure as its context.
            _run_stop_check(stop_check)
            if attempt == attempts - 1:
                raise
            delay = _SNAPSHOT_RETRY_DELAYS[attempt]
            logger.warning(
                "HL candle snapshot transport %s; retrying in %.1fs",
                type(exc).__name__,
                delay,
            )
            sleep_fn(delay)
            continue
        if response.status_code not in _SNAPSHOT_RETRYABLE_HTTP_STATUSES:
            response.raise_for_status()
            return response
        _run_stop_check(stop_check)
        if attempt == attempts - 1:
            response.raise_for_status()
        delay = _snapshot_retry_delay(response, attempt)
        logger.warning(
            "HL candle snapshot HTTP %d; retrying in %.1fs",
            response.status_code,
            delay,
        )
        sleep_fn(delay)
    raise RuntimeError("HL candle snapshot retry loop exhausted")


def _run_stop_check(stop_check: Callable[[], None] | None) -> None:
    if stop_check is not None:
        stop_check()


def _snapshot_retry_delay(response: requests.Response, attempt: int) -> float:
    raw = response.headers.get("Retry-After")
    try:
        requested = float(raw) if raw is not None else 0.0
    except ValueError:
        requested = 0.0
    if math.isnan(requested):
        # NaN would pass through min/max below, and no sleep accepts it.
        requested = 0.0
    fallback = _SNAPSHOT_RETRY_DELAYS[attempt]
    return min(max(requested, fallback), _MAX_RETRY_AFTER_SECONDS)


def _bounded_candle_frame(
    frame: pd.DataFrame,
    start_ms: int,
    end_ms: int,
) -> pd.DataFrame:
    if frame.empty:
        return frame
    times = pd.to_datetime(frame["timestamp"], utc=True)
    within = (times >= pd.to_datetime(start_ms, unit="ms", utc=True)) & (
        times <= pd.to_datetime(end_ms, unit="ms", utc=True)
    )
    return (
        frame.loc[within].drop_duplicates(subset=["timestamp"]).reset_index(drop=True)
    )


def fetch_hl_l2_book(
    symbol: str,
    *,
    session: requests.Session | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
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
        resp = _request_hl_l2_book(sess, payload, sleep_fn)
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


def _request_hl_l2_book(
    session: requests.Session,
    payload: dict[str, object],
    sleep_fn: Callable[[float], None],
) -> requests.Response:
    """Fetch one L2 response with the bounded public-read retry contract."""
    attempts = len(_SNAPSHOT_RETRY_DELAYS) + 1
    for attempt in range(attempts):
        try:
            response = session.post(HL_INFO_URL, json=payload, timeout=30)
        except requests.RequestException as exc:
            if attempt == attempts - 1:
                raise
            delay = _SNAPSHOT_RETRY_DELAYS[attempt]
            logger.warning(
                "HL L2 transport %s; retrying in %.1fs",
                type(exc).__name__,
                delay,
            )
            sleep_fn(delay)
            continue
        if response.status_code != 429:
            response.raise_for_status()
            return response
        if attempt == attempts - 1:
            response.raise_for_status()
        delay = _snapshot_retry_delay(response, attempt)
        logger.warning("HL L2 throttled; retrying in %.1fs", delay)
        sleep_fn(delay)
    raise RuntimeError("HL L2 retry loop exhausted")

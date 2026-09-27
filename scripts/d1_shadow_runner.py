#!/usr/bin/env python3
"""Observe-only D1 Donchian 20/10 swing shadow runner (research lane, Sleeve S1).

execution_authority: none. The runner builds no venue client, signs nothing,
reads no secret and imports nothing from ``hypervector``. Its only network peer
is Binance public market data (``data-api.binance.vision`` spot klines); it
never calls Hyperliquid. Egress is pinned at the transport: every send passes
an allow-list guard (HTTPS GET to that one host, counted per host for the run
log), redirects are never followed, and the HTTP session ignores the
environment (no ~/.netrc credentials, proxy or CA-bundle variables). The
Hyperliquid universe, volumes and ``maxLeverage`` come from a local census CSV
passed by argument.

Pre-registered rule set (Sleeve S1 of the 2026-09-26 swing synthesis):

- Universe, frozen once per month and recorded: the top 25 Hyperliquid main-dex
  crypto perps by census volume that also have a Binance USDT spot pair with at
  least 90 completed daily bars before the month starts. Census volume is the
  trailing 30-day column when the CSV has one, else the 24h ``dayNtlVlm``
  snapshot; the ``universe_frozen`` event records which. A Binance pair priced
  more than 2x away from the census ``markPx`` is a ticker collision and is
  rejected.
- Entry on the completed daily close: long when the close exceeds the highest
  high of the 20 bars before the signal bar, short when it is below their lowest
  low (the signal bar is excluded). The fill is the next 00:00 UTC open.
- Initial stop 2 x Wilder ATR(20) of the signal bar from that fill. Stops are
  checked intrabar on the daily high/low; a later bar that opens beyond the stop
  fills at that open (gap-through).
- Exit when the close breaks the opposite 10-bar channel (prior bars), at the
  next open. No max hold. Shorts are labelled ``hedge``.
- Per-asset signals follow the research engine's always-in convention: an entry
  that loses the slot race stays a virtual trade (``taken: false``) and blocks a
  new entry on that asset until it exits, exactly as in the backtest.
- At most 10 taken positions and gross notional <= 1.5 x book equity (a partial
  size down to 25% of the wanted size is allowed, as in the backtest).
  Same-day entries are ranked by trailing 30-day Binance quote volume through
  the signal bar (no look-ahead), then census rank, then coin.
- Size: 0.5% of a static notional book equity at stop. Leverage
  L = min(3, floor(1 / (MMR + 2.5 x stop))), capped at 2 for shorts, with
  MMR = 1 / (2 x maxLeverage) from the census.

Daily context tags: BTC close vs SMA200 (the beta-sleeve switch state) and the
SMA50/SMA200 state of BTC, ETH and SOL. No signal depends on them.

Ledger: append-only JSONL. Event types: ``universe_frozen``, ``signal``,
``hypothetical_entry``, ``hypothetical_stop_hit``, ``hypothetical_exit``,
``regime_tag`` and ``daily_mark``. Each completed bar ends with one
``daily_mark`` carrying the engine state, so a run resumes from the last mark
and processes only new completed bars; every event has a deterministic
``event_id`` and a re-derived event must match the stored one byte for byte, so
re-running the same UTC day appends nothing. Each ``daily_mark`` also carries
``ledger_chain_before``, a hash chain over every earlier line, so a deleted,
inserted or reordered line is detected. Entries and gap exits at today's open
are recorded as soon as the open exists (runs after 00:05 UTC). A day's bar is
treated as final only when the same response already has a later bar or an
hour has passed since the close; otherwise the day is deferred to the next run.
A missing bar for a symbol the book holds, a torn or edited ledger line, a
ledger conflict, a changed configuration or a census older than the freshness
limit at a monthly freeze stops the run fail-closed (exit code 2); only fully
completed days are ever appended.
"""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
import copy
from dataclasses import asdict, dataclass, field, fields
from datetime import UTC, date, datetime, timedelta
import fcntl
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import sys
import time
import traceback
from typing import Any, NamedTuple, Protocol
from urllib.parse import urlparse

import numpy as np
import pandas as pd
import requests
from requests.adapters import BaseAdapter, HTTPAdapter

SCHEMA = "d1_shadow_ledger_v1"
EXECUTION_AUTHORITY = "none"
REPO_ROOT = Path(__file__).resolve().parents[1]
RESEARCH_DIR = REPO_ROOT / "data" / "research" / "d1_shadow"
DEFAULT_LEDGER = RESEARCH_DIR / "ledger.jsonl"
DEFAULT_CENSUS = RESEARCH_DIR / "census_perps.csv"

BINANCE_DATA_URL = "https://data-api.binance.vision"
ALLOWED_DATA_HOSTS = frozenset({"data-api.binance.vision"})
KLINES_PATH = "/api/v3/klines"
KLINE_PAGE_LIMIT = 1000
MAX_KLINE_PAGES = 12
# Bars fetched before the first day a run processes: SMA200 needs 200, and the
# Wilder ATR seed's weight decays to ~(19/20)^380 by the first processed bar.
WARMUP_BARS = 400
SETTLE_DELAY = timedelta(minutes=5)
# A completed bar is final once the same response holds a later bar, or once
# this long has passed since the UTC close (a stale cached response is ruled out).
FINALITY_GRACE = timedelta(hours=1)
MAX_CENSUS_AGE_DAYS = 7
USER_AGENT = "hypervector-d1-shadow/1 (observe-only research)"

ENTRY_BARS = 20
EXIT_BARS = 10
ATR_BARS = 20
STOP_ATR_MULT = 2.0
PRIORITY_VOLUME_BARS = 30
SMA_FAST = 50
SMA_SLOW = 200
LONG_LEVERAGE_CAP = 3
SHORT_LEVERAGE_CAP = 2
LIQUIDATION_BUFFER_STOPS = 2.5
REGIME_COINS = ("BTC", "ETH", "SOL")
PRIORITY_RULE = (
    "trailing 30-day Binance USDT quote volume through the signal bar, "
    "descending; then census rank; then coin"
)
VOLUME_COLUMN_PREFERENCE = ("ntlVlm30d", "vlm30d", "trailing30dNtlVlm", "dayNtlVlm")
SNAPSHOT_VOLUME_COLUMN = "dayNtlVlm"
BAR_COLUMNS = ("open", "high", "low", "close", "quote_volume")
MAX_CENSUS_PRICE_RATIO = 2.0
PRICE_CHECK_MAX_AGE_DAYS = 7
EVENT_TYPES = frozenset(
    {
        "universe_frozen",
        "signal",
        "hypothetical_entry",
        "hypothetical_stop_hit",
        "hypothetical_exit",
        "daily_mark",
        "regime_tag",
    }
)
_UNHASHED_FIELDS = frozenset({"recorded_at", "mode", "content_digest"})
CHAIN_GENESIS = hashlib.sha256(f"{SCHEMA}|genesis".encode()).hexdigest()[:32]
_KILO_PREFIX = re.compile(r"k[A-Z0-9]{2,}")
# HL coin -> Binance base where the tickers differ beyond the 1000x ``k`` prefix.
BINANCE_BASE_OVERRIDES: dict[str, str] = {}


class ShadowError(RuntimeError):
    """A fail-closed condition: the run stops and appends nothing further."""


class LedgerError(ShadowError):
    """The ledger is unreadable, inconsistent or belongs to another config."""


class CensusError(ShadowError):
    """The census CSV is missing or lacks the columns the universe rule needs."""


class DataFetchError(ShadowError):
    """Binance public data could not be fetched."""


class EgressRefusedError(ShadowError):
    """A request or response involved a host outside the market-data allow-list."""


class DataGapError(ShadowError):
    """A symbol the book holds has no completed bar for a day being processed."""


class EngineInvariantError(ShadowError):
    """The engine state contradicts the rule set."""


class SymbolUnavailableError(Exception):
    """Binance has no such USDT spot pair."""


# ----------------------------------------------------------------- config


@dataclass(frozen=True)
class ShadowConfig:
    book_equity: float = 4800.0
    risk_fraction: float = 0.005
    max_slots: int = 10
    gross_cap: float = 1.5
    min_fill_fraction: float = 0.25
    funding_apr: float = 0.1095
    fee_bps: float = 4.32
    universe_size: int = 25
    min_history_bars: int = 90

    def validate(self) -> None:
        if not (math.isfinite(self.book_equity) and self.book_equity > 0):
            raise ShadowError("book equity must be a positive number")
        if not (0 < self.risk_fraction < 1):
            raise ShadowError("risk fraction must be in (0, 1)")
        if not math.isfinite(self.funding_apr):
            raise ShadowError("funding APR must be finite")
        if not (math.isfinite(self.fee_bps) and self.fee_bps >= 0):
            raise ShadowError("fee bps must be a non-negative number")
        if self.max_slots < 1 or self.universe_size < 1:
            raise ShadowError("slots and universe size must be positive")

    def as_record(self) -> dict[str, Any]:
        record = asdict(self)
        record["spec"] = {
            "entry_bars": ENTRY_BARS,
            "exit_bars": EXIT_BARS,
            "atr_bars": ATR_BARS,
            "stop_atr_mult": STOP_ATR_MULT,
            "priority_volume_bars": PRIORITY_VOLUME_BARS,
            "long_leverage_cap": LONG_LEVERAGE_CAP,
            "short_leverage_cap": SHORT_LEVERAGE_CAP,
            "liquidation_buffer_stops": LIQUIDATION_BUFFER_STOPS,
            "priority_rule": PRIORITY_RULE,
            "sizing_equity": "static_notional",
        }
        return record

    def fingerprint(self) -> str:
        return _sha256(_canonical(self.as_record()))[:16]


# ----------------------------------------------------------------- helpers


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _canonical(value: Any) -> str:
    return json.dumps(
        _jsonable(value), sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _finite(value: float | None) -> bool:
    return value is not None and math.isfinite(value)


def _month_key(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def _days(start: date, end: date) -> Iterable[date]:
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


def _truthy(value: Any) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    return str(value).strip().lower() in {"true", "1", "yes"}


def binance_symbol_for(coin: str) -> str:
    """Binance USDT spot symbol for a Hyperliquid main-dex coin."""
    base = BINANCE_BASE_OVERRIDES.get(coin)
    if base is None:
        base = coin[1:] if _KILO_PREFIX.fullmatch(coin) else coin
    return f"{base.upper()}USDT"


def leverage_for(
    stop_fraction: float, max_leverage: float, direction: int
) -> tuple[int, float, float, bool]:
    """Isolated leverage L = min(cap, floor(1 / (MMR + 2.5 x stop))), at least 1.

    Returns (leverage, mmr, liquidation distance, liquidation >= 2.5 stops away).
    """
    mmr = 1.0 / (2.0 * max_leverage)
    raw = math.floor(1.0 / (mmr + LIQUIDATION_BUFFER_STOPS * stop_fraction) + 1e-9)
    cap = LONG_LEVERAGE_CAP if direction > 0 else SHORT_LEVERAGE_CAP
    leverage = max(1, min(cap, math.floor(max_leverage + 1e-9), raw))
    distance = 1.0 / leverage - mmr
    return leverage, mmr, distance, distance >= LIQUIDATION_BUFFER_STOPS * stop_fraction


# ----------------------------------------------------------------- market data


class BarRow(NamedTuple):
    open: float
    high: float
    low: float
    close: float
    quote_volume: float
    atr: float
    entry_high: float
    entry_low: float
    exit_high: float
    exit_low: float
    sma_fast: float
    sma_slow: float
    quote_volume_30d: float


class KlineFetcher(Protocol):
    """Returns daily bars indexed by UTC open date, possibly with today's open bar.

    Raises ``SymbolUnavailableError`` when the pair does not exist.
    """

    def __call__(
        self, symbol: str, *, start: date | None, limit: int
    ) -> pd.DataFrame: ...


def empty_bars() -> pd.DataFrame:
    """No bars, but with the DatetimeIndex every date comparison expects."""
    return pd.DataFrame(
        {column: pd.Series(dtype=float) for column in BAR_COLUMNS},
        index=pd.DatetimeIndex([]),
    )


def normalize_bars(frame: pd.DataFrame | None) -> pd.DataFrame:
    columns = ["open", "high", "low", "close"]
    if frame is None or frame.empty:
        return empty_bars()
    out = frame.copy()
    if "quote_volume" not in out.columns:
        out["quote_volume"] = np.nan
    index = pd.DatetimeIndex(pd.to_datetime(out.index, utc=True))
    out.index = index.tz_localize(None).normalize()
    out = out[[*columns, "quote_volume"]].astype(float)
    out = out[~out.index.duplicated(keep="last")].sort_index()
    valid = out[columns].notna().all(axis=1) & (out[columns] > 0).all(axis=1)
    return out[valid]


def wilder_atr(
    high: np.ndarray, low: np.ndarray, close: np.ndarray, n: int = ATR_BARS
) -> np.ndarray:
    """Wilder ATR, identical to the research engine (seeded by the first n TRs)."""
    previous = np.r_[np.nan, close[:-1]]
    ranges = np.vstack([high - low, np.abs(high - previous), np.abs(low - previous)])
    true_range = np.nanmax(ranges, axis=0) if len(close) else np.array([])
    if len(true_range):
        true_range[0] = high[0] - low[0]
    atr = np.full(len(true_range), np.nan)
    if len(true_range) < n:
        return atr
    atr[n - 1] = true_range[:n].mean()
    for i in range(n, len(true_range)):
        atr[i] = atr[i - 1] + (true_range[i] - atr[i - 1]) / n
    return atr


def compute_indicators(bars: pd.DataFrame) -> dict[date, BarRow]:
    """Per completed bar: OHLC, ATR, prior-bar channels, SMAs, 30d quote volume."""
    if bars.empty:
        return {}
    high = bars["high"].to_numpy(dtype=float)
    low = bars["low"].to_numpy(dtype=float)
    close = bars["close"].to_numpy(dtype=float)
    atr = wilder_atr(high, low, close, ATR_BARS)
    highs, lows, closes = pd.Series(high), pd.Series(low), pd.Series(close)

    def prior(series: pd.Series, n: int, kind: str) -> np.ndarray:
        rolling = series.rolling(n, min_periods=n)
        values = rolling.max() if kind == "max" else rolling.min()
        return values.shift(1).to_numpy(dtype=float)

    volume = pd.Series(bars["quote_volume"].to_numpy(dtype=float))
    columns = (
        bars["open"].to_numpy(dtype=float),
        high,
        low,
        close,
        volume.to_numpy(dtype=float),
        atr,
        prior(highs, ENTRY_BARS, "max"),
        prior(lows, ENTRY_BARS, "min"),
        prior(highs, EXIT_BARS, "max"),
        prior(lows, EXIT_BARS, "min"),
        closes.rolling(SMA_FAST, min_periods=SMA_FAST).mean().to_numpy(dtype=float),
        closes.rolling(SMA_SLOW, min_periods=SMA_SLOW).mean().to_numpy(dtype=float),
        volume.rolling(PRIORITY_VOLUME_BARS, min_periods=1).sum().to_numpy(dtype=float),
    )
    rows: dict[date, BarRow] = {}
    for position, stamp in enumerate(bars.index):
        rows[stamp.date()] = BarRow(*(float(col[position]) for col in columns))
    return rows


@dataclass
class SymbolData:
    symbol: str
    bars: pd.DataFrame
    rows: dict[date, BarRow]
    in_progress_open: float | None
    latest_bar: date | None = None


class AllowListTransport(BaseAdapter):
    """Transport guard mounted for every URL scheme on the fetcher's session.

    It refuses anything but an HTTPS GET to ``ALLOWED_DATA_HOSTS`` before a
    socket is opened, and counts what it sends and refuses per host, so the run
    log reports observed traffic rather than a claim.
    """

    def __init__(self, delegate: BaseAdapter | None = None) -> None:
        super().__init__()
        self._delegate = delegate if delegate is not None else HTTPAdapter()
        self.sent: Counter[str] = Counter()
        self.refused: Counter[str] = Counter()

    def send(self, request: requests.PreparedRequest, **kwargs: Any) -> Any:
        parsed = urlparse(request.url or "")
        host = parsed.hostname or "<none>"
        if (
            parsed.scheme != "https"
            or host not in ALLOWED_DATA_HOSTS
            or request.method != "GET"
        ):
            self.refused[host] += 1
            raise EgressRefusedError(
                f"refusing {request.method} {parsed.scheme}://{host}: only HTTPS GET "
                f"to {sorted(ALLOWED_DATA_HOSTS)} is allowed"
            )
        self.sent[host] += 1
        return self._delegate.send(request, **kwargs)

    def close(self) -> None:
        self._delegate.close()


class BinanceKlineFetcher:
    """GET-only Binance public spot klines client (no keys, no signing).

    Egress is pinned three ways: the base URL must be an allowed host, every
    send passes ``AllowListTransport``, and redirects are never followed (a 3xx
    fails the fetch). The session ignores the environment (``trust_env`` off),
    so no ~/.netrc credentials, proxy or CA-bundle variables are read.
    ``transport`` replaces only the network adapter behind the guard (tests).
    """

    def __init__(
        self,
        base_url: str = BINANCE_DATA_URL,
        *,
        transport: BaseAdapter | None = None,
        timeout: float = 20.0,
        max_attempts: int = 3,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme != "https" or parsed.hostname not in ALLOWED_DATA_HOSTS:
            raise ValueError(
                f"refusing market-data host {base_url!r}; allowed: "
                f"{sorted(ALLOWED_DATA_HOSTS)}"
            )
        self._url = f"https://{parsed.hostname}{KLINES_PATH}"
        self._guard = AllowListTransport(transport)
        session = requests.Session()
        session.trust_env = False
        session.mount("https://", self._guard)
        session.mount("http://", self._guard)
        session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
        self._session = session
        self._timeout = timeout
        self._max_attempts = max_attempts
        self._sleep = sleep
        self.requests_made = 0

    @property
    def session(self) -> requests.Session:
        return self._session

    @property
    def requests_by_host(self) -> dict[str, int]:
        """Requests the transport guard let through, per host (observed)."""
        return dict(self._guard.sent)

    @property
    def refused_by_host(self) -> dict[str, int]:
        """Requests the transport guard refused, per host (observed)."""
        return dict(self._guard.refused)

    def __call__(self, symbol: str, *, start: date | None, limit: int) -> pd.DataFrame:
        rows: list[list[Any]] = []
        if start is None:
            rows = self._get({"symbol": symbol, "interval": "1d", "limit": limit})
        else:
            cursor = int(
                datetime(start.year, start.month, start.day, tzinfo=UTC).timestamp()
            )
            cursor *= 1000
            for _ in range(MAX_KLINE_PAGES):
                page = self._get(
                    {
                        "symbol": symbol,
                        "interval": "1d",
                        "startTime": cursor,
                        "limit": KLINE_PAGE_LIMIT,
                    }
                )
                rows.extend(page)
                if len(page) < KLINE_PAGE_LIMIT:
                    break
                cursor = int(page[-1][0]) + 86_400_000
        return self.parse(rows)

    @staticmethod
    def parse(rows: list[list[Any]]) -> pd.DataFrame:
        if not rows:
            return empty_bars()
        try:
            index = pd.to_datetime([int(row[0]) for row in rows], unit="ms", utc=True)
            return pd.DataFrame(
                {
                    "open": [float(row[1]) for row in rows],
                    "high": [float(row[2]) for row in rows],
                    "low": [float(row[3]) for row in rows],
                    "close": [float(row[4]) for row in rows],
                    "quote_volume": [float(row[7]) for row in rows],
                },
                index=index,
            )
        except (IndexError, KeyError, TypeError, ValueError) as exc:
            raise DataFetchError(
                f"malformed klines row ({type(exc).__name__}: {exc})"
            ) from exc

    def _get(self, params: dict[str, Any]) -> list[list[Any]]:
        last_error = "no attempt made"
        symbol = params.get("symbol")
        for attempt in range(1, self._max_attempts + 1):
            self.requests_made += 1
            try:
                response = self._session.get(
                    self._url,
                    params=params,
                    timeout=self._timeout,
                    allow_redirects=False,
                )
            except requests.RequestException as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                self._sleep(min(2.0 * attempt, 10.0))
                continue
            final = urlparse(response.url or "")
            if (
                response.history
                or final.scheme != "https"
                or final.hostname not in ALLOWED_DATA_HOSTS
            ):
                raise EgressRefusedError(
                    f"klines response for {symbol} came from "
                    f"{final.scheme}://{final.hostname}; refusing it"
                )
            if 300 <= response.status_code < 400:
                target = urlparse(response.headers.get("Location", "")).hostname
                raise DataFetchError(
                    f"HTTP {response.status_code} redirect for {symbol} (to "
                    f"{target!r}) refused; this client never follows redirects"
                )
            if response.status_code == 200:
                try:
                    payload = response.json()
                except ValueError as exc:
                    raise DataFetchError(f"non-JSON klines body for {params}") from exc
                if not isinstance(payload, list):
                    raise DataFetchError(f"unexpected klines payload for {params}")
                return payload
            if response.status_code == 400:
                try:
                    code = response.json().get("code")
                except ValueError:
                    code = None
                if code == -1121:
                    raise SymbolUnavailableError(params["symbol"])
                raise DataFetchError(f"HTTP 400 for {params['symbol']}: {code}")
            if response.status_code == 418:
                raise DataFetchError("HTTP 418: this IP is banned by Binance; stop")
            if response.status_code == 429 or response.status_code >= 500:
                retry_after = response.headers.get("Retry-After", "")
                wait = float(retry_after) if retry_after.isdigit() else 2.0 * attempt
                last_error = f"HTTP {response.status_code}"
                self._sleep(min(wait, 60.0))
                continue
            raise DataFetchError(f"HTTP {response.status_code} for {symbol}")
        raise DataFetchError(f"klines {symbol} failed: {last_error}")


class MarketData:
    """Per-run cache: one fetch per Binance symbol, completed bars split from today."""

    def __init__(
        self,
        fetcher: KlineFetcher,
        *,
        today: date,
        start: date | None,
        limit: int,
        now: datetime,
    ) -> None:
        self._fetcher = fetcher
        self._today = today
        self._start = start
        self._limit = limit
        self._now = now
        self._cache: dict[str, SymbolData | None] = {}
        self.fetch_calls = 0

    def get(self, symbol: str) -> SymbolData | None:
        if symbol in self._cache:
            return self._cache[symbol]
        self.fetch_calls += 1
        try:
            raw = self._fetcher(symbol, start=self._start, limit=self._limit)
        except SymbolUnavailableError:
            self._cache[symbol] = None
            return None
        bars = normalize_bars(raw)
        today = pd.Timestamp(self._today)
        live = bars[bars.index == today]
        complete = bars[bars.index < today]
        data = SymbolData(
            symbol=symbol,
            bars=complete,
            rows=compute_indicators(complete),
            in_progress_open=float(live["open"].iloc[0]) if len(live) else None,
            latest_bar=bars.index.max().date() if len(bars) else None,
        )
        self._cache[symbol] = data
        return data

    def bars(self, symbol: str) -> pd.DataFrame | None:
        data = self.get(symbol)
        return None if data is None else data.bars

    def is_final(self, symbol: str, day: date) -> bool:
        """The ``day`` bar is final: the same response has a later bar, or the
        close is ``FINALITY_GRACE`` old (so the response cannot predate it)."""
        data = self.get(symbol)
        if data is None or data.latest_bar is None or data.latest_bar > day:
            return True
        closed_at = datetime(day.year, day.month, day.day, tzinfo=UTC) + timedelta(
            days=1
        )
        return self._now >= closed_at + FINALITY_GRACE


# ----------------------------------------------------------------- census / universe


@dataclass(frozen=True)
class CensusEntry:
    coin: str
    binance_symbol: str
    max_leverage: float
    volume_usd: float
    census_rank: int
    mark_px: float | None = None


@dataclass(frozen=True)
class Census:
    entries: tuple[CensusEntry, ...]
    meta: dict[str, Any]


def load_census(path: Path, volume_column: str = "auto") -> Census:
    """Hyperliquid main-dex crypto perps from a local census CSV, by volume."""
    if not path.is_file():
        raise CensusError(f"census CSV not found: {path}")
    raw = path.read_bytes()
    frame = pd.read_csv(io.BytesIO(raw))
    missing = {"dex", "coin", "maxLeverage"} - set(frame.columns)
    if missing:
        raise CensusError(f"census CSV lacks columns {sorted(missing)}")
    if volume_column == "auto":
        column = next((c for c in VOLUME_COLUMN_PREFERENCE if c in frame.columns), None)
    else:
        column = volume_column if volume_column in frame.columns else None
    if column is None:
        raise CensusError(f"census CSV has no volume column ({volume_column})")
    candidates: list[tuple[float, str, float, float | None]] = []
    for record in frame.to_dict("records"):
        coin = str(record.get("coin", "")).strip()
        if str(record.get("dex", "")).strip() != "main" or not coin or ":" in coin:
            continue
        if _truthy(record.get("isDelisted", False)):
            continue
        status = record.get("listing_status")
        if isinstance(status, str) and status.strip() and status.strip() != "listed":
            continue
        try:
            max_leverage = float(record["maxLeverage"])
            volume = float(record[column])
        except (TypeError, ValueError):
            continue
        if not (_finite(max_leverage) and max_leverage > 0):
            continue
        if not (_finite(volume) and volume > 0):
            continue
        try:
            mark_px: float | None = float(record.get("markPx"))
        except (TypeError, ValueError):
            mark_px = None
        candidates.append((volume, coin, max_leverage, mark_px))
    candidates.sort(key=lambda item: (-item[0], item[1]))
    entries = tuple(
        CensusEntry(
            coin=coin,
            binance_symbol=binance_symbol_for(coin),
            max_leverage=max_leverage,
            volume_usd=volume,
            census_rank=rank,
            mark_px=mark_px if _finite(mark_px) and mark_px > 0 else None,
        )
        for rank, (volume, coin, max_leverage, mark_px) in enumerate(
            candidates, start=1
        )
    )
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    meta = {
        "path": str(path),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "mtime_utc": mtime.isoformat(timespec="seconds"),
        "rows": int(len(frame)),
        "eligible_main_dex_rows": len(entries),
        "volume_column": column,
        "volume_basis": (
            "24h_snapshot" if column == SNAPSHOT_VOLUME_COLUMN else "trailing_30d"
        ),
    }
    return Census(entries=entries, meta=meta)


def _census_price_ratio(
    entry: CensusEntry, bars: pd.DataFrame, census_day: pd.Timestamp
) -> float | None:
    """Binance close near the census capture day over the census mark (per unit)."""
    if entry.mark_px is None or pd.isna(census_day):
        return None
    near = bars[bars.index <= census_day]
    if near.empty or (census_day - near.index[-1]).days > PRICE_CHECK_MAX_AGE_DAYS:
        return None
    per_unit = entry.mark_px / (1000.0 if _KILO_PREFIX.fullmatch(entry.coin) else 1.0)
    return float(near["close"].iloc[-1]) / per_unit


def freeze_universe(
    month_start: date,
    census: Census,
    history: Callable[[str], pd.DataFrame | None],
    config: ShadowConfig,
) -> dict[str, Any]:
    """Walk the census by volume and keep the first N coins with enough Binance history.

    History is point-in-time: only completed bars before ``month_start`` count, and
    the pair must have a bar for the day before (not stale or delisted). A pair
    whose close near the census capture date is not within 2x of the census
    ``markPx`` is a different asset behind the same ticker and is rejected.
    """
    cutoff = pd.Timestamp(month_start)
    census_day = pd.Timestamp(str(census.meta.get("mtime_utc", ""))[:10] or None)
    expected_last = cutoff - pd.Timedelta(days=1)
    members: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in census.entries:
        if len(members) >= config.universe_size:
            break
        base = {"coin": entry.coin, "binance_symbol": entry.binance_symbol}
        if entry.binance_symbol in seen:
            rejected.append({**base, "reason": "duplicate_binance_symbol"})
            continue
        bars = history(entry.binance_symbol)
        if bars is None:
            rejected.append({**base, "reason": "no_binance_usdt_spot_pair"})
            continue
        before = bars[bars.index < cutoff]
        if before.empty or before.index[-1] != expected_last:
            last = before.index[-1].date().isoformat() if len(before) else None
            rejected.append({**base, "reason": "stale_binance_pair", "last_bar": last})
            continue
        if len(before) < config.min_history_bars:
            rejected.append(
                {**base, "reason": "insufficient_history", "history_bars": len(before)}
            )
            continue
        ratio = _census_price_ratio(entry, bars, census_day)
        if ratio is not None and not (
            1.0 / MAX_CENSUS_PRICE_RATIO <= ratio <= MAX_CENSUS_PRICE_RATIO
        ):
            rejected.append({**base, "reason": "price_mismatch", "price_ratio": ratio})
            continue
        seen.add(entry.binance_symbol)
        members.append(
            {
                **base,
                "census_rank": entry.census_rank,
                "census_volume_usd": entry.volume_usd,
                "max_leverage": entry.max_leverage,
                "mmr": 1.0 / (2.0 * entry.max_leverage),
                "history_bars_seen": int(len(before)),
                "price_ratio_vs_census": ratio,
            }
        )
    return {
        "month": _month_key(month_start),
        "effective_from": month_start.isoformat(),
        "history_cutoff": expected_last.date().isoformat(),
        "rule": (
            f"top {config.universe_size} HL main-dex crypto perps by census volume "
            f"with a Binance USDT spot pair and >= {config.min_history_bars} "
            "completed daily bars before the month starts, priced within "
            f"{MAX_CENSUS_PRICE_RATIO:g}x of the census markPx"
        ),
        "census": census.meta,
        # Positive: census captured before the month started. Negative: after it
        # (a backfill freeze), so the volume ranking is not point-in-time.
        "census_age_days_at_month_start": (
            None if pd.isna(census_day) else int((cutoff - census_day).days)
        ),
        "size": len(members),
        "short_universe": len(members) < config.universe_size,
        "members": members,
        "rejected": rejected,
        "priority_rule": PRIORITY_RULE,
        "execution_authority": EXECUTION_AUTHORITY,
    }


# ----------------------------------------------------------------- engine state


@dataclass
class VirtualTrade:
    trade_id: str
    coin: str
    binance_symbol: str
    direction: int
    signal_date: str
    entry_date: str
    entry_px: float
    stop_px: float
    stop_fraction: float
    atr: float
    leverage: int
    mmr: float
    max_leverage: float
    liq_px: float
    liq_distance: float
    liq_buffer_ok: bool
    taken: bool
    skip_reason: str | None
    risk_usd: float
    want_notional_usd: float
    notional_usd: float
    margin_usd: float
    priority_rank: int
    priority_quote_volume_30d: float | None
    census_rank: int | None


@dataclass
class PendingOrder:
    coin: str
    binance_symbol: str
    signal_date: str
    exit_direction: int = 0
    entry_direction: int = 0
    atr: float | None = None
    max_leverage: float | None = None
    census_rank: int | None = None
    priority_quote_volume_30d: float | None = None


@dataclass
class EngineState:
    last_bar_date: str | None = None
    trades: dict[str, VirtualTrade] = field(default_factory=dict)
    pending: dict[str, PendingOrder] = field(default_factory=dict)
    realized_net_usd: float = 0.0
    closed_trades: int = 0
    closed_taken_trades: int = 0
    btc_beta_state: str | None = None

    def to_record(self, config: ShadowConfig) -> dict[str, Any]:
        return {
            "last_bar_date": self.last_bar_date,
            "trades": [asdict(self.trades[c]) for c in sorted(self.trades)],
            "pending": [asdict(self.pending[c]) for c in sorted(self.pending)],
            "realized_net_usd": self.realized_net_usd,
            "closed_trades": self.closed_trades,
            "closed_taken_trades": self.closed_taken_trades,
            "btc_beta_state": self.btc_beta_state,
            "config": config.as_record(),
            "config_fingerprint": config.fingerprint(),
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> EngineState:
        trade_fields = {f.name for f in fields(VirtualTrade)}
        pending_fields = {f.name for f in fields(PendingOrder)}
        try:
            trades = [
                VirtualTrade(**{k: v for k, v in item.items() if k in trade_fields})
                for item in record["trades"]
            ]
            pending = [
                PendingOrder(**{k: v for k, v in item.items() if k in pending_fields})
                for item in record["pending"]
            ]
            return cls(
                last_bar_date=record["last_bar_date"],
                trades={t.coin: t for t in trades},
                pending={p.coin: p for p in pending},
                realized_net_usd=float(record["realized_net_usd"]),
                closed_trades=int(record["closed_trades"]),
                closed_taken_trades=int(record["closed_taken_trades"]),
                btc_beta_state=record.get("btc_beta_state"),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise LedgerError(f"daily_mark state is unreadable: {exc}") from exc


def make_event(kind: str, bar_date: date | str, key: str, payload: Mapping) -> dict:
    if kind not in EVENT_TYPES:
        raise EngineInvariantError(f"unknown event type {kind}")
    day = bar_date if isinstance(bar_date, str) else bar_date.isoformat()
    event = {
        "schema": SCHEMA,
        "event": kind,
        "event_id": _sha256(f"{SCHEMA}|{kind}|{day}|{key}")[:24],
        "bar_date": day,
        **_jsonable(payload),
    }
    event["content_digest"] = content_digest(event)
    return event


def content_digest(event: Mapping[str, Any]) -> str:
    body = {k: v for k, v in event.items() if k not in _UNHASHED_FIELDS}
    return _sha256(_canonical(body))[:24]


def _side(direction: int) -> tuple[str, str]:
    return ("long", "trend") if direction > 0 else ("short", "hedge")


def _priority_key(order: PendingOrder) -> tuple[float, int, str]:
    volume = order.priority_quote_volume_30d
    volume = volume if _finite(volume) else -1.0
    rank = order.census_rank if order.census_rank is not None else 1_000_000
    return (-float(volume), int(rank), order.coin)


class ShadowEngine:
    """Deterministic per-bar state machine; mutates ``state`` and returns events."""

    def __init__(self, config: ShadowConfig, state: EngineState) -> None:
        self.config = config
        self.state = state

    # -------------------------------------------------------- at the open
    def open_step(self, day: date, opens: Mapping[str, float]) -> list[dict]:
        state = self.state
        events: list[dict] = []
        for coin in sorted(state.pending):
            order = state.pending[coin]
            trade = state.trades.get(coin)
            if (
                order.exit_direction
                and trade
                and trade.direction == order.exit_direction
            ):
                events.append(
                    self._close(
                        trade, day, opens[coin], "channel_exit", "hypothetical_exit"
                    )
                )
        for coin in sorted(state.trades):
            trade = state.trades[coin]
            price = float(opens[coin])
            if trade.direction * (price - trade.liq_px) <= 0:
                reason = "liquidation_gap"
            elif trade.direction * (price - trade.stop_px) <= 0:
                reason = "gap_stop"
            else:
                continue
            events.append(
                self._close(
                    trade,
                    day,
                    price,
                    reason,
                    "hypothetical_stop_hit",
                    bar={"open": price},
                )
            )
        entries = sorted(
            (order for order in state.pending.values() if order.entry_direction),
            key=_priority_key,
        )
        for rank, order in enumerate(entries, start=1):
            if order.coin in state.trades:
                raise EngineInvariantError(f"{order.coin}: entry while a trade is open")
            events.append(self._enter(order, day, float(opens[order.coin]), rank))
        state.pending = {}
        return events

    # -------------------------------------------------------- the completed bar
    def bar_step(
        self,
        day: date,
        rows: Mapping[str, BarRow],
        members: Mapping[str, Mapping[str, Any]],
        universe_month: str,
    ) -> list[dict]:
        state = self.state
        events: list[dict] = []
        for coin in sorted(state.trades):
            trade = state.trades[coin]
            row = rows[coin]
            d = trade.direction
            if (d > 0 and row.low <= trade.stop_px) or (
                d < 0 and row.high >= trade.stop_px
            ):
                wick = (d > 0 and row.low <= trade.liq_px) or (
                    d < 0 and row.high >= trade.liq_px
                )
                events.append(
                    self._close(
                        trade,
                        day,
                        trade.stop_px,
                        "stop_intrabar",
                        "hypothetical_stop_hit",
                        bar={"open": row.open, "high": row.high, "low": row.low},
                        wick_through_liq=wick,
                    )
                )
        pending: dict[str, PendingOrder] = {}
        next_open = (day + timedelta(days=1)).isoformat()
        for coin in sorted(rows):
            row = rows[coin]
            channels = (
                row.atr,
                row.entry_high,
                row.entry_low,
                row.exit_high,
                row.exit_low,
            )
            if not all(_finite(value) for value in channels):
                continue
            trade = state.trades.get(coin)
            member = members.get(coin)
            long_signal = row.close > row.entry_high
            short_signal = row.close < row.entry_low
            if trade is not None:
                d = trade.direction
                exit_level = row.exit_low if d > 0 else row.exit_high
                if not (row.close < exit_level if d > 0 else row.close > exit_level):
                    continue
                reverse = short_signal if d > 0 else long_signal
                order = PendingOrder(
                    coin=coin,
                    binance_symbol=trade.binance_symbol,
                    signal_date=day.isoformat(),
                    exit_direction=d,
                )
                side, label = _side(d)
                events.append(
                    make_event(
                        "signal",
                        day,
                        f"{coin}:exit_{side}",
                        {
                            "coin": coin,
                            "binance_symbol": trade.binance_symbol,
                            "kind": f"exit_{side}",
                            "side": side,
                            "label": label,
                            "trade_id": trade.trade_id,
                            "taken": trade.taken,
                            "close": row.close,
                            "channel_level": exit_level,
                            "channel_bars": EXIT_BARS,
                            "fill_at_open_of": next_open,
                            "reversal_blocked": (
                                "not_in_universe"
                                if reverse and member is None
                                else None
                            ),
                        },
                    )
                )
                if reverse and member is not None:
                    self._entry_order(order, -d, row, member)
                    events.append(self._entry_signal(day, order, row, universe_month))
                pending[coin] = order
            elif member is not None and (long_signal or short_signal):
                order = PendingOrder(
                    coin=coin,
                    binance_symbol=str(member["binance_symbol"]),
                    signal_date=day.isoformat(),
                )
                self._entry_order(order, 1 if long_signal else -1, row, member)
                events.append(self._entry_signal(day, order, row, universe_month))
                pending[coin] = order
        state.pending = pending
        return events

    def mark(
        self,
        day: date,
        rows: Mapping[str, BarRow],
        *,
        missing: list[str],
        universe_month: str,
        cold_start: bool,
    ) -> dict:
        cfg = self.config
        state = self.state
        state.last_bar_date = day.isoformat()
        fee = cfg.fee_bps * 1e-4
        taken: list[dict] = []
        untaken: list[dict] = []
        gross = margin = unrealized = funding_total = 0.0
        longs = shorts = 0
        for coin in sorted(state.trades):
            trade = state.trades[coin]
            close = rows[coin].close
            held = (day - date.fromisoformat(trade.entry_date)).days + 1
            ratio = close / trade.entry_px
            d = trade.direction
            gross_ret = d * (ratio - 1.0)
            fee_ret = fee * (1.0 + ratio)
            funding_ret = d * cfg.funding_apr / 365.0 * held
            net_ret = gross_ret - funding_ret - fee_ret
            side, label = _side(d)
            record = {
                "trade_id": trade.trade_id,
                "coin": coin,
                "side": side,
                "label": label,
                "entry_date": trade.entry_date,
                "entry_px": trade.entry_px,
                "close": close,
                "stop_px": trade.stop_px,
                "days_held": held,
                "net_r_unrealized": net_ret / trade.stop_fraction,
            }
            if not trade.taken:
                untaken.append(record)
                continue
            notional = trade.notional_usd
            record.update(
                {
                    "liq_px": trade.liq_px,
                    "leverage": trade.leverage,
                    "notional_usd": notional,
                    "margin_usd": trade.margin_usd,
                    "risk_usd": trade.risk_usd,
                    "gross_unrealized_usd": gross_ret * notional,
                    "fees_est_usd": fee_ret * notional,
                    "funding_est_usd": funding_ret * notional,
                    "net_unrealized_usd": net_ret * notional,
                }
            )
            taken.append(record)
            gross += notional
            margin += trade.margin_usd
            unrealized += net_ret * notional
            funding_total += funding_ret * notional
            longs += d > 0
            shorts += d < 0
        payload = {
            "universe_month": universe_month,
            "book_equity_notional": cfg.book_equity,
            "funding_apr": cfg.funding_apr,
            "fee_bps": cfg.fee_bps,
            "cold_start": cold_start,
            "open_positions": taken,
            "untaken_virtual_trades": untaken,
            "totals": {
                "open_taken": len(taken),
                "open_long": longs,
                "open_short_hedge": shorts,
                "slots_free": cfg.max_slots - len(taken),
                "open_untaken_virtual": len(untaken),
                "gross_notional_usd": gross,
                "gross_to_equity": gross / cfg.book_equity,
                "margin_usd": margin,
                "net_unrealized_usd": unrealized,
                "funding_est_open_usd": funding_total,
                "realized_net_usd_cum": state.realized_net_usd,
                "hypothetical_equity_usd": cfg.book_equity
                + state.realized_net_usd
                + unrealized,
                "closed_trades": state.closed_trades,
                "closed_taken_trades": state.closed_taken_trades,
            },
            "missing_bars": sorted(missing),
            "data_source": "binance_spot_usdt_1d",
            "execution_authority": EXECUTION_AUTHORITY,
            "state": state.to_record(cfg),
        }
        return make_event("daily_mark", day, "mark", payload)

    # -------------------------------------------------------- internals
    @staticmethod
    def _entry_order(
        order: PendingOrder, direction: int, row: BarRow, member: Mapping[str, Any]
    ) -> None:
        order.entry_direction = direction
        order.atr = row.atr
        order.max_leverage = float(member["max_leverage"])
        order.census_rank = int(member["census_rank"])
        order.priority_quote_volume_30d = row.quote_volume_30d

    @staticmethod
    def _entry_signal(
        day: date, order: PendingOrder, row: BarRow, universe_month: str
    ) -> dict:
        side, label = _side(order.entry_direction)
        level = row.entry_high if order.entry_direction > 0 else row.entry_low
        return make_event(
            "signal",
            day,
            f"{order.coin}:entry_{side}",
            {
                "coin": order.coin,
                "binance_symbol": order.binance_symbol,
                "kind": f"entry_{side}",
                "side": side,
                "label": label,
                "reversal": bool(order.exit_direction),
                "close": row.close,
                "channel_level": level,
                "channel_bars": ENTRY_BARS,
                "atr_signal": row.atr,
                "priority_quote_volume_30d": order.priority_quote_volume_30d,
                "census_rank": order.census_rank,
                "universe_month": universe_month,
                "fill_at_open_of": (day + timedelta(days=1)).isoformat(),
            },
        )

    def _allocate(self, want: float, leverage: int) -> tuple[bool, float, str | None]:
        cfg = self.config
        open_taken = [t for t in self.state.trades.values() if t.taken]
        if len(open_taken) >= cfg.max_slots:
            return False, 0.0, "slots_full"
        gross_used = sum(t.notional_usd for t in open_taken)
        margin_used = sum(t.margin_usd for t in open_taken)
        room = min(
            want,
            cfg.gross_cap * cfg.book_equity - gross_used,
            (cfg.book_equity - margin_used) * leverage,
        )
        if room < cfg.min_fill_fraction * want:
            return False, 0.0, "gross_cap"
        return True, room, None

    def _enter(self, order: PendingOrder, day: date, fill: float, rank: int) -> dict:
        cfg = self.config
        d = order.entry_direction
        side, label = _side(d)
        trade_id = f"{order.coin}:{side}:{day.isoformat()}"
        stop = fill - d * STOP_ATR_MULT * float(order.atr or math.nan)
        stop_fraction = abs(fill - stop) / fill if fill > 0 else math.nan
        base = {
            "trade_id": trade_id,
            "coin": order.coin,
            "binance_symbol": order.binance_symbol,
            "side": side,
            "label": label,
            "signal_date": order.signal_date,
            "entry_date": day.isoformat(),
            "entry_px": fill,
            "fill_basis": "binance_1d_open",
            "atr_signal": order.atr,
            "priority_rank": rank,
            "priority_quote_volume_30d": order.priority_quote_volume_30d,
            "census_rank": order.census_rank,
        }
        if not (_finite(stop_fraction) and stop_fraction > 0):
            return make_event(
                "hypothetical_entry",
                day,
                trade_id,
                {**base, "taken": False, "skip_reason": "invalid_stop"},
            )
        leverage, mmr, liq_distance, buffer_ok = leverage_for(
            stop_fraction, float(order.max_leverage or 1.0), d
        )
        risk = cfg.book_equity * cfg.risk_fraction
        want = risk / stop_fraction
        taken, notional, reason = self._allocate(want, leverage)
        trade = VirtualTrade(
            trade_id=trade_id,
            coin=order.coin,
            binance_symbol=order.binance_symbol,
            direction=d,
            signal_date=order.signal_date,
            entry_date=day.isoformat(),
            entry_px=fill,
            stop_px=stop,
            stop_fraction=stop_fraction,
            atr=float(order.atr or math.nan),
            leverage=leverage,
            mmr=mmr,
            max_leverage=float(order.max_leverage or 1.0),
            liq_px=fill * (1.0 - d * liq_distance),
            liq_distance=liq_distance,
            liq_buffer_ok=buffer_ok,
            taken=taken,
            skip_reason=reason,
            risk_usd=risk if taken else 0.0,
            want_notional_usd=want,
            notional_usd=notional,
            margin_usd=notional / leverage if taken else 0.0,
            priority_rank=rank,
            priority_quote_volume_30d=order.priority_quote_volume_30d,
            census_rank=order.census_rank,
        )
        self.state.trades[order.coin] = trade
        return make_event(
            "hypothetical_entry",
            day,
            trade_id,
            {
                **base,
                "taken": taken,
                "skip_reason": reason,
                "stop_px": stop,
                "stop_fraction": stop_fraction,
                "leverage": leverage,
                "max_leverage": trade.max_leverage,
                "mmr": mmr,
                "liq_px": trade.liq_px,
                "liq_distance": liq_distance,
                "liq_buffer_ok": buffer_ok,
                "risk_usd_planned": risk,
                "want_notional_usd": want,
                "notional_usd": notional,
                "scaled_by_gross_cap": bool(taken and notional < want),
                "margin_usd": trade.margin_usd,
                "slots_used_after": sum(
                    1 for t in self.state.trades.values() if t.taken
                ),
            },
        )

    def _close(
        self,
        trade: VirtualTrade,
        day: date,
        price: float,
        reason: str,
        kind: str,
        *,
        bar: Mapping[str, float] | None = None,
        wick_through_liq: bool = False,
    ) -> dict:
        cfg = self.config
        state = self.state
        d = trade.direction
        held = (day - date.fromisoformat(trade.entry_date)).days
        ratio = price / trade.entry_px
        fee_ret = cfg.fee_bps * 1e-4 * (1.0 + ratio)
        gross_ret = d * (ratio - 1.0)
        funding_ret = d * cfg.funding_apr / 365.0 * held
        if reason == "liquidation_gap":
            net_ret = -1.0 / trade.leverage - fee_ret
        else:
            net_ret = gross_ret - funding_ret - fee_ret
        notional = trade.notional_usd if trade.taken else 0.0
        side, label = _side(d)
        payload = {
            "trade_id": trade.trade_id,
            "coin": trade.coin,
            "binance_symbol": trade.binance_symbol,
            "side": side,
            "label": label,
            "taken": trade.taken,
            "exit_reason": reason,
            "entry_date": trade.entry_date,
            "entry_px": trade.entry_px,
            "exit_px": price,
            "stop_px": trade.stop_px,
            "liq_px": trade.liq_px,
            "wick_through_liq": wick_through_liq,
            # Research-engine order: a pending channel exit fills at the open
            # before the liquidation check, so an open beyond liq_px is booked
            # as a channel exit and its loss is not capped at the margin. Flag it.
            "exit_beyond_liq_px": bool(d * (price - trade.liq_px) <= 0),
            "bar": dict(bar) if bar else None,
            "days_held": held,
            "gross_return": gross_ret,
            "fee_return": fee_ret,
            "funding_est_return": funding_ret,
            "net_return": net_ret,
            "net_r": net_ret / trade.stop_fraction,
            "notional_usd": notional if trade.taken else None,
            "gross_pnl_usd": gross_ret * notional if trade.taken else None,
            "fees_usd": fee_ret * notional if trade.taken else None,
            "funding_est_usd": funding_ret * notional if trade.taken else None,
            "net_pnl_usd": net_ret * notional if trade.taken else None,
        }
        if trade.taken:
            state.realized_net_usd += net_ret * notional
            state.closed_taken_trades += 1
        state.closed_trades += 1
        del state.trades[trade.coin]
        return make_event(kind, day, trade.trade_id, payload)


def regime_tag(
    day: date, rows: Mapping[str, BarRow | None], previous: str | None
) -> tuple[dict, str | None]:
    """BTC SMA200 beta-switch state plus SMA50/SMA200 context for BTC, ETH, SOL."""
    context: dict[str, Any] = {}
    for coin in REGIME_COINS:
        row = rows.get(coin)
        if row is None:
            context[coin] = None
            continue

        def above(level: float, row: BarRow = row) -> bool | None:
            return None if not _finite(level) else bool(row.close > level)

        context[coin] = {
            "close": row.close,
            "sma50": row.sma_fast,
            "sma200": row.sma_slow,
            "above_sma50": above(row.sma_fast),
            "above_sma200": above(row.sma_slow),
            "sma50_above_sma200": (
                bool(row.sma_fast > row.sma_slow)
                if _finite(row.sma_fast) and _finite(row.sma_slow)
                else None
            ),
        }
    btc = context.get("BTC")
    above_200 = btc["above_sma200"] if btc else None
    current = None if above_200 is None else ("long" if above_200 else "cash")
    payload = {
        "btc_beta_switch": {
            "rule": "BTC daily close > SMA200: long 1x; otherwise cash",
            "state": current,
            "previous_state": previous,
            "switched": (
                None if current is None or previous is None else current != previous
            ),
            "close": btc["close"] if btc else None,
            "sma200": btc["sma200"] if btc else None,
        },
        "context": context,
        "note": "context tags only; no D1 signal depends on them",
    }
    return make_event("regime_tag", day, "regime", payload), (current or previous)


# ----------------------------------------------------------------- ledger


def _chain_step(chain: str, event: Mapping[str, Any]) -> str:
    return _sha256(f"{chain}|{event['content_digest']}")[:32]


def ledger_chain(events: Iterable[Mapping[str, Any]]) -> str:
    """Hash chain over the content digests of ``events`` in ledger order."""
    chain = CHAIN_GENESIS
    for event in events:
        chain = _chain_step(chain, event)
    return chain


def load_ledger(path: Path) -> list[dict]:
    """Read and verify the ledger: line digests, the daily_mark chain, no torn tail."""
    if not path.exists():
        return []
    raw = path.read_bytes()
    if raw and not raw.endswith(b"\n"):
        keep = raw.rfind(b"\n") + 1
        raise LedgerError(
            f"{path}: the last line is incomplete (a crash mid-append?). Keep a "
            f"copy, truncate the file to {keep} bytes (the end of the last complete "
            "line) and re-run; the next run re-derives the missing events"
        )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise LedgerError(f"{path} is not UTF-8 ({exc})") from exc
    events: list[dict] = []
    chain = CHAIN_GENESIS
    for number, line in enumerate(text.split("\n"), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise LedgerError(f"{path}:{number} is not valid JSON ({exc})") from exc
        if not isinstance(event, dict) or event.get("schema") != SCHEMA:
            raise LedgerError(f"{path}:{number} is not a {SCHEMA} event")
        if event.get("content_digest") != content_digest(event):
            raise LedgerError(
                f"{path}:{number} content does not match its digest "
                "(edited or corrupted); refusing to continue"
            )
        if event["event"] == "daily_mark" and event.get("ledger_chain_before") != chain:
            raise LedgerError(
                f"{path}:{number} breaks the ledger chain: a line before it was "
                "deleted, inserted or reordered; refusing to continue"
            )
        chain = _chain_step(chain, event)
        events.append(event)
    return events


def append_events(path: Path, events: list[dict]) -> None:
    if not events:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(_canonical(event) + "\n" for event in events)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())


def _dedupe(existing: Iterable[dict], generated: list[dict]) -> list[dict]:
    """Drop events already in the ledger; a same-id event with other content is fatal."""
    known = {event["event_id"]: content_digest(event) for event in existing}
    fresh: list[dict] = []
    for event in generated:
        stored = known.get(event["event_id"])
        if stored is None:
            known[event["event_id"]] = event["content_digest"]
            fresh.append(event)
        elif stored != event["content_digest"]:
            raise LedgerError(
                f"ledger conflict: {event['event']} {event['bar_date']} "
                f"({event['event_id']}) was recorded with different content"
            )
    return fresh


# ----------------------------------------------------------------- runner


@dataclass
class RunReport:
    mode: str
    effective_today: str
    first_bar: str | None = None
    last_bar: str | None = None
    appended: list[dict] = field(default_factory=list)
    fetch_calls: int = 0
    error: str | None = None
    notes: list[str] = field(default_factory=list)
    btc_beta_state: str | None = None
    # Taken positions in the book after everything this run recorded, and the
    # point that book is at: "<day> close", or "<today> open" when today's open
    # step (entries and gap exits at the open) was recorded too.
    open_taken: int | None = None
    book_through: str | None = None
    deferred: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None

    def summary(self) -> str:
        counts = Counter(event["event"] for event in self.appended)
        detail = ",".join(f"{k}={counts[k]}" for k in sorted(counts)) or "none"
        bars = (
            f"{self.first_bar}..{self.last_bar}"
            if self.first_bar
            else "none (up to date)"
        )
        text = (
            f"d1_shadow mode={self.mode} today={self.effective_today} bars={bars} "
            f"appended={len(self.appended)} [{detail}] open_taken={self.open_taken} "
            f"book_through={(self.book_through or 'none').replace(' ', '_')} "
            f"btc_beta={self.btc_beta_state} fetches={self.fetch_calls}"
        )
        if self.deferred:
            text += f" deferred={self.deferred}"
        if self.error:
            text += f" FAIL-CLOSED: {self.error}"
        return text


def run_shadow(
    *,
    ledger_path: Path,
    census_path: Path,
    config: ShadowConfig,
    fetcher: KlineFetcher,
    now: datetime,
    backfill_from: date | None = None,
    dry_run: bool = False,
    volume_column: str = "auto",
    max_census_age_days: int = MAX_CENSUS_AGE_DAYS,
) -> RunReport:
    """Process every new completed UTC day, then today's open; append new events."""
    config.validate()
    if now.tzinfo is None:
        raise ShadowError("now must be timezone-aware")
    now = now.astimezone(UTC)
    effective = now - SETTLE_DELAY
    today = effective.date()
    last_complete = today - timedelta(days=1)
    existing = load_ledger(ledger_path)
    marks = [event for event in existing if event["event"] == "daily_mark"]
    universes: dict[str, dict] = {
        event["month"]: event
        for event in existing
        if event["event"] == "universe_frozen"
    }
    mode = "backfill" if backfill_from else "daily"
    report = RunReport(mode=mode, effective_today=today.isoformat())
    cold_start = False
    if backfill_from is not None:
        if existing:
            raise LedgerError(
                f"--backfill-from needs an empty ledger; {ledger_path} has "
                f"{len(existing)} events (use a new --ledger path)"
            )
        if backfill_from > last_complete:
            raise ShadowError(f"backfill start {backfill_from} is not a completed day")
        state, start, cold_start = EngineState(), backfill_from, True
    else:
        if marks:
            record = marks[-1].get("state") or {}
            if record.get("config_fingerprint") != config.fingerprint():
                raise LedgerError(
                    "configuration differs from the ledger's (fingerprint "
                    f"{record.get('config_fingerprint')} vs {config.fingerprint()}); "
                    "use a new --ledger path for a new configuration"
                )
            state = EngineState.from_record(record)
            start = date.fromisoformat(state.last_bar_date) + timedelta(days=1)
            if start > today:
                raise LedgerError(
                    f"ledger is ahead of the clock (last bar {state.last_bar_date})"
                )
        elif existing:
            raise LedgerError("ledger has events but no daily_mark; refusing to guess")
        else:
            state, start, cold_start = EngineState(), last_complete, True
            report.notes.append(
                "cold start: flat book from the last completed bar "
                "(use --backfill-from to seed open positions)"
            )

    # Always fetch forward from a fixed start (never "the latest N bars"), so the
    # window depends on the ledger and the clock argument, not the wall clock.
    market = MarketData(
        fetcher,
        today=today,
        start=start - timedelta(days=WARMUP_BARS),
        limit=KLINE_PAGE_LIMIT,
        now=now,
    )
    engine = ShadowEngine(config, state)
    census_cache: list[Census] = []

    def census() -> Census:
        if not census_cache:
            census_cache.append(load_census(census_path, volume_column))
        return census_cache[0]

    def universe_for(day: date, sink: list[dict]) -> dict:
        key = _month_key(day)
        if key not in universes:
            month_start = day.replace(day=1)
            payload = freeze_universe(month_start, census(), market.bars, config)
            age = payload["census_age_days_at_month_start"]
            if mode == "daily" and (age is None or age > max_census_age_days):
                raise CensusError(
                    f"census {census_path} is {age} days old at the {key} universe "
                    f"freeze (limit {max_census_age_days}); refresh it and re-run"
                )
            # Point-in-time only when the census was captured before the month
            # started (age >= 1 day); a backfill uses today's census.
            payload["point_in_time"] = mode == "daily" and age is not None and age > 0
            payload["max_census_age_days"] = max_census_age_days
            payload["frozen_by"] = mode
            event = make_event("universe_frozen", month_start, key, payload)
            universes[key] = event
            sink.append(event)
        return universes[key]

    def symbol_map() -> dict[str, str]:
        mapping = {coin: t.binance_symbol for coin, t in state.trades.items()}
        mapping.update({coin: p.binance_symbol for coin, p in state.pending.items()})
        return mapping

    committed: list[dict] = []
    for day in _days(start, last_complete):
        day_events: list[dict] = []
        try:
            universe = universe_for(day, day_events)
            members = {m["coin"]: m for m in universe["members"]}
            required = symbol_map()
            working = {coin: str(m["binance_symbol"]) for coin, m in members.items()}
            working.update(required)
            rows: dict[str, BarRow] = {}
            missing: list[str] = []
            for coin, symbol in sorted(working.items()):
                data = market.get(symbol)
                row = data.rows.get(day) if data else None
                if row is None:
                    if coin in required:
                        raise DataGapError(
                            f"{coin} ({symbol}) is held or pending but has no "
                            f"completed {day} bar"
                        )
                    missing.append(coin)
                    continue
                rows[coin] = row
            regime_rows: dict[str, BarRow | None] = {}
            for coin in REGIME_COINS:
                data = market.get(binance_symbol_for(coin))
                regime_rows[coin] = data.rows.get(day) if data else None
            used = {working[coin] for coin in rows}
            used |= {binance_symbol_for(c) for c, r in regime_rows.items() if r}
            unsettled = sorted(s for s in used if not market.is_final(s, day))
            if unsettled:
                report.deferred = day.isoformat()
                report.notes.append(
                    f"deferred {day}: no later bar yet for {', '.join(unsettled)} "
                    "(the response may predate the close); the next run retries"
                )
                break
            # Every fetch for the day is done; the state mutates only from here on.
            day_events += engine.open_step(day, {c: rows[c].open for c in required})
            day_events += engine.bar_step(day, rows, members, universe["month"])
            tag, state.btc_beta_state = regime_tag(
                day, regime_rows, state.btc_beta_state
            )
            day_events.append(tag)
            day_events.append(
                engine.mark(
                    day,
                    rows,
                    missing=missing,
                    universe_month=universe["month"],
                    cold_start=cold_start,
                )
            )
        except (DataGapError, DataFetchError, CensusError) as exc:
            report.error = str(exc)
            break
        cold_start = False
        committed += day_events
        report.first_bar = report.first_bar or day.isoformat()
        report.last_bar = day.isoformat()

    book = state
    report.book_through = (
        f"{state.last_bar_date} close" if state.last_bar_date else None
    )
    if report.error is None and state.last_bar_date == last_complete.isoformat():
        required = symbol_map()
        opens: dict[str, float] = {}
        try:
            for coin, symbol in sorted(required.items()):
                data = market.get(symbol)
                if data is None or data.in_progress_open is None:
                    report.notes.append(f"{today} open not yet available for {coin}")
                    break
                opens[coin] = data.in_progress_open
        except DataFetchError as exc:
            report.notes.append(f"today's open step deferred: {exc}")
        if len(opens) == len(required):
            provisional = ShadowEngine(config, copy.deepcopy(state))
            committed += provisional.open_step(today, opens)
            book = provisional.state
            report.book_through = f"{today.isoformat()} open"

    fresh = _dedupe(existing, committed)
    chain = ledger_chain(existing)
    stamp = datetime.now(UTC).isoformat(timespec="seconds")
    for event in fresh:
        if event["event"] == "daily_mark":
            event["ledger_chain_before"] = chain
            event["content_digest"] = content_digest(event)
        chain = _chain_step(chain, event)
        event["recorded_at"] = stamp
        event["mode"] = mode
    if not dry_run:
        append_events(ledger_path, fresh)
    report.appended = fresh
    report.fetch_calls = market.fetch_calls
    report.btc_beta_state = state.btc_beta_state
    report.open_taken = sum(1 for trade in book.trades.values() if trade.taken)
    return report


# ----------------------------------------------------------------- CLI


def _parse_now(text: str | None) -> datetime:
    real = datetime.now(UTC)
    if text is None:
        return real
    value = datetime.fromisoformat(text)
    value = value if value.tzinfo else value.replace(tzinfo=UTC)
    if value > real + timedelta(minutes=1):
        raise ShadowError("--now-utc cannot be in the future")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Observe-only D1 Donchian 20/10 swing shadow (Sleeve S1). Reads "
            "Binance public 1d klines and a local HL census; never calls "
            "Hyperliquid; builds no execution client."
        )
    )
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--census", type=Path, default=DEFAULT_CENSUS)
    parser.add_argument(
        "--volume-column",
        default="auto",
        help="census volume column (auto prefers a trailing-30d column, else dayNtlVlm)",
    )
    parser.add_argument("--book-equity", type=float, default=ShadowConfig.book_equity)
    parser.add_argument(
        "--funding-apr",
        type=float,
        default=ShadowConfig.funding_apr,
        help="hypothetical funding APR as a fraction (longs pay when positive)",
    )
    parser.add_argument("--fee-bps", type=float, default=ShadowConfig.fee_bps)
    parser.add_argument(
        "--backfill-from",
        type=date.fromisoformat,
        default=None,
        help="replay from this UTC date into an empty ledger to seed state",
    )
    parser.add_argument(
        "--max-census-age-days",
        type=int,
        default=MAX_CENSUS_AGE_DAYS,
        help=(
            "daily mode: fail closed at a monthly universe freeze when the census "
            "was captured more than this many days before the month started"
        ),
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print new events; write nothing"
    )
    parser.add_argument("--now-utc", default=None, help=argparse.SUPPRESS)
    return parser


def _traffic(source: object) -> str:
    """Observed HTTP traffic per host (from the transport guard) for the log."""

    def counts(values: Mapping[str, int]) -> str:
        return ",".join(f"{host}:{n}" for host, n in sorted(values.items())) or "none"

    sent = getattr(source, "requests_by_host", None)
    if sent is None:
        text = " http_requests_by_host=n/a(injected_fetcher)"
    else:
        text = f" http_requests_by_host={counts(sent)}"
        refused = getattr(source, "refused_by_host", None) or {}
        if refused:
            text += f" refused_by_host={counts(refused)}"
    return text + " hyperliquid_client=none"


def main(argv: list[str] | None = None, *, fetcher: KlineFetcher | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = ShadowConfig(
        book_equity=args.book_equity,
        funding_apr=args.funding_apr,
        fee_bps=args.fee_bps,
    )
    lock_handle = None
    source = fetcher or BinanceKlineFetcher()
    try:
        now = _parse_now(args.now_utc)
        if not args.dry_run:
            args.ledger.parent.mkdir(parents=True, exist_ok=True)
            lock_handle = args.ledger.with_name(f"{args.ledger.name}.lock").open("w")
            try:
                fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ShadowError(
                    "another d1_shadow run holds the ledger lock"
                ) from exc
        report = run_shadow(
            ledger_path=args.ledger,
            census_path=args.census,
            config=config,
            fetcher=source,
            now=now,
            backfill_from=args.backfill_from,
            dry_run=args.dry_run,
            volume_column=args.volume_column,
            max_census_age_days=args.max_census_age_days,
        )
    except ShadowError as exc:
        print(f"d1_shadow FAIL-CLOSED: {exc}{_traffic(source)}", file=sys.stderr)
        return 2
    except Exception as exc:  # any other failure also fails closed (exit 2)
        traceback.print_exc(file=sys.stderr)
        print(
            f"d1_shadow FAIL-CLOSED: unexpected {type(exc).__name__}: {exc}"
            f"{_traffic(source)}",
            file=sys.stderr,
        )
        return 2
    finally:
        if lock_handle is not None:
            lock_handle.close()
    if args.dry_run:
        for event in report.appended:
            print(_canonical(event))
    for note in report.notes:
        print(f"d1_shadow note: {note}", file=sys.stderr)
    stamp = datetime.now(UTC).isoformat(timespec="seconds")
    suffix = _traffic(source)
    if args.dry_run:
        suffix += " (dry-run)"
    print(f"{stamp} {report.summary()}{suffix}")
    return 0 if report.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())

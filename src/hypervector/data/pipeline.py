"""Live research history: HL-max first, Binance then Bybit backfill, cache-first.

Cache entries are keyed by symbol, timeframe and lookback length and stand for
"the last N days". Every load reports the window it actually serves (first and
last bar, coverage of the lookback, age of the last bar, fetch time), so a run
can never claim a window it does not hold:

* A cached window whose last bar is older than ``max_cache_age`` (default one
  day), or that holds under 95% of the lookback's bars, is refreshed when
  network is allowed. Offline it is served with ``stale``/``partial`` set and a
  warning naming the window. ``max_cache_age=None`` pins whatever is cached
  (the flags are still reported).
* A window this pipeline fetched less than ``max_cache_age`` ago is served even
  when partial: the venues had nothing more (HL retention, a new listing).
* Strict HL-only loads use their own ``<key>_hlonly`` entry and never write the
  default (backfilled) entry; default loads never read ``_hlonly``.
* A refresh never discards a file the pipeline did not write (a legacy or an
  explicitly installed window): it is renamed to
  ``<key>__preserved_<start>_<end>.parquet`` first, byte for byte.
* Freshness is a data-honesty rule, not a strategy gate: only a technical
  failure (no data, network error while refreshing) aborts a load.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from hypervector.config import DEFAULT_LOOKBACK, ResearchConfig
from hypervector.data.backfill import (
    BackfillUnavailable,
    fetch_binance_ohlcv,
    fetch_bybit_ohlcv,
)
from hypervector.data.cache import ParquetCache
from hypervector.data.history import merge_history
from hypervector.data.hl import fetch_hl_ohlcv
from hypervector.data.provenance import (
    normalize_ohlcv,
    summarize_provenance,
    timeframe_delta,
)
from hypervector.infra import ensure_data_layout

logger = logging.getLogger(__name__)

_TF_BARS_PER_DAY = {"1m": 1440, "5m": 288, "15m": 96, "1h": 24}
DEFAULT_MAX_CACHE_AGE = pd.Timedelta(days=1)
MIN_COVERAGE = 0.95
CACHE_ORIGIN = "research_history"
_HL_SOURCES = ("hl", "hl_gap_fill")
_STRICT_SUFFIX = "_hlonly"


def cache_key(
    symbol: str, timeframe: str, lookback_days: int, *, strict_hl_only: bool = False
) -> str:
    key = f"{symbol.upper()}_{timeframe}_{lookback_days}d"
    return f"{key}{_STRICT_SUFFIX}" if strict_hl_only else key


def strict_hl_only_from_meta(meta: Mapping[str, Any] | None) -> bool:
    """Whether a strategy bundle's research window was loaded strict HL-only.

    Read from ``meta.strict_hl_only`` or the recorded ``data_provenance``, so a
    later replay or training run of the bundle loads the same (``_hlonly``)
    window instead of the Binance/Bybit-backfilled default entry.
    """
    if not isinstance(meta, Mapping):
        return False
    if "strict_hl_only" in meta:
        return meta["strict_hl_only"] is True
    provenance = meta.get("data_provenance")
    return isinstance(provenance, Mapping) and provenance.get("strict_hl_only") is True


def live_hl_fetcher(symbol: str, timeframe: str, lookback_days: int) -> pd.DataFrame:
    return fetch_hl_ohlcv(symbol, timeframe, lookback_days)


def live_binance_fetcher(
    symbol: str, timeframe: str, lookback_days: int
) -> pd.DataFrame:
    return fetch_binance_ohlcv(symbol, timeframe, lookback_days)


def live_bybit_fetcher(symbol: str, timeframe: str, lookback_days: int) -> pd.DataFrame:
    return fetch_bybit_ohlcv(symbol, timeframe, lookback_days)


def _expected_bars(timeframe: str, lookback_days: int) -> int:
    return int(lookback_days * _TF_BARS_PER_DAY.get(timeframe, 1440))


@dataclass(frozen=True)
class _Request:
    symbol: str
    timeframe: str
    lookback_days: int
    strict_hl_only: bool
    now: pd.Timestamp
    max_cache_age: pd.Timedelta | None
    tolerance: pd.Timedelta


@dataclass(frozen=True)
class _Window:
    start: pd.Timestamp | None
    end: pd.Timestamp | None
    bars: int
    expected_bars: int
    coverage: float
    age: pd.Timedelta | None
    stale: bool
    partial: bool
    fetched_at: pd.Timestamp | None
    recently_fetched: bool

    def reason(self) -> str:
        parts = []
        if self.stale:
            parts.append("stale")
        if self.partial:
            parts.append("partial")
        return "+".join(parts)


@dataclass(frozen=True)
class _CacheHit:
    key: str
    path: Path
    frame: pd.DataFrame
    metadata: dict[str, Any] | None
    window: _Window
    hl_only: bool

    def needs_refresh(self, request: _Request) -> bool:
        if request.max_cache_age is None or self.window.recently_fetched:
            return False
        return self.window.stale or self.window.partial


def load_research_history(
    data_root: Path | str,
    *,
    symbol: str = "BTC",
    timeframe: str = "1m",
    lookback_days: int = DEFAULT_LOOKBACK,
    strict_hl_only: bool = False,
    force_refresh: bool = False,
    allow_network: bool = True,
    config: ResearchConfig | None = None,
    max_cache_age: pd.Timedelta | None = DEFAULT_MAX_CACHE_AGE,
    now: pd.Timestamp | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Cache-first live history: HL max, then Binance → Bybit gap fill.

    HL wins on timestamp overlap. Provenance is per-bar ``source`` plus the
    served window (``start``/``end``, ``coverage_ratio``, ``age_seconds``,
    ``stale``/``partial``, cache key/path, fetch time, backfill status).
    Bybit is only called when HL+Binance still leave a material hole
    (<95% of expected bars for the lookback). See the module docstring for the
    freshness rules; ``now`` exists for deterministic tests.
    """
    if force_refresh and not allow_network:
        raise ValueError("offline history cannot force a network refresh")
    if config is not None:
        symbol = config.symbol
        timeframe = config.timeframe
        lookback_days = config.lookback_days
        strict_hl_only = config.strict_hl_only

    request = _request(
        symbol, timeframe, lookback_days, strict_hl_only, max_cache_age, now
    )
    root = ensure_data_layout(data_root).root
    cache = ParquetCache(root / "cache")
    key = cache_key(symbol, timeframe, lookback_days, strict_hl_only=strict_hl_only)

    refresh_reason: str | None = "force_refresh" if force_refresh else None
    if not force_refresh:
        stale_hit: _CacheHit | None = None
        for candidate in _candidate_keys(request):
            hit = _read_cache(cache, candidate, request)
            if hit is None:
                continue
            if strict_hl_only and candidate != key and not hit.hl_only:
                logger.info(
                    "strict HL load bypassing incompatible mixed-venue cache %s",
                    candidate,
                )
                continue
            if not hit.needs_refresh(request):
                return hit.frame, _served_from_cache(hit, request, note=None)
            stale_hit = stale_hit or hit
        if stale_hit is not None:
            if not allow_network:
                return stale_hit.frame, _served_from_cache(
                    stale_hit, request, note="network not allowed; serving it as is"
                )
            refresh_reason = stale_hit.window.reason()
            logger.warning(
                "history cache %s is %s (%s); refreshing",
                stale_hit.key,
                refresh_reason,
                _describe(stale_hit.window),
            )

    if not allow_network:
        raise FileNotFoundError(
            f"offline history cache missing or incompatible: {cache.path_for(key)}"
        )

    merged, backfill = _fetch(cache, request)
    preserved = _preserve_unmanaged(cache, key)
    metadata = _metadata(request, strict_hl_only=strict_hl_only, backfill=backfill)
    path = cache.save(key, merged, metadata=metadata)
    window = _assess(merged, metadata, request)
    provenance = _provenance(
        merged,
        window,
        request,
        key=key,
        path=path,
        cache_hit=False,
        refresh_reason=refresh_reason,
        backfill=backfill,
        preserved=preserved,
        note=None,
    )
    return merged, provenance


def _request(
    symbol: str,
    timeframe: str,
    lookback_days: int,
    strict_hl_only: bool,
    max_cache_age: pd.Timedelta | None,
    now: pd.Timestamp | None,
) -> _Request:
    if isinstance(max_cache_age, (bool, int, float)):
        # pd.Timedelta(3600) is 3600 nanoseconds; refuse the ambiguity.
        raise TypeError("max_cache_age must be a Timedelta (or None), not a number")
    age = None if max_cache_age is None else pd.Timedelta(max_cache_age)
    if age is not None and age <= pd.Timedelta(0):
        raise ValueError("max_cache_age must be positive or None")
    clock = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    clock = clock.tz_localize("UTC") if clock.tzinfo is None else clock.tz_convert("UTC")
    tolerance = age if age is not None else DEFAULT_MAX_CACHE_AGE
    bar = timeframe_delta(timeframe)
    if bar is not None:
        # The newest closed bar is up to one bar old; never call that stale.
        tolerance = max(tolerance, 2 * bar)
    return _Request(
        symbol=symbol,
        timeframe=timeframe,
        lookback_days=int(lookback_days),
        strict_hl_only=strict_hl_only,
        now=clock,
        max_cache_age=age,
        tolerance=tolerance,
    )


def _candidate_keys(request: _Request) -> tuple[str, ...]:
    default = cache_key(request.symbol, request.timeframe, request.lookback_days)
    if not request.strict_hl_only:
        return (default,)
    strict = cache_key(
        request.symbol, request.timeframe, request.lookback_days, strict_hl_only=True
    )
    # A default entry that is entirely HL may serve a strict load (read only).
    return (strict, default)


def _read_cache(cache: ParquetCache, key: str, request: _Request) -> _CacheHit | None:
    if not cache.exists(key):
        return None
    frame = cache.load(key)
    assert frame is not None
    metadata = cache.load_metadata(key)
    hl_only = "source" in frame and bool(frame["source"].isin(_HL_SOURCES).all())
    return _CacheHit(
        key=key,
        path=cache.path_for(key),
        frame=frame,
        metadata=metadata,
        window=_assess(frame, metadata, request),
        hl_only=hl_only,
    )


def _assess(
    frame: pd.DataFrame, metadata: dict[str, Any] | None, request: _Request
) -> _Window:
    expected = _expected_bars(request.timeframe, request.lookback_days)
    start = end = age = None
    if len(frame):
        ts = pd.to_datetime(frame["timestamp"], utc=True)
        start, end = ts.min(), ts.max()
        age = request.now - end
    coverage = len(frame) / expected if expected else 1.0
    fetched_at = _fetched_at(metadata)
    return _Window(
        start=start,
        end=end,
        bars=int(len(frame)),
        expected_bars=expected,
        coverage=coverage,
        age=age,
        stale=age is None or age > request.tolerance,
        partial=coverage < MIN_COVERAGE,
        fetched_at=fetched_at,
        recently_fetched=(
            fetched_at is not None and request.now - fetched_at <= request.tolerance
        ),
    )


def _fetched_at(metadata: dict[str, Any] | None) -> pd.Timestamp | None:
    if not metadata or metadata.get("origin") != CACHE_ORIGIN:
        return None
    try:
        value = pd.Timestamp(metadata.get("fetched_at"))
    except (TypeError, ValueError):
        return None
    if pd.isna(value):
        return None
    return value.tz_localize("UTC") if value.tzinfo is None else value.tz_convert("UTC")


def _fetch(
    cache: ParquetCache, request: _Request
) -> tuple[pd.DataFrame, dict[str, str]]:
    symbol, timeframe, lookback = (
        request.symbol,
        request.timeframe,
        request.lookback_days,
    )
    hl_df = live_hl_fetcher(symbol, timeframe, lookback)
    if hl_df is not None and len(hl_df):
        hl_df = normalize_ohlcv(
            hl_df, source="hl" if "source" not in hl_df.columns else None
        )
    else:
        hl_df = None

    backfills: list[tuple[str, pd.DataFrame]] = []
    if request.strict_hl_only:
        status = {name: "skipped: strict HL-only" for name in ("binance", "bybit")}
    elif ":" in symbol.strip():
        # HIP-3 dex:ASSET (same test as hl_coin) has no Binance/Bybit instrument.
        logger.info("HIP-3 %s: CEX backfill not applicable; loading HL-only history", symbol)
        status = {
            name: "not_applicable: HIP-3 dex:ASSET has no CEX equivalent"
            for name in ("binance", "bybit")
        }
    else:
        try:
            backfills, status = _cex_backfill(request, hl_df)
        except Exception as exc:
            _keep_hl_only(cache, request, hl_df, exc)
            raise

    merged = merge_history(hl_df, backfills)
    if len(merged) == 0:
        raise RuntimeError(f"no history for {symbol} {timeframe} lookback={lookback}d")
    return merged, status


def _cex_backfill(
    request: _Request, hl_df: pd.DataFrame | None
) -> tuple[list[tuple[str, pd.DataFrame]], dict[str, str]]:
    status: dict[str, str] = {}
    backfills: list[tuple[str, pd.DataFrame]] = []
    bn = _optional_backfill("binance", live_binance_fetcher, request, status)
    if bn is not None and len(bn):
        backfills.append(("binance", bn))

    partial = merge_history(hl_df, backfills)
    expected = _expected_bars(request.timeframe, request.lookback_days)
    coverage = len(partial) / expected if expected else 1.0
    if coverage < MIN_COVERAGE:
        logger.info(
            "HL+Binance coverage %.1f%% < 95%% — fetching Bybit backfill",
            100 * coverage,
        )
        bb = _optional_backfill("bybit", live_bybit_fetcher, request, status)
        if bb is not None and len(bb):
            backfills.append(("bybit", bb))
    else:
        status["bybit"] = f"skipped: HL+Binance coverage {coverage:.1%}"
        logger.info(
            "HL+Binance coverage %.1f%% — skip Bybit",
            100 * coverage,
        )
    return backfills, status


def _optional_backfill(
    name: str,
    fetcher: Any,
    request: _Request,
    status: dict[str, str],
) -> pd.DataFrame | None:
    """Run one CEX fetcher; only "venue does not list it" is tolerated."""
    try:
        frame = fetcher(request.symbol, request.timeframe, request.lookback_days)
    except BackfillUnavailable as exc:
        status[name] = f"unavailable: {exc}"
        logger.warning(
            "%s backfill unavailable for %s (%s); keeping HL history",
            name,
            request.symbol,
            exc,
        )
        return None
    status[name] = f"ok: {0 if frame is None else len(frame)} bars"
    return frame


def _keep_hl_only(
    cache: ParquetCache,
    request: _Request,
    hl_df: pd.DataFrame | None,
    exc: BaseException,
) -> None:
    """A failed backfill stays loud, but the HL candles it fetched are kept."""
    if hl_df is None or not len(hl_df):
        return
    key = cache_key(
        request.symbol, request.timeframe, request.lookback_days, strict_hl_only=True
    )
    status = {
        name: f"skipped: backfill failed ({type(exc).__name__})"
        for name in ("binance", "bybit")
    }
    try:
        _preserve_unmanaged(cache, key)
        cache.save(key, hl_df, metadata=_metadata(request, strict_hl_only=True, backfill=status))
    except Exception as save_exc:  # noqa: BLE001 — the backfill failure stays the raised error
        exc.add_note(f"could not keep the fetched HL history: {save_exc}")
        return
    exc.add_note(
        f"{len(hl_df)} fetched HL bars were kept in cache key {key}; retry later "
        "(commands that offer --strict-hl-only can use that HL-only history now)"
    )


def _metadata(
    request: _Request, *, strict_hl_only: bool, backfill: dict[str, str]
) -> dict[str, Any]:
    return {
        "origin": CACHE_ORIGIN,
        "fetched_at": request.now.isoformat(),
        "symbol": request.symbol,
        "timeframe": request.timeframe,
        "lookback_days": request.lookback_days,
        "strict_hl_only": strict_hl_only,
        "backfill": backfill,
    }


def _preserve_unmanaged(cache: ParquetCache, key: str) -> str | None:
    """Rename a file this pipeline did not write before it is replaced."""
    path = cache.path_for(key)
    if not path.is_file():
        return None
    try:
        metadata = cache.load_metadata(key)
    except Exception:  # noqa: BLE001 — an unreadable footer is still kept
        metadata = None
    if metadata is not None and metadata.get("origin") == CACHE_ORIGIN:
        return None
    label = _window_label(path)
    target = path.with_name(f"{path.stem}__preserved_{label}.parquet")
    counter = 1
    while target.exists():
        target = path.with_name(f"{path.stem}__preserved_{label}_{counter}.parquet")
        counter += 1
    try:
        os.replace(path, target)
    except FileNotFoundError:
        # A concurrent refresh of the same key already moved it aside.
        return None
    logger.warning(
        "kept unmanaged cache %s as %s before refreshing it", path.name, target.name
    )
    return str(target)


def _window_label(path: Path) -> str:
    try:
        ts = pd.to_datetime(
            pd.read_parquet(path, columns=["timestamp"])["timestamp"], utc=True
        )
    except Exception:  # noqa: BLE001 — label only; the bytes are kept regardless
        return "unreadable"
    if ts.empty:
        return "empty"
    return f"{ts.min():%Y%m%dT%H%MZ}_{ts.max():%Y%m%dT%H%MZ}"


def _served_from_cache(hit: _CacheHit, request: _Request, *, note: str | None) -> dict[str, Any]:
    if note is None and (hit.window.stale or hit.window.partial):
        if request.max_cache_age is None:
            note = "cache pinned (max_cache_age=None); serving it as is"
        elif hit.window.recently_fetched:
            note = "fetched recently; the venues had no more history"
    backfill = (hit.metadata or {}).get("backfill")
    return _provenance(
        hit.frame,
        hit.window,
        request,
        key=hit.key,
        path=hit.path,
        cache_hit=True,
        refresh_reason=None,
        backfill=backfill if isinstance(backfill, dict) else None,
        preserved=None,
        note=note,
    )


def _provenance(
    frame: pd.DataFrame,
    window: _Window,
    request: _Request,
    *,
    key: str,
    path: Path,
    cache_hit: bool,
    refresh_reason: str | None,
    backfill: dict[str, str] | None,
    preserved: str | None,
    note: str | None,
) -> dict[str, Any]:
    provenance = summarize_provenance(frame, timeframe=request.timeframe)
    warnings = _window_warnings(window, request, key, note)
    for message in warnings:
        logger.warning(message)
    provenance.update(
        {
            "symbol": request.symbol,
            "lookback_days": request.lookback_days,
            "strict_hl_only": request.strict_hl_only,
            "expected_bars": window.expected_bars,
            "coverage_ratio": round(window.coverage, 6),
            "cache_key": key,
            "cache_path": str(path),
            "cache_hit": cache_hit,
            "refreshed": refresh_reason is not None and not cache_hit,
            "refresh_reason": refresh_reason,
            "fetched_at": (
                window.fetched_at.isoformat() if window.fetched_at is not None else None
            ),
            "age_seconds": (
                float(window.age.total_seconds()) if window.age is not None else None
            ),
            "max_cache_age_seconds": (
                float(request.max_cache_age.total_seconds())
                if request.max_cache_age is not None
                else None
            ),
            "stale": window.stale,
            "partial": window.partial,
            "backfill": backfill,
            "preserved_previous": preserved,
            "warnings": warnings,
        }
    )
    return provenance


def _window_warnings(
    window: _Window, request: _Request, key: str, note: str | None
) -> list[str]:
    if not (window.stale or window.partial):
        return []
    message = (
        f"history {key} for the last {request.lookback_days}d is "
        f"{window.reason()}: {_describe(window)}"
    )
    if note:
        message = f"{message}; {note}"
    return [message]


def _describe(window: _Window) -> str:
    if window.start is None or window.end is None:
        return "no bars"
    age_days = window.age.total_seconds() / 86_400 if window.age is not None else 0.0
    return (
        f"covers {window.start:%Y-%m-%dT%H:%MZ}..{window.end:%Y-%m-%dT%H:%MZ}, "
        f"{window.bars} of {window.expected_bars} bars ({window.coverage:.1%}), "
        f"last bar {age_days:.2f}d old"
    )

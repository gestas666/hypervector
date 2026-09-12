"""Bounded venue-native Hyperliquid candle acquisition from 0xArchive."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import datetime
import json
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_api import (
    HttpSession,
    OxaRestClient,
    parse_utc_timestamp_ms,
    validate_window,
)
from hypervector.data.oxa_candle_request import (
    CandleInterval as CandleInterval,
    OxaCandleRequest as OxaCandleRequest,
)
from hypervector.data.provenance import normalize_ohlcv
from hypervector.data.oxa_storage import (
    file_evidence,
    open_text_reader,
    publish_immutable_directory,
    verify_file_evidence,
    write_gzip_json,
    write_json,
)

_PANDAS_FREQUENCIES = {
    "1m": "1min",
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
    "1h": "1h",
    "4h": "4h",
    "1d": "1D",
    "1w": "7D",
}


@dataclass(frozen=True)
class OxaCandle:
    """One validated Hyperliquid OHLCV interval."""

    timestamp: str
    ts_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: float
    trade_count: int

    def to_bar(self) -> dict[str, object]:
        """Return the canonical research OHLCV representation."""
        row = asdict(self)
        row.pop("ts_ms")
        row["source"] = "hl"
        return row


@dataclass(frozen=True)
class OxaCandlePage:
    """One validated vendor candle response envelope."""

    request_id: str
    next_cursor: str | None
    candles: tuple[OxaCandle, ...]
    raw_payload: dict[str, object]


@dataclass(frozen=True)
class OxaCandleFetch:
    """Bounded candle pages and their normalized unique intervals."""

    pages: tuple[OxaCandlePage, ...]
    candles: tuple[OxaCandle, ...]
    complete: bool
    continuation_cursor: str | None

    @property
    def request_ids(self) -> tuple[str, ...]:
        """Return vendor request identifiers in page order."""
        return tuple(page.request_id for page in self.pages)


@dataclass(frozen=True)
class OxaStoredCandles:
    """Published raw evidence, normalized Parquet, and manifest paths."""

    directory: Path
    candles_path: Path
    manifest_path: Path


class OxaCandleClient:
    """Authenticated REST boundary for Hyperliquid venue candles."""

    def __init__(self, *, api_key: str, session: HttpSession | None = None) -> None:
        self._client = OxaRestClient(api_key=api_key, session=session)

    def fetch_page(
        self, request: OxaCandleRequest, *, cursor: str | None = None
    ) -> OxaCandlePage:
        """Fetch and validate one bounded candle page."""
        payload = self._client.get(
            request.route(),
            params=request.params(cursor),
            timeout=request.timeout_seconds,
        )
        return _parse_page(payload, request)


def fetch_candle_history(
    client: OxaCandleClient, request: OxaCandleRequest
) -> OxaCandleFetch:
    """Fetch bounded pages and reject conflicting cursor-boundary candles."""
    pages: list[OxaCandlePage] = []
    cursor: str | None = None
    for _ in range(request.max_pages):
        page = client.fetch_page(request, cursor=cursor)
        pages.append(page)
        cursor = page.next_cursor
        if cursor is None:
            break
    candles = _merge_candles(pages, end_ms=int(request.end.timestamp() * 1000))
    return OxaCandleFetch(tuple(pages), candles, cursor is None, cursor)


def candle_output_directory(data_root: Path | str, request: OxaCandleRequest) -> Path:
    """Return the immutable bundle directory for one candle window."""
    stamp = "%Y%m%dT%H%M%S%fZ"
    window = f"{request.start.strftime(stamp)}_{request.end.strftime(stamp)}"
    root = Path(data_root) / "cache" / "vendor" / "0xarchive" / "hyperliquid"
    if request.market_family == "hip3":
        root /= "hip3"
    return root / request.symbol / f"{window}_candles_{request.interval}"


def store_candle_history(
    data_root: Path | str,
    request: OxaCandleRequest,
    result: OxaCandleFetch,
) -> OxaStoredCandles:
    """Atomically publish raw candle pages, normalized Parquet, and manifest."""
    final = candle_output_directory(data_root, request)

    def write_bundle(staging: Path) -> None:
        raw_dir = staging / "raw"
        raw_dir.mkdir()
        files = _write_raw_pages(raw_dir, result.pages)
        candles_path = staging / "candles.parquet"
        pd.DataFrame(candle.to_bar() for candle in result.candles).to_parquet(
            candles_path, index=False
        )
        files["candles.parquet"] = file_evidence(candles_path)
        write_json(staging / "manifest.json", _manifest(request, result, files))

    publish_immutable_directory(final, write_bundle)
    return OxaStoredCandles(final, final / "candles.parquet", final / "manifest.json")


def acquire_and_store_candles(
    *, data_root: Path | str, api_key: str, request: OxaCandleRequest
) -> dict[str, object]:
    """Acquire a complete candle window and return a secret-free report."""
    result = fetch_candle_history(OxaCandleClient(api_key=api_key), request)
    if not result.complete:
        raise ValueError("candle max-pages exhausted before completing the window")
    stored = store_candle_history(data_root, request, result)
    return {
        "ok": True,
        "venue": "hyperliquid",
        "source": request.source,
        "market_family": request.market_family,
        "symbol": request.symbol,
        "interval": request.interval,
        "row_count": len(result.candles),
        "page_count": len(result.pages),
        "request_ids": list(result.request_ids),
        "complete": result.complete,
        "directory": str(stored.directory.resolve()),
        "candles_path": str(stored.candles_path.resolve()),
        "manifest_path": str(stored.manifest_path.resolve()),
    }


def read_complete_candle_evidence(
    bundle: Path,
    request: OxaCandleRequest,
    *,
    require_complete_cadence: bool = False,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Verify and reproduce one immutable candle bundle without network access."""
    manifest = _read_candle_manifest(bundle)
    _verify_manifest_request(manifest, request)
    verify_file_evidence(bundle, manifest.get("files"))
    pages = _read_manifest_pages(bundle, manifest, request)
    reproduced = _merge_candles(list(pages), end_ms=int(request.end.timestamp() * 1000))
    frame = pd.read_parquet(bundle / "candles.parquet")
    _verify_reproduced_candles(frame, reproduced, manifest)
    if require_complete_cadence:
        _verify_complete_cadence(frame, request)
    return frame, {
        "bundle": str(bundle.resolve()),
        "manifest": file_evidence(bundle / "manifest.json"),
        "candles": file_evidence(bundle / "candles.parquet"),
        "raw_page_count": len(pages),
        "row_count": len(frame),
        "raw_reproduction_matches": True,
        "complete_cadence_required": require_complete_cadence,
    }


def repair_candle_cadence(
    frame: pd.DataFrame,
    *,
    start: datetime,
    end: datetime,
    max_gap_minutes: int = 30,
) -> tuple[pd.DataFrame, int]:
    """Fill bounded missing minutes with labeled zero-volume continuity bars."""
    validate_window(start, end)
    if max_gap_minutes < 1:
        raise ValueError("max_gap_minutes must be positive")
    bars = normalize_ohlcv(frame)
    expected = pd.date_range(start, end, freq="1min", inclusive="left")
    indexed = bars.set_index("timestamp").reindex(expected)
    missing = indexed["close"].isna()
    if missing.iloc[0]:
        raise ValueError("cannot repair a leading candle gap without prior close")
    run_lengths = missing.groupby((~missing).cumsum()).sum()
    if not run_lengths.empty and int(run_lengths.max()) > max_gap_minutes:
        raise ValueError("candle gap exceeds the configured continuity repair bound")
    prior_close = indexed["close"].ffill()
    for column in ("open", "high", "low", "close"):
        indexed.loc[missing, column] = prior_close.loc[missing]
    indexed.loc[missing, "volume"] = 0.0
    indexed.loc[missing, "source"] = "hl_gap_fill"
    indexed.index.name = "timestamp"
    return normalize_ohlcv(indexed.reset_index()), int(missing.sum())


def _read_candle_manifest(bundle: Path) -> dict[str, object]:
    path = bundle / "manifest.json"
    if not path.is_file():
        raise FileNotFoundError(f"candle manifest is missing: {path}")
    payload: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("candle manifest must be an object")
    return payload


def _verify_manifest_request(
    manifest: dict[str, object], request: OxaCandleRequest
) -> None:
    expected: dict[str, object] = {
        "schema_version": 1,
        "source": request.source,
        "source_api": request.source_api,
        "venue": "hyperliquid",
        "symbol": request.symbol,
        "interval": request.interval,
        "requested_start": request.start.isoformat(),
        "requested_end": request.end.isoformat(),
        "page_limit": request.limit,
        "max_pages": request.max_pages,
        "complete": True,
        "continuation_cursor": None,
    }
    if request.market_family == "hip3" or "market_family" in manifest:
        expected["market_family"] = request.market_family
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise ValueError("candle manifest differs from the exact request")


def _read_manifest_pages(
    bundle: Path,
    manifest: dict[str, object],
    request: OxaCandleRequest,
) -> tuple[OxaCandlePage, ...]:
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise ValueError("candle manifest files must be an object")
    paths = tuple(sorted(key for key in files if key.startswith("raw/")))
    page_count = manifest.get("page_count")
    if isinstance(page_count, bool) or not isinstance(page_count, int):
        raise ValueError("candle manifest page count must be an integer")
    if not paths or len(paths) != page_count:
        raise ValueError("candle manifest raw-page coverage is inconsistent")
    pages = tuple(_read_candle_page(bundle / path, request) for path in paths)
    _verify_page_sequence(pages, manifest)
    return pages


def _read_candle_page(path: Path, request: OxaCandleRequest) -> OxaCandlePage:
    with open_text_reader(path) as handle:
        payload: object = json.load(handle)
    return _parse_page(payload, request)


def _verify_page_sequence(
    pages: tuple[OxaCandlePage, ...], manifest: dict[str, object]
) -> None:
    request_ids = manifest.get("request_ids")
    if not isinstance(request_ids, list) or any(
        not isinstance(value, str) for value in request_ids
    ):
        raise ValueError("candle manifest request identifiers are invalid")
    if tuple(request_ids) != tuple(page.request_id for page in pages):
        raise ValueError("candle raw-page request identifiers differ from manifest")
    if any(page.next_cursor is None for page in pages[:-1]):
        raise ValueError("candle raw-page cursor chain terminates early")
    if pages[-1].next_cursor is not None:
        raise ValueError("candle raw-page cursor chain is incomplete")


def _verify_reproduced_candles(
    frame: pd.DataFrame,
    reproduced: tuple[OxaCandle, ...],
    manifest: dict[str, object],
) -> None:
    row_count = manifest.get("row_count")
    if isinstance(row_count, bool) or not isinstance(row_count, int):
        raise ValueError("candle manifest row count must be an integer")
    if len(frame) != row_count or len(reproduced) != row_count:
        raise ValueError("candle row count differs from manifest or raw pages")
    expected = pd.DataFrame(candle.to_bar() for candle in reproduced)
    try:
        pd.testing.assert_frame_equal(frame, expected, check_exact=True)
    except AssertionError as exc:
        raise ValueError("candle Parquet differs from normalized raw pages") from exc


def _verify_complete_cadence(frame: pd.DataFrame, request: OxaCandleRequest) -> None:
    if "timestamp" not in frame.columns:
        raise ValueError("candle Parquet is missing timestamp")
    observed = pd.DatetimeIndex(pd.to_datetime(frame["timestamp"], utc=True))
    expected = pd.date_range(
        request.start,
        request.end,
        freq=_PANDAS_FREQUENCIES[request.interval],
        inclusive="left",
    )
    if not observed.equals(expected):
        raise ValueError("candle timestamps do not provide exact complete cadence")


def _parse_page(payload: object, request: OxaCandleRequest) -> OxaCandlePage:
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise ValueError("0xArchive candle response must be a successful object")
    data, meta = payload.get("data"), payload.get("meta")
    if not isinstance(data, list) or not isinstance(meta, dict):
        raise ValueError("0xArchive candle response is missing data or meta")
    request_id, cursor = meta.get("request_id"), meta.get("next_cursor")
    if not isinstance(request_id, str) or not request_id:
        raise ValueError("0xArchive candle response is missing request_id")
    if cursor is not None and not isinstance(cursor, str):
        raise ValueError("0xArchive candle cursor must be a string or null")
    candles = tuple(_parse_candle(row, request) for row in data)
    return OxaCandlePage(request_id, cursor, candles, payload)


def _parse_candle(value: object, request: OxaCandleRequest) -> OxaCandle:
    if not isinstance(value, dict):
        raise ValueError("0xArchive candle data must contain objects")
    timestamp = value.get("timestamp")
    if not isinstance(timestamp, str):
        raise ValueError("candle timestamp must be a string")
    ts_ms = parse_utc_timestamp_ms(timestamp, label="candle timestamp")
    bounds = request.params()
    if not bounds["start"] <= ts_ms <= bounds["end"]:
        raise ValueError("candle timestamp is outside requested window")
    prices = tuple(_finite_number(value.get(key), key) for key in _PRICE_KEYS)
    open_, high, low, close = prices
    if low > min(open_, close) or high < max(open_, close) or low > high:
        raise ValueError("candle OHLC values are inconsistent")
    volume = _finite_number(value.get("volume"), "volume", allow_zero=True)
    quote = _finite_number(value.get("quote_volume"), "quote_volume", allow_zero=True)
    count = value.get("trade_count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError("candle trade_count must be a non-negative integer")
    return OxaCandle(timestamp, ts_ms, *prices, volume, quote, count)


_PRICE_KEYS = ("open", "high", "low", "close")


def _finite_number(value: object, label: str, *, allow_zero: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"candle {label} must be numeric")
    number = float(value)
    minimum = 0.0 if allow_zero else 0.0
    if (
        not math.isfinite(number)
        or number < minimum
        or (not allow_zero and number == 0)
    ):
        raise ValueError(f"candle {label} must be finite and non-negative")
    return number


def _merge_candles(pages: list[OxaCandlePage], *, end_ms: int) -> tuple[OxaCandle, ...]:
    merged: dict[int, OxaCandle] = {}
    for page in pages:
        for candle in page.candles:
            if candle.ts_ms == end_ms:
                continue
            existing = merged.get(candle.ts_ms)
            if existing is not None and existing != candle:
                raise ValueError("conflicting duplicate candle timestamp")
            merged[candle.ts_ms] = candle
    return tuple(merged[key] for key in sorted(merged))


def _write_raw_pages(
    raw_dir: Path, pages: tuple[OxaCandlePage, ...]
) -> dict[str, dict[str, object]]:
    evidence: dict[str, dict[str, object]] = {}
    for index, page in enumerate(pages, start=1):
        path = raw_dir / f"page-{index:04d}.json.gz"
        write_gzip_json(path, page.raw_payload)
        evidence[f"raw/{path.name}"] = file_evidence(path)
    return evidence


def _manifest(
    request: OxaCandleRequest,
    result: OxaCandleFetch,
    files: dict[str, dict[str, object]],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "source": request.source,
        "source_api": request.source_api,
        "market_family": request.market_family,
        "venue": "hyperliquid",
        "symbol": request.symbol,
        "interval": request.interval,
        "requested_start": request.start.isoformat(),
        "requested_end": request.end.isoformat(),
        "page_limit": request.limit,
        "max_pages": request.max_pages,
        "request_ids": list(result.request_ids),
        "page_count": len(result.pages),
        "row_count": len(result.candles),
        "complete": result.complete,
        "continuation_cursor": result.continuation_cursor,
        "files": files,
    }

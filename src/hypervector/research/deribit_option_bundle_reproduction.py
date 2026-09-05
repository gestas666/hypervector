"""Independent raw-to-normalized reproduction for Deribit option bundles."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Protocol

import pyarrow.parquet as pq

from hypervector.data.oxa_storage import (
    file_evidence,
    open_text_reader,
    verify_file_evidence,
)
from hypervector.research.deribit_option_trade_acquisition import (
    DAY_MS,
    OptionTrade,
    TradePage,
    TradeWindow,
    parse_instruments,
    parse_trade_page,
)


_SCHEMA = "deribit_btc_option_flow_source_bundle_v1"


class _DigestProtocol(Protocol):
    def update(self, value: bytes) -> None: ...


@dataclass(frozen=True)
class DeribitRawReproductionAudit:
    """Exact normalized-row reproduction evidence for one immutable bundle."""

    bundle: str
    manifest: dict[str, object]
    normalized_trade_rows: int
    normalized_instrument_rows: int
    raw_trade_pages: int
    truncated_trade_pages: int
    terminal_trade_pages: int
    terminal_window_coverage_complete: bool
    duplicate_trades_removed: int
    raw_trade_rows_sha256: str
    parquet_trade_rows_sha256: str
    raw_instrument_rows_sha256: str
    parquet_instrument_rows_sha256: str
    trade_rows_match: bool
    instrument_rows_match: bool
    all_registered_files_verified: bool

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible reproduction record."""
        return asdict(self)


@dataclass(frozen=True)
class _RawTradeDigest:
    rows: int
    pages: int
    truncated_pages: int
    terminal_pages: int
    duplicates: int
    sha256: str
    terminal_window_coverage_complete: bool


def reproduce_deribit_option_bundle(bundle: Path) -> DeribitRawReproductionAudit:
    """Reparse every registered raw page and compare exact normalized row hashes."""
    manifest = _validated_manifest(bundle)
    raw_trades = _digest_raw_trades(
        bundle, _requests(manifest), _mapping(manifest, "coverage")
    )
    parquet_trades = _digest_rows(_parquet_rows(bundle / "trades.parquet"))
    raw_instruments = _raw_instrument_rows(bundle)
    raw_instrument_digest = _digest_rows(raw_instruments)
    parquet_instruments = _digest_rows(_parquet_rows(bundle / "instruments.parquet"))
    _validate_counts(manifest, raw_trades, parquet_trades, parquet_instruments)
    trade_match = raw_trades.rows == parquet_trades[0] and (
        raw_trades.sha256 == parquet_trades[1]
    )
    instrument_match = raw_instrument_digest == parquet_instruments
    if not trade_match:
        raise ValueError("Deribit raw trade pages do not reproduce normalized Parquet")
    if not instrument_match:
        raise ValueError("Deribit raw instruments do not reproduce normalized Parquet")
    return _audit(
        bundle,
        raw_trades,
        parquet_trades,
        raw_instrument_digest,
        parquet_instruments,
    )


def _validated_manifest(bundle: Path) -> dict[str, object]:
    path = bundle / "manifest.json"
    if not path.is_file():
        raise FileNotFoundError(f"Deribit option-flow manifest is missing: {path}")
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Deribit option-flow manifest must be an object")
    expected = {
        "schema_version": _SCHEMA,
        "source": "deribit_official_btc_option_trades",
        "symbol": "BTC",
        "report_only": True,
        "execution_authority": "none",
        "candidate_outcomes_computed": False,
    }
    if any(
        value.get(key) != expected_value for key, expected_value in expected.items()
    ):
        raise ValueError("Deribit option-flow manifest identity or authority drifted")
    verify_file_evidence(bundle, value.get("files"))
    return value


def _digest_raw_trades(
    bundle: Path,
    requests: Sequence[Mapping[str, object]],
    coverage: Mapping[str, object],
) -> _RawTradeDigest:
    digest = sha256()
    current_day: int | None = None
    day_trades: list[OptionTrade] = []
    rows = pages = truncated = duplicates = 0
    terminal_windows: list[TradeWindow] = []
    for request in requests:
        page = _read_registered_page(bundle, request)
        pages += 1
        truncated += int(page.has_more)
        day = page.window.start_ms // DAY_MS * DAY_MS
        if current_day is not None and day < current_day:
            raise ValueError("Deribit raw trade requests are not day ordered")
        if current_day is not None and day != current_day:
            added, removed = _digest_unique_day(digest, day_trades)
            rows += added
            duplicates += removed
            day_trades = []
        current_day = day
        if not page.has_more:
            day_trades.extend(page.trades)
            terminal_windows.append(page.window)
    added, removed = _digest_unique_day(digest, day_trades)
    rows += added
    duplicates += removed
    _validate_terminal_coverage(coverage, terminal_windows)
    return _RawTradeDigest(
        rows,
        pages,
        truncated,
        len(terminal_windows),
        duplicates,
        digest.hexdigest(),
        True,
    )


def _validate_terminal_coverage(
    coverage: Mapping[str, object], windows: Sequence[TradeWindow]
) -> None:
    start = _integer(coverage.get("start_timestamp_ms"), "coverage start")
    end = _integer(coverage.get("end_timestamp_ms_exclusive"), "coverage end")
    if end <= start or not windows:
        raise ValueError("Deribit terminal trade-window coverage is empty or invalid")
    cursor = start
    for window in sorted(windows, key=lambda value: (value.start_ms, value.end_ms)):
        if window.start_ms != cursor:
            raise ValueError("Deribit terminal trade windows have a gap or overlap")
        cursor = window.end_ms
    if cursor != end:
        raise ValueError("Deribit terminal trade windows do not cover the source end")


def _read_registered_page(bundle: Path, request: Mapping[str, object]) -> TradePage:
    page_number = _integer(request.get("page"), "request page")
    start = _integer(request.get("start_timestamp"), "request start")
    inclusive_end = _integer(request.get("end_timestamp"), "request end")
    window = TradeWindow(start, inclusive_end + 1)
    path = bundle / "raw" / "trades" / f"page_{page_number:06d}.json.gz"
    with open_text_reader(path) as handle:
        content = handle.read().encode("utf-8")
    page = parse_trade_page(content, window)
    if request.get("rows") != len(page.trades):
        raise ValueError("Deribit raw trade request row count drifted")
    if request.get("has_more") is not page.has_more:
        raise ValueError("Deribit raw trade truncation flag drifted")
    if request.get("normalized") is not (not page.has_more):
        raise ValueError("Deribit raw trade normalization flag drifted")
    return page


def _digest_unique_day(
    digest: _DigestProtocol,
    trades: Sequence[OptionTrade],
) -> tuple[int, int]:
    by_id: dict[str, OptionTrade] = {}
    duplicates = 0
    for trade in trades:
        prior = by_id.get(trade.trade_id)
        if prior is None:
            by_id[trade.trade_id] = trade
        elif prior == trade:
            duplicates += 1
        else:
            raise ValueError(f"Deribit raw trade ID conflicts: {trade.trade_id}")
    ordered = sorted(
        by_id.values(), key=lambda value: (value.timestamp_ms, value.trade_id)
    )
    for trade in ordered:
        _update_digest(digest, asdict(trade))
    return len(ordered), duplicates


def _raw_instrument_rows(bundle: Path) -> Iterator[dict[str, object]]:
    path = bundle / "raw" / "instruments.json.gz"
    with open_text_reader(path) as handle:
        content = handle.read().encode("utf-8")
    for instrument in parse_instruments(content):
        yield asdict(instrument)


def _parquet_rows(path: Path) -> Iterator[dict[str, object]]:
    parquet = pq.ParquetFile(path)
    for batch in parquet.iter_batches(batch_size=65_536):
        for value in batch.to_pylist():
            if not isinstance(value, dict):
                raise ValueError(f"Deribit normalized row is not an object: {path}")
            yield value


def _digest_rows(rows: Iterable[Mapping[str, object]]) -> tuple[int, str]:
    digest = sha256()
    count = 0
    for row in rows:
        _update_digest(digest, row)
        count += 1
    return count, digest.hexdigest()


def _update_digest(digest: _DigestProtocol, row: Mapping[str, object]) -> None:
    encoded = json.dumps(
        dict(row), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    digest.update(encoded + b"\n")


def _validate_counts(
    manifest: Mapping[str, object],
    raw: _RawTradeDigest,
    parquet_trades: tuple[int, str],
    parquet_instruments: tuple[int, str],
) -> None:
    coverage = _mapping(manifest, "coverage")
    expected = {
        "trade_rows": raw.rows,
        "instrument_rows": parquet_instruments[0],
        "raw_trade_pages": raw.pages,
        "truncated_pages": raw.truncated_pages,
        "duplicate_trades_removed_within_day": raw.duplicates,
    }
    if any(coverage.get(key) != value for key, value in expected.items()):
        raise ValueError("Deribit raw reproduction counts differ from manifest")
    if parquet_trades[0] != raw.rows:
        raise ValueError("Deribit normalized trade row count differs from raw source")


def _audit(
    bundle: Path,
    raw: _RawTradeDigest,
    parquet_trades: tuple[int, str],
    raw_instruments: tuple[int, str],
    parquet_instruments: tuple[int, str],
) -> DeribitRawReproductionAudit:
    return DeribitRawReproductionAudit(
        bundle=str(bundle.resolve()),
        manifest=file_evidence(bundle / "manifest.json"),
        normalized_trade_rows=parquet_trades[0],
        normalized_instrument_rows=parquet_instruments[0],
        raw_trade_pages=raw.pages,
        truncated_trade_pages=raw.truncated_pages,
        terminal_trade_pages=raw.terminal_pages,
        terminal_window_coverage_complete=raw.terminal_window_coverage_complete,
        duplicate_trades_removed=raw.duplicates,
        raw_trade_rows_sha256=raw.sha256,
        parquet_trade_rows_sha256=parquet_trades[1],
        raw_instrument_rows_sha256=raw_instruments[1],
        parquet_instrument_rows_sha256=parquet_instruments[1],
        trade_rows_match=True,
        instrument_rows_match=True,
        all_registered_files_verified=True,
    )


def _requests(manifest: Mapping[str, object]) -> tuple[dict[str, object], ...]:
    value = manifest.get("requests")
    if not isinstance(value, list) or not value:
        raise ValueError("Deribit option-flow manifest has no request records")
    requests: list[dict[str, object]] = []
    for request in value:
        if not isinstance(request, dict):
            raise ValueError("Deribit option-flow request record is not an object")
        requests.append(request)
    return tuple(requests)


def _mapping(value: Mapping[str, object], key: str) -> dict[str, object]:
    nested = value.get(key)
    if not isinstance(nested, dict):
        raise ValueError(f"Deribit option-flow manifest lacks object: {key}")
    return nested


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"Deribit option-flow {label} is not a nonnegative integer")
    return value

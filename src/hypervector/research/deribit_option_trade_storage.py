"""Streaming immutable storage for Deribit BTC option source evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from hypervector.data.oxa_storage import (
    file_evidence,
    gzip_text_writer,
    publish_immutable_directory,
    write_json,
)
from hypervector.research.deribit_option_trade_acquisition import (
    DAY_MS,
    DERIBIT_INSTRUMENTS_URL,
    OptionTrade,
    PageFetcher,
    TradePage,
    TradeWindow,
    fetch_trade_history,
    parse_instruments,
)


_HYPOTHESIS = "V58_BTC_DERIBIT_OTM_DIRECTIONAL_FLOW_LONG_V1"
_SCHEMA_VERSION = "deribit_btc_option_flow_source_bundle_v1"
_TRADE_SCHEMA = pa.schema(
    [
        ("trade_id", pa.string()),
        ("trade_seq", pa.int64()),
        ("instrument_name", pa.string()),
        ("timestamp_ms", pa.int64()),
        ("direction", pa.string()),
        ("amount", pa.float64()),
        ("price", pa.float64()),
        ("index_price", pa.float64()),
        ("mark_price", pa.float64()),
        ("iv", pa.float64()),
        ("tick_direction", pa.int64()),
        ("block_trade_id", pa.string()),
        ("block_rfq_id", pa.int64()),
        ("combo_id", pa.string()),
        ("combo_trade_id", pa.string()),
    ]
)
_INSTRUMENT_SCHEMA = pa.schema(
    [
        ("instrument_name", pa.string()),
        ("creation_timestamp_ms", pa.int64()),
        ("expiration_timestamp_ms", pa.int64()),
        ("strike", pa.float64()),
        ("option_type", pa.string()),
        ("contract_size", pa.float64()),
    ]
)


@dataclass(frozen=True)
class _TradeWriteSummary:
    rows: int
    raw_pages: int
    truncated_pages: int
    duplicate_trades_removed: int
    requests: tuple[dict[str, object], ...]


def acquire_deribit_option_bundle(
    output: Path,
    fetch_bytes: PageFetcher,
    *,
    window: TradeWindow,
    max_requests_per_day: int,
    context: dict[str, object],
) -> Path:
    """Fetch and atomically publish a source-only Deribit option bundle."""
    bound_context = _validated_context(context)
    _validate_window(window)
    if output.exists():
        raise FileExistsError(f"Deribit option bundle already exists: {output}")

    def writer(staging: Path) -> None:
        _write_bundle(
            staging,
            fetch_bytes,
            window,
            max_requests_per_day,
            bound_context,
        )

    publish_immutable_directory(output, writer)
    return output


def _validated_context(context: dict[str, object]) -> dict[str, object]:
    if context.get("hypothesis_id") != _HYPOTHESIS:
        raise ValueError("Deribit option acquisition hypothesis identity drifted")
    if context.get("execution_authority") != "none":
        raise ValueError("Deribit option acquisition gained execution authority")
    if context.get("candidate_outcomes_inspected_before_acquisition") is not False:
        raise ValueError("Deribit option acquisition context contains outcomes")
    if context.get("live_change_authorized") is not False:
        raise ValueError("Deribit option acquisition context authorizes live change")
    preregistration = context.get("preregistration")
    if not isinstance(preregistration, dict) or not preregistration:
        raise ValueError("Deribit option acquisition lacks preregistration evidence")
    if not isinstance(preregistration.get("sha256"), str):
        raise ValueError("Deribit option acquisition lacks preregistration SHA-256")
    if not isinstance(preregistration.get("bytes"), int):
        raise ValueError("Deribit option acquisition lacks preregistration bytes")
    return dict(context)


def _validate_window(window: TradeWindow) -> None:
    if window.start_ms % DAY_MS or window.end_ms % DAY_MS:
        raise ValueError("Deribit option bundle bounds must be UTC-day aligned")


def _write_bundle(
    staging: Path,
    fetch_bytes: PageFetcher,
    window: TradeWindow,
    max_requests_per_day: int,
    context: dict[str, object],
) -> None:
    raw_trades = staging / "raw" / "trades"
    raw_trades.mkdir(parents=True)
    files: dict[str, dict[str, object]] = {}
    instrument_rows = _write_instruments(staging, fetch_bytes, files)
    summary = _write_trades(
        staging,
        raw_trades,
        fetch_bytes,
        window,
        max_requests_per_day,
        files,
    )
    manifest = _manifest(window, instrument_rows, summary, files, context)
    write_json(staging / "manifest.json", manifest)


def _write_instruments(
    staging: Path,
    fetch_bytes: PageFetcher,
    files: dict[str, dict[str, object]],
) -> int:
    parameters: dict[str, str | int | bool] = {
        "currency": "BTC",
        "kind": "option",
        "expired": "true",
    }
    content = fetch_bytes(DERIBIT_INSTRUMENTS_URL, parameters)
    instruments = parse_instruments(content)
    raw = staging / "raw" / "instruments.json.gz"
    _write_raw(raw, content)
    files["raw/instruments.json.gz"] = file_evidence(raw)
    path = staging / "instruments.parquet"
    pq.write_table(
        pa.Table.from_pylist(
            [asdict(value) for value in instruments], schema=_INSTRUMENT_SCHEMA
        ),
        path,
    )
    files["instruments.parquet"] = file_evidence(path)
    return len(instruments)


def _write_trades(
    staging: Path,
    raw_directory: Path,
    fetch_bytes: PageFetcher,
    window: TradeWindow,
    max_requests_per_day: int,
    files: dict[str, dict[str, object]],
) -> _TradeWriteSummary:
    writer = pq.ParquetWriter(staging / "trades.parquet", _TRADE_SCHEMA)
    seen: set[str] = set()
    requests: list[dict[str, object]] = []
    counts = [0, 0, 0]
    page_number = 0
    try:
        for start in range(window.start_ms, window.end_ms, DAY_MS):
            history = fetch_trade_history(
                fetch_bytes,
                TradeWindow(start, start + DAY_MS),
                max_requests=max_requests_per_day,
            )
            page_number = _write_trade_pages(
                raw_directory, history.pages, page_number, files, requests
            )
            rows = _new_trade_rows(history.trades, seen)
            if rows:
                writer.write_table(pa.Table.from_pylist(rows, schema=_TRADE_SCHEMA))
            counts[0] += len(rows)
            counts[1] += history.truncated_pages
            counts[2] += history.duplicate_trades_removed
    finally:
        writer.close()
    files["trades.parquet"] = file_evidence(staging / "trades.parquet")
    return _TradeWriteSummary(
        counts[0], page_number, counts[1], counts[2], tuple(requests)
    )


def _write_trade_pages(
    raw_directory: Path,
    pages: tuple[TradePage, ...],
    offset: int,
    files: dict[str, dict[str, object]],
    requests: list[dict[str, object]],
) -> int:
    for index, page in enumerate(pages, start=offset + 1):
        relative = f"raw/trades/page_{index:06d}.json.gz"
        path = raw_directory.parent.parent / relative
        _write_raw(path, page.content)
        files[relative] = file_evidence(path)
        requests.append(_request_record(index, page))
    return offset + len(pages)


def _new_trade_rows(
    trades: tuple[OptionTrade, ...],
    seen: set[str],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for value in trades:
        row = asdict(value)
        trade_id = row.get("trade_id")
        if not isinstance(trade_id, str):
            raise ValueError("Deribit normalized trade ID is invalid")
        if trade_id in seen:
            raise ValueError(f"Deribit option trade ID is duplicated: {trade_id}")
        seen.add(trade_id)
        rows.append(row)
    return rows


def _write_raw(path: Path, content: bytes) -> None:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Deribit raw response is not UTF-8") from exc
    with gzip_text_writer(path) as handle:
        handle.write(text)


def _request_record(index: int, page: TradePage) -> dict[str, object]:
    return {
        "page": index,
        "start_timestamp": page.window.start_ms,
        "end_timestamp": page.window.end_ms - 1,
        "rows": len(page.trades),
        "has_more": page.has_more,
        "normalized": not page.has_more,
    }


def _manifest(
    window: TradeWindow,
    instrument_rows: int,
    summary: _TradeWriteSummary,
    files: dict[str, dict[str, object]],
    context: dict[str, object],
) -> dict[str, object]:
    return {
        "schema_version": _SCHEMA_VERSION,
        "source": "deribit_official_btc_option_trades",
        "symbol": "BTC",
        "report_only": True,
        "execution_authority": "none",
        "candidate_outcomes_computed": False,
        "context": context,
        "coverage": {
            "start_timestamp_ms": window.start_ms,
            "end_timestamp_ms_exclusive": window.end_ms,
            "trade_rows": summary.rows,
            "instrument_rows": instrument_rows,
            "raw_trade_pages": summary.raw_pages,
            "truncated_pages": summary.truncated_pages,
            "duplicate_trades_removed_within_day": summary.duplicate_trades_removed,
        },
        "requests": list(summary.requests),
        "files": files,
    }

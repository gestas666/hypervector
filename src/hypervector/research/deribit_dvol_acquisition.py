"""Immutable outcome-blind acquisition of official Deribit BTC DVOL candles."""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import (
    file_evidence,
    publish_immutable_directory,
    write_immutable_parquet,
    write_json,
)


DERIBIT_DVOL_URL = "https://www.deribit.com/api/v2/public/get_volatility_index_data"
START_TIMESTAMP_MS = 1_753_660_800_000
END_TIMESTAMP_MS = 1_785_196_800_000
HOUR_MS = 3_600_000
EXPECTED_ROWS = 8_761
_HYPOTHESIS = "V58_BTC_DVOL_VRP_CONTINUATION_LONG_V1"
_SCHEMA_VERSION = "deribit_btc_dvol_hourly_bundle_v1"
_MAX_PAGES = 100

RequestParameters = Mapping[str, str | int]
PageFetcher = Callable[[str, RequestParameters], bytes]


@dataclass(frozen=True)
class DvolPage:
    """One raw official response and its validated request metadata."""

    content: bytes
    parameters: dict[str, str | int]
    rows: list[list[object]]
    continuation: int | None


def acquire_deribit_dvol_bundle(
    output: Path,
    fetch_bytes: PageFetcher,
    *,
    context: dict[str, object],
) -> Path:
    """Fetch and atomically publish source-only Deribit BTC DVOL evidence."""
    bound_context = _validated_context(context)
    if output.exists():
        raise FileExistsError(f"Deribit DVOL bundle already exists: {output}")

    def writer(staging: Path) -> None:
        pages = _fetch_pages(fetch_bytes)
        frame = _normalized_frame(pages)
        _write_bundle(staging, pages, frame, bound_context)

    publish_immutable_directory(output, writer)
    return output


def _validated_context(context: dict[str, object]) -> dict[str, object]:
    if context.get("hypothesis_id") != _HYPOTHESIS:
        raise ValueError("Deribit DVOL acquisition hypothesis identity drifted")
    if context.get("execution_authority") != "none":
        raise ValueError("Deribit DVOL acquisition gained execution authority")
    if context.get("candidate_results_inspected_before_acquisition") is not False:
        raise ValueError("Deribit DVOL acquisition context contains candidate results")
    preregistration = context.get("preregistration")
    if not isinstance(preregistration, dict) or not preregistration:
        raise ValueError("Deribit DVOL acquisition lacks preregistration evidence")
    return dict(context)


def _fetch_pages(fetch_bytes: PageFetcher) -> list[DvolPage]:
    pages: list[DvolPage] = []
    end_timestamp = END_TIMESTAMP_MS
    while True:
        parameters = _parameters(end_timestamp)
        content = fetch_bytes(DERIBIT_DVOL_URL, parameters)
        rows, continuation = _parse_page(content, len(pages) + 1)
        pages.append(DvolPage(content, parameters, rows, continuation))
        if continuation is None:
            return pages
        _validate_continuation(continuation, end_timestamp, len(pages))
        end_timestamp = continuation
        if len(pages) >= _MAX_PAGES:
            raise ValueError("Deribit DVOL pagination exceeded 100 pages")


def _parameters(end_timestamp: int) -> dict[str, str | int]:
    return {
        "currency": "BTC",
        "start_timestamp": START_TIMESTAMP_MS,
        "end_timestamp": end_timestamp,
        "resolution": "3600",
    }


def _parse_page(
    content: bytes, page_number: int
) -> tuple[list[list[object]], int | None]:
    payload = _decoded_payload(content, page_number)
    if "error" in payload:
        raise ValueError(f"Deribit DVOL page {page_number} returned JSON-RPC error")
    if payload.get("jsonrpc") != "2.0":
        raise ValueError(f"Deribit DVOL page {page_number} JSON-RPC version drifted")
    result = payload.get("result")
    if not isinstance(result, dict):
        raise ValueError(f"Deribit DVOL page {page_number} lacks result object")
    data = result.get("data")
    if not isinstance(data, list):
        raise ValueError(f"Deribit DVOL page {page_number} data is not an array")
    rows = _page_rows(data, page_number)
    continuation = result.get("continuation")
    if continuation is not None and (
        not isinstance(continuation, int) or isinstance(continuation, bool)
    ):
        raise ValueError(f"Deribit DVOL page {page_number} continuation is invalid")
    return rows, continuation


def _decoded_payload(content: bytes, page_number: int) -> dict[str, object]:
    if not isinstance(content, bytes) or not content:
        raise ValueError(f"Deribit DVOL page {page_number} returned no bytes")
    try:
        payload = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"Deribit DVOL page {page_number} is invalid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Deribit DVOL page {page_number} root is not an object")
    return payload


def _page_rows(data: list[object], page_number: int) -> list[list[object]]:
    rows: list[list[object]] = []
    for row_number, value in enumerate(data, start=1):
        if not isinstance(value, list) or len(value) != 5:
            raise ValueError(
                f"Deribit DVOL page {page_number} row {row_number} needs five values"
            )
        rows.append(value)
    return rows


def _validate_continuation(continuation: int, prior_end: int, page_number: int) -> None:
    if continuation >= prior_end:
        raise ValueError(
            f"Deribit DVOL page {page_number} continuation is not backward"
        )
    if continuation < START_TIMESTAMP_MS:
        raise ValueError(
            f"Deribit DVOL page {page_number} continuation precedes frozen start"
        )


def _normalized_frame(pages: list[DvolPage]) -> pd.DataFrame:
    records = [
        _validated_record(row, page_number, row_number)
        for page_number, page in enumerate(pages, start=1)
        for row_number, row in enumerate(page.rows, start=1)
    ]
    frame = pd.DataFrame.from_records(records)
    if frame.empty:
        raise ValueError("Deribit DVOL history contains no rows")
    frame = frame.sort_values("timestamp_ms", kind="stable").reset_index(drop=True)
    _validate_coverage(frame)
    frame["timestamp"] = pd.to_datetime(frame.pop("timestamp_ms"), unit="ms", utc=True)
    return frame[["timestamp", "open", "high", "low", "close"]]


def _validated_record(
    row: list[object],
    page_number: int,
    row_number: int,
) -> dict[str, int | float]:
    timestamp = row[0]
    if not isinstance(timestamp, int) or isinstance(timestamp, bool):
        raise ValueError(
            _row_error(page_number, row_number, "timestamp is not integer")
        )
    if timestamp % HOUR_MS:
        raise ValueError(
            _row_error(page_number, row_number, "timestamp is not hour-aligned")
        )
    values = [_numeric_value(value, page_number, row_number) for value in row[1:]]
    open_value, high, low, close = values
    if high < max(open_value, low, close) or low > min(open_value, high, close):
        raise ValueError(_row_error(page_number, row_number, "OHLC bounds are invalid"))
    return {
        "timestamp_ms": timestamp,
        "open": open_value,
        "high": high,
        "low": low,
        "close": close,
    }


def _numeric_value(value: object, page_number: int, row_number: int) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(_row_error(page_number, row_number, "OHLC is not numeric"))
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError(
            _row_error(page_number, row_number, "OHLC must be finite and positive")
        )
    return number


def _row_error(page_number: int, row_number: int, message: str) -> str:
    return f"Deribit DVOL page {page_number} row {row_number} {message}"


def _validate_coverage(frame: pd.DataFrame) -> None:
    timestamps = frame["timestamp_ms"]
    if timestamps.duplicated().any():
        raise ValueError("Deribit DVOL history contains duplicate timestamps")
    differences = timestamps.diff().dropna()
    if not differences.eq(HOUR_MS).all():
        raise ValueError("Deribit DVOL history lacks exact hourly continuity")
    if (
        timestamps.iloc[0] != START_TIMESTAMP_MS
        or timestamps.iloc[-1] != END_TIMESTAMP_MS
    ):
        raise ValueError("Deribit DVOL history does not match exact bounds")
    if len(frame) != EXPECTED_ROWS:
        raise ValueError(f"Deribit DVOL history needs exactly {EXPECTED_ROWS} rows")


def _write_bundle(
    staging: Path,
    pages: list[DvolPage],
    frame: pd.DataFrame,
    context: dict[str, object],
) -> None:
    raw_directory = staging / "raw"
    raw_directory.mkdir()
    files: dict[str, dict[str, object]] = {}
    requests: list[dict[str, object]] = []
    for index, page in enumerate(pages, start=1):
        relative = f"raw/page_{index:04d}.json"
        path = staging / relative
        path.write_bytes(page.content)
        files[relative] = file_evidence(path)
        requests.append(_request_record(index, page))
    parquet = staging / "dvol.parquet"
    write_immutable_parquet(parquet, frame)
    files["dvol.parquet"] = file_evidence(parquet)
    write_json(staging / "manifest.json", _manifest(frame, files, requests, context))


def _request_record(index: int, page: DvolPage) -> dict[str, object]:
    return {
        "page": index,
        "parameters": page.parameters,
        "rows": len(page.rows),
        "continuation": page.continuation,
    }


def _manifest(
    frame: pd.DataFrame,
    files: dict[str, dict[str, object]],
    requests: list[dict[str, object]],
    context: dict[str, object],
) -> dict[str, object]:
    return {
        "schema_version": _SCHEMA_VERSION,
        "source": "deribit_official_btc_dvol_hourly",
        "source_url": DERIBIT_DVOL_URL,
        "symbol": "BTC",
        "resolution_seconds": 3600,
        "report_only": True,
        "execution_authority": "none",
        "candidate_outcomes_computed": False,
        "context": context,
        "coverage": {
            "rows": len(frame),
            "first_timestamp": frame.iloc[0]["timestamp"].isoformat(),
            "last_timestamp": frame.iloc[-1]["timestamp"].isoformat(),
            "hourly_gaps": 0,
            "duplicate_timestamps": 0,
        },
        "requests": requests,
        "files": files,
    }

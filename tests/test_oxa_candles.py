"""Tests for venue-native 0xArchive candle acquisition."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_candles import (
    OxaCandleClient,
    OxaCandleRequest,
    fetch_candle_history,
    repair_candle_cadence,
    store_candle_history,
)

VALID_PAGE = {
    "success": True,
    "data": [
        {
            "timestamp": "2026-07-26T00:00:00Z",
            "open": 100.0,
            "high": 102.0,
            "low": 99.0,
            "close": 101.0,
            "volume": 4.0,
            "quote_volume": 402.0,
            "trade_count": 7,
        }
    ],
    "meta": {"request_id": "request-1", "next_cursor": None},
}


@dataclass
class FakeResponse:
    status_code: int
    payload: object

    def json(self) -> object:
        return self.payload


class FakeSession:
    """Return deterministic response payloads in request order."""

    def __init__(self, payloads: list[object]) -> None:
        self.payloads = payloads

    def get(self, *_args: object, **_kwargs: object) -> FakeResponse:
        return FakeResponse(200, self.payloads.pop(0))


def _request(*, max_pages: int = 1) -> OxaCandleRequest:
    return OxaCandleRequest(
        "BTC",
        datetime(2026, 7, 26, tzinfo=UTC),
        datetime(2026, 7, 26, 1, tzinfo=UTC),
        "1m",
        10_000,
        max_pages,
    )


def test_candle_pages_normalize_and_deduplicate_boundaries() -> None:
    """Exact cursor-boundary candles become one chronological venue bar."""
    first = copy.deepcopy(VALID_PAGE)
    second = copy.deepcopy(VALID_PAGE)
    first["meta"]["next_cursor"] = "next"  # type: ignore[index]
    second["meta"]["request_id"] = "request-2"  # type: ignore[index]
    result = fetch_candle_history(
        OxaCandleClient(api_key="test", session=FakeSession([first, second])),
        _request(max_pages=2),
    )

    assert result.complete is True
    assert len(result.candles) == 1
    assert result.request_ids == ("request-1", "request-2")


def test_inclusive_vendor_end_candle_is_excluded_from_normalized_window() -> None:
    """Normalized research windows remain half-open despite vendor responses."""
    payload = copy.deepcopy(VALID_PAGE)
    payload["data"][0]["timestamp"] = "2026-07-26T01:00:00Z"  # type: ignore[index]

    result = fetch_candle_history(
        OxaCandleClient(api_key="test", session=FakeSession([payload])), _request()
    )

    assert result.complete is True
    assert result.candles == ()


def test_candle_bundle_is_atomic_auditable_and_cache_ready(tmp_path: Path) -> None:
    """Stored Parquet retains venue bars while raw pages remain checksummed."""
    result = fetch_candle_history(
        OxaCandleClient(
            api_key="test", session=FakeSession([copy.deepcopy(VALID_PAGE)])
        ),
        _request(),
    )

    stored = store_candle_history(tmp_path, _request(), result)
    manifest = json.loads(stored.manifest_path.read_text(encoding="utf-8"))
    bars = pd.read_parquet(stored.candles_path)

    assert manifest["complete"] is True
    assert manifest["files"]["raw/page-0001.json.gz"]["sha256"]
    assert list(bars["source"]) == ["hl"]
    assert bars.iloc[0]["close"] == 101.0


def test_candle_request_rejects_non_utc_or_unsupported_interval() -> None:
    """Candle acquisition remains bounded to canonical venue intervals."""
    start = datetime(2026, 7, 26)
    end = start + timedelta(hours=1)
    try:
        OxaCandleRequest("BTC", start, end, "2m")
    except ValueError as exc:
        assert "UTC" in str(exc) or "interval" in str(exc)
    else:
        raise AssertionError("invalid candle request was accepted")


def test_research_cadence_repairs_missing_minutes_with_labeled_flat_bars() -> None:
    """Missing vendor candles become explicit zero-volume continuity evidence."""
    frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                ["2026-07-26T00:00:00Z", "2026-07-26T00:02:00Z"], utc=True
            ),
            "open": [100.0, 101.0],
            "high": [100.0, 101.0],
            "low": [100.0, 101.0],
            "close": [100.0, 101.0],
            "volume": [1.0, 2.0],
            "source": ["hl", "hl"],
        }
    )

    repaired, fills = repair_candle_cadence(
        frame,
        start=datetime(2026, 7, 26, tzinfo=UTC),
        end=datetime(2026, 7, 26, 0, 3, tzinfo=UTC),
    )

    assert fills == 1
    assert len(repaired) == 3
    assert repaired.iloc[1]["source"] == "hl_gap_fill"
    assert repaired.iloc[1]["open"] == repaired.iloc[1]["close"] == 100.0
    assert repaired.iloc[1]["volume"] == 0.0

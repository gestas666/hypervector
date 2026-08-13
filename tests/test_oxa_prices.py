"""Tests for immutable 0xArchive Hyperliquid price history."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from hypervector.data.oxa_prices import (
    OxaPriceClient,
    OxaPriceRequest,
    fetch_price_history,
    store_price_history,
)

VALID_PAGE = {
    "success": True,
    "data": [
        {
            "timestamp": "2026-07-26T00:00:25.723Z",
            "mark_price": "64356",
            "oracle_price": "64368",
            "mid_price": "64355.5",
        }
    ],
    "meta": {"count": 1, "request_id": "request-1", "next_cursor": None},
}


@dataclass
class FakeResponse:
    status_code: int
    payload: object

    def json(self) -> object:
        return self.payload


class FakeSession:
    """Return deterministic responses while retaining request parameters."""

    def __init__(self, payloads: list[object]) -> None:
        self.payloads = payloads
        self.params: list[dict[str, int | str]] = []
        self.urls: list[str] = []

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        self.urls.append(url)
        self.params.append(dict(kwargs["params"]))
        return FakeResponse(200, self.payloads.pop(0))


def _request(*, max_pages: int = 1) -> OxaPriceRequest:
    return OxaPriceRequest(
        "BTC",
        datetime(2026, 7, 26, tzinfo=UTC),
        datetime(2026, 7, 26, 1, tzinfo=UTC),
        1000,
        max_pages,
    )


def test_price_history_propagates_cursor_and_deduplicates_boundary() -> None:
    first = copy.deepcopy(VALID_PAGE)
    second = copy.deepcopy(VALID_PAGE)
    first["meta"]["next_cursor"] = "1785024085723"  # type: ignore[index]
    second["meta"]["request_id"] = "request-2"  # type: ignore[index]
    second["data"].append(  # type: ignore[union-attr]
        {
            "timestamp": "2026-07-26T00:01:26.313Z",
            "mark_price": "64340",
            "oracle_price": "64360.6",
            "mid_price": None,
        }
    )
    session = FakeSession([first, second])

    result = fetch_price_history(
        OxaPriceClient(api_key="test", session=session),
        _request(max_pages=2),
    )

    assert result.complete is True
    assert len(result.snapshots) == 2
    assert result.snapshots[1].mid_price is None
    assert session.params[1]["cursor"] == "1785024085723"


def test_price_history_rejects_conflicting_duplicate_timestamp() -> None:
    first = copy.deepcopy(VALID_PAGE)
    second = copy.deepcopy(VALID_PAGE)
    first["meta"]["next_cursor"] = "next"  # type: ignore[index]
    second["meta"]["request_id"] = "request-2"  # type: ignore[index]
    second["data"][0]["mark_price"] = "64357"  # type: ignore[index]

    with pytest.raises(ValueError, match="conflicting duplicate"):
        fetch_price_history(
            OxaPriceClient(api_key="test", session=FakeSession([first, second])),
            _request(max_pages=2),
        )


def test_hip3_price_history_uses_namespaced_route_without_rewriting_symbol() -> None:
    session = FakeSession([copy.deepcopy(VALID_PAGE)])
    request = OxaPriceRequest(
        "xyz:MU",
        datetime(2026, 7, 26, tzinfo=UTC),
        datetime(2026, 7, 26, 1, tzinfo=UTC),
        market_family="hip3",
    )

    result = fetch_price_history(
        OxaPriceClient(api_key="test", session=session),
        request,
    )

    assert result.complete is True
    assert session.urls[0].endswith("/v1/hyperliquid/hip3/prices/xyz:MU")


def test_price_bundle_retains_raw_pages_checksums_and_decimal_text(
    tmp_path: Path,
) -> None:
    result = fetch_price_history(
        OxaPriceClient(
            api_key="test", session=FakeSession([copy.deepcopy(VALID_PAGE)])
        ),
        _request(),
    )

    stored = store_price_history(tmp_path, _request(), result)
    manifest = json.loads(stored.manifest_path.read_text(encoding="utf-8"))
    prices = pd.read_parquet(stored.prices_path)

    assert manifest["complete"] is True
    assert manifest["files"]["raw/page-0001.json.gz"]["sha256"]
    assert prices.iloc[0]["mark_price"] == "64356"
    assert prices.iloc[0]["source"] == "0xarchive_hyperliquid_prices"


def test_price_request_rejects_invalid_bounds_and_page_limit() -> None:
    start = datetime(2026, 7, 26, tzinfo=UTC)
    with pytest.raises(ValueError):
        OxaPriceRequest("BTC", start, start, 1000, 1)
    with pytest.raises(ValueError, match="limit"):
        OxaPriceRequest("BTC", start, start.replace(hour=1), 1001, 1)

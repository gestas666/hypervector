"""Bounded, secret-safe 0xArchive Hyperliquid history ingestion tests."""

from __future__ import annotations

import copy
import gzip
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from hypervector.data.oxa_history import (
    OxaBookRequest,
    OxaHistoryClient,
    OxaHistoryError,
)
from hypervector.data.oxa_history import (
    fetch_orderbook_history,
    output_directory,
    store_orderbook_history,
)
from hypervector.data.book_align import load_l2_jsonl


VALID_PAGE: dict[str, object] = {
    "success": True,
    "data": [
        {
            "coin": "BTC",
            "symbol": "BTC",
            "timestamp": "2026-07-26T23:50:00.830Z",
            "bids": [
                {"px": "65370.0", "sz": "14.30759", "n": 42},
                {"px": "65369.0", "sz": "3.47923", "n": 6},
            ],
            "asks": [
                {"px": "65371.0", "sz": "2.00215", "n": 10},
                {"px": "65374.0", "sz": "0.09359", "n": 2},
            ],
            "mid_price": "65370.5",
            "spread": "1.0",
            "spread_bps": "0.15297420090101804",
        }
    ],
    "meta": {
        "count": 1,
        "next_cursor": "1785109800830",
        "request_id": "request-1",
    },
}


@dataclass
class FakeResponse:
    """Minimal requests-like response used at the injected HTTP boundary."""

    payload: dict[str, object]
    status_code: int = 200

    def json(self) -> dict[str, object]:
        """Return the configured JSON response."""
        return self.payload


class FakeSession:
    """Capture one GET request without making a network call."""

    def __init__(self, payload: dict[str, object]) -> None:
        self.response = FakeResponse(payload)
        self.calls: list[dict[str, object]] = []

    def get(
        self,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, int | str],
        timeout: float,
    ) -> FakeResponse:
        """Record explicit request fields and return a static response."""
        self.calls.append(
            {"url": url, "headers": headers, "params": params, "timeout": timeout}
        )
        return self.response


class SequenceSession(FakeSession):
    """Return one configured response per request."""

    def __init__(self, payloads: list[dict[str, object]]) -> None:
        super().__init__(payloads[0])
        self._payloads = iter(payloads)

    def get(
        self,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, int | str],
        timeout: float,
    ) -> FakeResponse:
        """Capture a request and advance the response queue."""
        self.calls.append(
            {"url": url, "headers": headers, "params": params, "timeout": timeout}
        )
        return FakeResponse(next(self._payloads))


class InvalidJsonResponse(FakeResponse):
    """Model a successful HTTP response with an invalid JSON body."""

    def json(self) -> dict[str, object]:
        """Raise the decoder boundary error produced by requests."""
        raise ValueError("invalid JSON body")


def test_client_requires_nonempty_api_key() -> None:
    """The vendor client must fail before making an unauthenticated request."""
    with pytest.raises(ValueError, match="OXA_API_KEY is required"):
        OxaHistoryClient(api_key="")


def test_client_wraps_invalid_json_as_retryable_transport_failure() -> None:
    """Malformed successful responses must be actionable and retryable."""
    session = FakeSession(VALID_PAGE)
    session.response = InvalidJsonResponse(VALID_PAGE)

    with pytest.raises(OxaHistoryError, match="invalid JSON") as raised:
        OxaHistoryClient(api_key="test-key", session=session).fetch_page(
            _valid_request()
        )

    assert raised.value.status_code is None


def test_client_sends_secret_only_in_header_and_preserves_request_id() -> None:
    """Acquisition metadata must retain provenance without leaking credentials."""
    secret = "test-secret-value"
    session = FakeSession(VALID_PAGE)
    request = OxaBookRequest(
        symbol="BTC",
        start=datetime(2026, 7, 26, 23, 50, tzinfo=UTC),
        end=datetime(2026, 7, 26, 23, 51, tzinfo=UTC),
        limit=5,
    )

    page = OxaHistoryClient(api_key=secret, session=session).fetch_page(request)

    call = session.calls[0]
    assert call["url"] == (
        "https://api.0xarchive.io/v1/hyperliquid/orderbook/BTC/history"
    )
    assert call["headers"] == {"X-API-Key": secret}
    assert call["params"] == {
        "start": 1_785_109_800_000,
        "end": 1_785_109_860_000,
        "depth": 20,
        "limit": 5,
    }
    assert page.request_id == "request-1"
    assert secret not in repr(page)


def test_valid_page_preserves_raw_decimals_and_loads_as_replay_jsonl(
    tmp_path: Path,
) -> None:
    """Normalized rows retain native levels and satisfy the existing loader."""
    session = FakeSession(copy.deepcopy(VALID_PAGE))
    request = _valid_request(depth=2)

    page = OxaHistoryClient(api_key="test-key", session=session).fetch_page(request)
    row = page.snapshots[0].to_replay_row(request_id=page.request_id)
    output = tmp_path / "books.jsonl"
    output.write_text(json.dumps(row) + "\n", encoding="utf-8")

    raw_level = page.raw_payload["data"][0]["bids"][0]  # type: ignore[index]
    assert raw_level["px"] == "65370.0"
    assert row["bids"][0] == {"px": "65370.0", "sz": "14.30759", "n": 42}
    assert row["ts_exchange_ms"] == 1_785_109_800_830
    assert row["source"] == "0xarchive_hyperliquid_native_l2"
    assert "ts_recv_ms" not in row
    loaded = load_l2_jsonl(output)
    assert loaded.iloc[0]["best_bid"] == 65370.0
    assert loaded.iloc[0]["best_ask"] == 65371.0


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda row: row.update(timestamp="not-a-time"), "timestamp"),
        (
            lambda row: row.update(timestamp="2026-07-26T23:49:59Z"),
            "outside requested",
        ),
        (lambda row: row.update(symbol="ETH"), "symbol"),
        (lambda row: row.update(bids=[]), "empty"),
        (
            lambda row: row["asks"][0].update(px="65369.0"),
            "crossed",
        ),
        (lambda row: row["bids"][0].update(px="0"), "positive"),
        (lambda row: row["asks"][0].update(sz="-1"), "positive"),
        (lambda row: row["bids"][0].update(n=-1), "order count"),
        (lambda row: row.update(bids=row["bids"] * 11), "depth"),
        (lambda row: row["bids"].reverse(), "descending"),
        (lambda row: row["asks"].reverse(), "ascending"),
    ],
)
def test_snapshot_validation_rejects_invalid_native_books(
    mutation: object,
    message: str,
) -> None:
    """Invalid native L2 evidence must fail instead of producing replay data."""
    payload = copy.deepcopy(VALID_PAGE)
    row = payload["data"][0]  # type: ignore[index]
    mutation(row)  # type: ignore[operator]
    session = FakeSession(payload)

    with pytest.raises(ValueError, match=message):
        OxaHistoryClient(api_key="test-key", session=session).fetch_page(
            _valid_request()
        )


def test_same_millisecond_updates_coalesce_to_last_vendor_state() -> None:
    """Sub-millisecond updates use the last ordered state without false timing."""
    payload = copy.deepcopy(VALID_PAGE)
    duplicate = copy.deepcopy(payload["data"][0])  # type: ignore[index]
    duplicate["bids"][0]["sz"] = "99.0"  # type: ignore[index]
    payload["data"].append(duplicate)  # type: ignore[union-attr]

    page = OxaHistoryClient(
        api_key="test-key", session=FakeSession(payload)
    ).fetch_page(_valid_request())

    assert len(page.snapshots) == 1
    assert page.snapshots[0].bids[0].sz == "99.0"
    assert page.coalesced_same_ms == 1


def test_missing_request_id_is_rejected() -> None:
    """Every accepted page must retain the vendor correlation identifier."""
    payload = copy.deepcopy(VALID_PAGE)
    del payload["meta"]["request_id"]  # type: ignore[index]

    with pytest.raises(ValueError, match="request_id"):
        OxaHistoryClient(api_key="test-key", session=FakeSession(payload)).fetch_page(
            _valid_request()
        )


def test_pagination_passes_only_vendor_cursor_and_completes() -> None:
    """Pagination retains fixed bounds and follows only the returned cursor."""
    first = copy.deepcopy(VALID_PAGE)
    second = copy.deepcopy(VALID_PAGE)
    first["meta"]["next_cursor"] = "cursor-2"  # type: ignore[index]
    second["meta"]["next_cursor"] = None  # type: ignore[index]
    second["meta"]["request_id"] = "request-2"  # type: ignore[index]
    second["data"] = []
    session = SequenceSession([first, second])
    request = _valid_request(max_pages=2)

    result = fetch_orderbook_history(
        OxaHistoryClient(api_key="test-key", session=session), request
    )

    assert len(session.calls) == 2
    expected = request.params()
    assert session.calls[0]["params"] == expected
    assert session.calls[1]["params"] == {**expected, "cursor": "cursor-2"}
    assert result.complete is True
    assert result.continuation_cursor is None
    assert result.request_ids == ("request-1", "request-2")


def test_pagination_exposes_cursor_when_intentionally_bounded() -> None:
    """A page cap must report truncation instead of claiming full coverage."""
    first = copy.deepcopy(VALID_PAGE)
    first["meta"]["next_cursor"] = "still-more"  # type: ignore[index]

    result = fetch_orderbook_history(
        OxaHistoryClient(api_key="test-key", session=SequenceSession([first])),
        _valid_request(max_pages=1),
    )

    assert result.complete is False
    assert result.continuation_cursor == "still-more"


def test_normalized_rows_retain_their_originating_page_request_id(
    tmp_path: Path,
) -> None:
    """Per-row provenance must identify its actual vendor response page."""
    first = copy.deepcopy(VALID_PAGE)
    second = copy.deepcopy(VALID_PAGE)
    first["meta"]["next_cursor"] = "cursor-2"  # type: ignore[index]
    second["meta"]["next_cursor"] = None  # type: ignore[index]
    second["meta"]["request_id"] = "request-2"  # type: ignore[index]
    second["data"][0]["timestamp"] = "2026-07-26T23:50:01Z"  # type: ignore[index]
    request = _valid_request(depth=2, max_pages=2)
    result = fetch_orderbook_history(
        OxaHistoryClient(api_key="test-key", session=SequenceSession([first, second])),
        request,
    )

    stored = store_orderbook_history(tmp_path, request, result)
    with gzip.open(stored.books_path, "rt", encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle]

    assert [row["vendor_request_id"] for row in rows] == [
        "request-1",
        "request-2",
    ]


def test_storage_is_atomic_auditable_and_does_not_overwrite(tmp_path: Path) -> None:
    """Validated evidence publishes once with checksums and replay JSONL."""
    request = _valid_request(depth=2)
    result = fetch_orderbook_history(
        OxaHistoryClient(
            api_key="test-key", session=SequenceSession([copy.deepcopy(VALID_PAGE)])
        ),
        request,
    )

    stored = store_orderbook_history(tmp_path, request, result)

    assert stored.directory == output_directory(tmp_path, request)
    assert stored.books_path.is_file()
    assert stored.manifest_path.is_file()
    manifest = json.loads(stored.manifest_path.read_text(encoding="utf-8"))
    assert manifest["source"] == "0xarchive_hyperliquid_native_l2"
    assert manifest["request_ids"] == ["request-1"]
    assert manifest["row_count"] == 1
    assert stored.books_path.name == "books.jsonl.gz"
    assert manifest["files"]["raw/page-0001.json.gz"]["sha256"]
    assert load_l2_jsonl(stored.books_path).shape[0] == 1
    with pytest.raises(FileExistsError, match="already exists"):
        store_orderbook_history(tmp_path, request, result)


def test_invalid_later_page_does_not_publish_partial_directory(tmp_path: Path) -> None:
    """A validation failure must leave no success-shaped output directory."""
    first = copy.deepcopy(VALID_PAGE)
    second = copy.deepcopy(VALID_PAGE)
    first["meta"]["next_cursor"] = "cursor-2"  # type: ignore[index]
    second["data"][0]["asks"] = []  # type: ignore[index]
    request = _valid_request(max_pages=2)

    with pytest.raises(ValueError, match="empty"):
        result = fetch_orderbook_history(
            OxaHistoryClient(
                api_key="test-key", session=SequenceSession([first, second])
            ),
            request,
        )
        store_orderbook_history(tmp_path, request, result)

    assert not output_directory(tmp_path, request).exists()


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"symbol": "../BTC"}, "symbol"),
        ({"depth": 21}, "depth"),
        ({"limit": 0}, "limit"),
        ({"max_pages": 0}, "max_pages"),
        ({"end": datetime(2026, 7, 26, tzinfo=UTC)}, "after start"),
        (
            {"start": datetime(2026, 7, 26, tzinfo=timezone(timedelta(hours=-4)))},
            "UTC",
        ),
    ],
)
def test_request_rejects_unsafe_or_unbounded_inputs(
    changes: dict[str, object],
    message: str,
) -> None:
    """Every historical query must have a valid explicit bound."""
    values: dict[str, object] = {
        "symbol": "BTC",
        "start": datetime(2026, 7, 26, 23, 50, tzinfo=UTC),
        "end": datetime(2026, 7, 26, 23, 51, tzinfo=UTC),
        "depth": 20,
        "limit": 1000,
        "max_pages": 1,
    }
    values.update(changes)

    with pytest.raises(ValueError, match=message):
        OxaBookRequest(**values)  # type: ignore[arg-type]


def _valid_request(*, depth: int = 20, max_pages: int = 1) -> OxaBookRequest:
    return OxaBookRequest(
        symbol="BTC",
        start=datetime(2026, 7, 26, 23, 50, tzinfo=UTC),
        end=datetime(2026, 7, 26, 23, 51, tzinfo=UTC),
        depth=depth,
        limit=5,
        max_pages=max_pages,
    )

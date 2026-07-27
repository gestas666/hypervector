"""Bounded 0xArchive Hyperliquid public-trade ingestion tests."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from hypervector.data.oxa_trades import (
    OxaTradeClient,
    OxaTradeRequest,
    fetch_trade_history,
    load_trade_jsonl,
    store_trade_history,
    trade_output_directory,
)


VALID_PAGE: dict[str, object] = {
    "success": True,
    "data": [
        {
            "symbol": "BTC",
            "coin": "BTC",
            "side": "B",
            "price": "65370",
            "size": "0.00133",
            "timestamp": "2026-07-26T23:50:00Z",
            "tx_hash": "0x0",
            "trade_id": 39_747_663_698_056,
            "order_id": 503_112_194_289,
            "crossed": False,
            "fee": "-0.002608",
            "fee_token": "USDC",
            "direction": "Open Long",
        },
        {
            "symbol": "BTC",
            "coin": "BTC",
            "side": "A",
            "price": "65370",
            "size": "0.00133",
            "timestamp": "2026-07-26T23:50:00Z",
            "tx_hash": "0x0",
            "trade_id": 39_747_663_698_056,
            "order_id": 503_112_237_811,
            "crossed": True,
            "fee": "0.039123",
            "fee_token": "USDC",
            "direction": "Open Short",
        },
    ],
    "meta": {"count": 2, "next_cursor": None, "request_id": "request-1"},
}


@dataclass
class FakeResponse:
    """Minimal response used at the injected REST boundary."""

    payload: dict[str, object]
    status_code: int = 200

    def json(self) -> dict[str, object]:
        """Return the configured payload."""
        return self.payload


class FakeSession:
    """Capture REST calls and return queued response envelopes."""

    def __init__(self, payloads: list[dict[str, object]]) -> None:
        self._payloads = iter(payloads)
        self.calls: list[dict[str, object]] = []

    def get(
        self,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, int | str],
        timeout: float,
    ) -> FakeResponse:
        """Record one call and return the next envelope."""
        self.calls.append(
            {"url": url, "headers": headers, "params": params, "timeout": timeout}
        )
        return FakeResponse(next(self._payloads))


def test_trade_client_is_bounded_authenticated_and_secret_safe() -> None:
    """Trade history must use explicit bounds and header-only authentication."""
    secret = "test-secret-value"
    session = FakeSession([copy.deepcopy(VALID_PAGE)])
    request = _request(limit=5)

    page = OxaTradeClient(api_key=secret, session=session).fetch_page(request)

    assert session.calls == [
        {
            "url": "https://api.0xarchive.io/v1/hyperliquid/trades/BTC",
            "headers": {"X-API-Key": secret},
            "params": {
                "start": 1_785_109_800_000,
                "end": 1_785_109_860_000,
                "limit": 5,
            },
            "timeout": 30.0,
        }
    ]
    assert page.request_id == "request-1"
    assert secret not in repr(page)


def test_recent_participant_fills_normalize_to_one_taker_trade() -> None:
    """Maker and taker participant rows must not double-count one match."""
    result = fetch_trade_history(
        OxaTradeClient(
            api_key="test-key",
            session=FakeSession([copy.deepcopy(VALID_PAGE)]),
        ),
        _request(),
    )

    assert len(result.pages[0].fills) == 2
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.trade_id == 39_747_663_698_056
    assert trade.aggressor_side == "sell"
    assert trade.price == "65370"
    assert trade.size == "0.00133"
    row = trade.to_replay_row()
    assert row["vendor_request_id"] == "request-1"
    assert "received_ts_ns" not in row
    assert "fee" not in row
    raw = result.pages[0].raw_payload["data"]  # type: ignore[index]
    assert raw[0]["fee"] == "-0.002608"
    assert raw[1]["fee"] == "0.039123"


def test_cross_page_participant_rows_normalize_after_pagination() -> None:
    """A page boundary between maker and taker rows must not lose the match."""
    first = copy.deepcopy(VALID_PAGE)
    second = copy.deepcopy(VALID_PAGE)
    first["data"] = [first["data"][0]]  # type: ignore[index]
    first["meta"]["next_cursor"] = "cursor-2"  # type: ignore[index]
    second["data"] = [second["data"][1]]  # type: ignore[index]
    second["meta"]["request_id"] = "request-2"  # type: ignore[index]
    session = FakeSession([first, second])
    request = _request(max_pages=2)

    result = fetch_trade_history(
        OxaTradeClient(api_key="test-key", session=session), request
    )

    expected = request.params()
    assert session.calls[1]["params"] == {**expected, "cursor": "cursor-2"}
    assert result.complete is True
    assert len(result.trades) == 1
    assert result.trades[0].request_id == "request-2"


def test_bounded_page_reports_unresolved_participant_group() -> None:
    """A truncated maker-only group must remain explicit rather than guessed."""
    first = copy.deepcopy(VALID_PAGE)
    first["data"] = [first["data"][0]]  # type: ignore[index]
    first["meta"]["next_cursor"] = "still-more"  # type: ignore[index]

    result = fetch_trade_history(
        OxaTradeClient(api_key="test-key", session=FakeSession([first])),
        _request(max_pages=1),
    )

    assert result.complete is False
    assert result.continuation_cursor == "still-more"
    assert result.trades == ()
    assert result.unresolved_fill_groups == 1


def test_sole_legacy_fill_is_accepted_without_inventing_a_counterparty() -> None:
    """An unmarked sole legacy fill can represent its documented taker-only era."""
    payload = copy.deepcopy(VALID_PAGE)
    payload["data"] = [payload["data"][1]]  # type: ignore[index]
    payload["data"][0]["crossed"] = None  # type: ignore[index]

    result = fetch_trade_history(
        OxaTradeClient(api_key="test-key", session=FakeSession([payload])),
        _request(),
    )

    assert len(result.trades) == 1
    assert result.trades[0].aggressor_side == "sell"


def test_conflicting_participant_fill_identity_is_rejected() -> None:
    """Both sides of a match must agree on timestamp, price, and size."""
    payload = copy.deepcopy(VALID_PAGE)
    payload["data"][1]["price"] = "65371"  # type: ignore[index]

    with pytest.raises(ValueError, match="conflicting participant"):
        fetch_trade_history(
            OxaTradeClient(api_key="test-key", session=FakeSession([payload])),
            _request(),
        )


def test_trade_storage_is_atomic_auditable_and_replay_loadable(
    tmp_path: Path,
) -> None:
    """Validated participant evidence publishes once with normalized matches."""
    request = _request()
    result = fetch_trade_history(
        OxaTradeClient(
            api_key="test-key",
            session=FakeSession([copy.deepcopy(VALID_PAGE)]),
        ),
        request,
    )

    stored = store_trade_history(tmp_path, request, result)

    assert stored.directory == trade_output_directory(tmp_path, request)
    assert stored.trades_path.is_file()
    manifest = json.loads(stored.manifest_path.read_text(encoding="utf-8"))
    assert manifest["raw_fill_count"] == 2
    assert manifest["trade_count"] == 1
    assert manifest["request_ids"] == ["request-1"]
    assert stored.trades_path.name == "trades.jsonl.gz"
    assert manifest["files"]["raw/page-0001.json.gz"]["sha256"]
    loaded = load_trade_jsonl(stored.trades_path)
    assert loaded.iloc[0]["aggressor_side"] == "sell"
    assert loaded.iloc[0]["price"] == 65370.0
    with pytest.raises(FileExistsError, match="already exists"):
        store_trade_history(tmp_path, request, result)


def test_missing_trade_request_id_is_rejected() -> None:
    """Every participant page must retain vendor support provenance."""
    payload = copy.deepcopy(VALID_PAGE)
    del payload["meta"]["request_id"]  # type: ignore[index]

    with pytest.raises(ValueError, match="request_id"):
        OxaTradeClient(api_key="test-key", session=FakeSession([payload])).fetch_page(
            _request()
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("symbol", "ETH", "symbol"),
        ("side", "X", "side"),
        ("price", "0", "positive"),
        ("size", "-1", "positive"),
        ("trade_id", None, "trade_id"),
        ("crossed", "yes", "crossed"),
        ("timestamp", "2026-07-26T23:49:59Z", "outside requested"),
    ],
)
def test_trade_fill_validation_rejects_invalid_rows(
    field: str,
    value: object,
    message: str,
) -> None:
    """Malformed participant fills must fail instead of producing trades."""
    payload = copy.deepcopy(VALID_PAGE)
    payload["data"][0][field] = value  # type: ignore[index]

    with pytest.raises(ValueError, match=message):
        OxaTradeClient(api_key="test-key", session=FakeSession([payload])).fetch_page(
            _request()
        )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"symbol": "../BTC"}, "symbol"),
        ({"limit": 0}, "limit"),
        ({"max_pages": 0}, "max_pages"),
        ({"end": datetime(2026, 7, 26, tzinfo=UTC)}, "after start"),
        (
            {"start": datetime(2026, 7, 26, tzinfo=timezone(timedelta(hours=-4)))},
            "UTC",
        ),
    ],
)
def test_trade_request_rejects_unsafe_or_unbounded_inputs(
    changes: dict[str, object],
    message: str,
) -> None:
    """Every trade query must retain valid explicit bounds."""
    values: dict[str, object] = {
        "symbol": "BTC",
        "start": datetime(2026, 7, 26, 23, 50, tzinfo=UTC),
        "end": datetime(2026, 7, 26, 23, 51, tzinfo=UTC),
        "limit": 1000,
        "max_pages": 1,
    }
    values.update(changes)

    with pytest.raises(ValueError, match=message):
        OxaTradeRequest(**values)  # type: ignore[arg-type]


def _request(*, limit: int = 1000, max_pages: int = 1) -> OxaTradeRequest:
    return OxaTradeRequest(
        symbol="BTC",
        start=datetime(2026, 7, 26, 23, 50, tzinfo=UTC),
        end=datetime(2026, 7, 26, 23, 51, tzinfo=UTC),
        limit=limit,
        max_pages=max_pages,
    )

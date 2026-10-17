"""Bounded 0xArchive Hyperliquid liquidation acquisition tests."""

from __future__ import annotations

import copy
import gzip
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest


VALID_PAGE: dict[str, object] = {
    "success": True,
    "data": [
        {
            "symbol": "BTC",
            "coin": "BTC",
            "timestamp": "2026-08-21T12:00:00.123Z",
            "liquidated_user": "0x1111111111111111111111111111111111111111",
            "liquidator_user": "0x2222222222222222222222222222222222222222",
            "price": "77800.5",
            "size": "0.75",
            "side": "B",
            "mark_price": "77795.0",
            "closed_pnl": "-1250.50",
            "direction": "Close Short",
            "trade_id": 12_345,
            "tx_hash": "0xabc",
        }
    ],
    "meta": {
        "count": 1,
        "next_cursor": None,
        "request_id": "liquidations-request-1",
    },
}


@dataclass
class FakeResponse:
    """Minimal injected HTTP response."""

    payload: dict[str, object]
    status_code: int = 200

    def json(self) -> dict[str, object]:
        """Return the configured payload."""
        return self.payload


class FakeSession:
    """Capture REST calls and return queued liquidation pages."""

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


def test_liquidation_client_uses_bounded_secret_safe_route() -> None:
    """The liquidation label source must use bounded header-authenticated GET."""
    from hypervector.data.oxa_liquidations import (
        OxaLiquidationClient,
        OxaLiquidationRequest,
    )

    secret = "configured-test-secret"
    session = FakeSession([copy.deepcopy(VALID_PAGE)])
    request = OxaLiquidationRequest(
        symbol="BTC",
        start=datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
        end=datetime(2026, 8, 21, 12, 1, tzinfo=UTC),
        limit=5,
    )

    page = OxaLiquidationClient(api_key=secret, session=session).fetch_page(request)

    assert session.calls == [
        {
            "url": "https://api.0xarchive.io/v1/hyperliquid/liquidations/BTC",
            "headers": {"X-API-Key": secret},
            "params": {
                "start": 1_787_313_600_000,
                "end": 1_787_313_660_000,
                "limit": 5,
            },
            "timeout": 30.0,
        }
    ]
    assert page.events[0].direction == "Close Short"
    assert page.events[0].notional_usd == "58350.375"
    assert secret not in repr(page)


def test_historical_empty_liquidator_address_is_preserved_as_missing() -> None:
    """Older labels without a liquidator address must remain usable and explicit."""
    from hypervector.data.oxa_liquidations import (
        OxaLiquidationRequest,
        parse_liquidation_page,
    )

    payload = copy.deepcopy(VALID_PAGE)
    payload["data"][0]["liquidator_user"] = ""  # type: ignore[index]
    request = OxaLiquidationRequest(
        "BTC",
        datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
        datetime(2026, 8, 21, 12, 1, tzinfo=UTC),
    )

    event = parse_liquidation_page(payload, request).events[0]

    assert event.liquidator_user is None
    assert event.to_row()["liquidator_user"] is None


def test_observed_cross_margin_liquidation_direction_is_explicitly_normalized() -> None:
    """The observed cross-margin display string must map without losing provenance."""
    from hypervector.data.oxa_liquidations import (
        OxaLiquidationRequest,
        parse_liquidation_page,
    )

    payload = copy.deepcopy(VALID_PAGE)
    payload["data"][0]["direction"] = "Liquidated Cross Long"  # type: ignore[index]
    payload["data"][0]["side"] = "A"  # type: ignore[index]
    request = OxaLiquidationRequest(
        "BTC",
        datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
        datetime(2026, 8, 21, 12, 1, tzinfo=UTC),
    )

    row = parse_liquidation_page(payload, request).events[0].to_row()

    assert row["liquidated_direction"] == "long"
    assert row["vendor_direction"] == "Liquidated Cross Long"


def test_liquidation_direction_must_match_forced_trade_side() -> None:
    """A contradictory vendor direction and trade side must fail closed."""
    from hypervector.data.oxa_liquidations import (
        OxaLiquidationRequest,
        parse_liquidation_page,
    )

    payload = copy.deepcopy(VALID_PAGE)
    payload["data"][0]["direction"] = "Close Long"  # type: ignore[index]
    payload["data"][0]["side"] = "B"  # type: ignore[index]
    request = OxaLiquidationRequest(
        "BTC",
        datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
        datetime(2026, 8, 21, 12, 1, tzinfo=UTC),
    )

    with pytest.raises(ValueError, match="direction and side disagree"):
        parse_liquidation_page(payload, request)


@pytest.mark.parametrize(
    "vendor_direction",
    ["Liquidated Cross Short", "Liquidated Isolated Short"],
)
def test_observed_august_short_direction_variants_are_normalized(
    vendor_direction: str,
) -> None:
    """Observed forced-short variants must remain explicit and side-checked."""
    from hypervector.data.oxa_liquidations import (
        OxaLiquidationRequest,
        parse_liquidation_page,
    )

    payload = copy.deepcopy(VALID_PAGE)
    payload["data"][0]["direction"] = vendor_direction  # type: ignore[index]
    request = OxaLiquidationRequest(
        "BTC",
        datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
        datetime(2026, 8, 21, 12, 1, tzinfo=UTC),
    )

    row = parse_liquidation_page(payload, request).events[0].to_row()
    assert row["liquidated_direction"] == "short"
    assert row["vendor_direction"] == vendor_direction


@pytest.mark.parametrize(
    "vendor_direction",
    ["Liquidated Cross Long", "Liquidated Isolated Long"],
)
def test_long_direction_variants_symmetric_with_observed_shorts_are_normalized(
    vendor_direction: str,
) -> None:
    """Forced-long variants (sold on side A) must parse, not abort the fetch."""
    from hypervector.data.oxa_liquidations import (
        OxaLiquidationRequest,
        parse_liquidation_page,
    )

    payload = copy.deepcopy(VALID_PAGE)
    payload["data"][0]["direction"] = vendor_direction  # type: ignore[index]
    payload["data"][0]["side"] = "A"  # type: ignore[index]
    request = OxaLiquidationRequest(
        "BTC",
        datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
        datetime(2026, 8, 21, 12, 1, tzinfo=UTC),
    )

    row = parse_liquidation_page(payload, request).events[0].to_row()
    assert row["liquidated_direction"] == "long"
    assert row["vendor_direction"] == vendor_direction
    assert row["exchange_side"] == "A"

    payload["data"][0]["side"] = "B"  # type: ignore[index]
    with pytest.raises(ValueError, match="direction and side disagree"):
        parse_liquidation_page(payload, request)


def test_liquidation_history_follows_bounded_cursor_pages() -> None:
    """Pagination must stop at max-pages and expose an unfinished cursor."""
    from hypervector.data.oxa_liquidations import (
        OxaLiquidationClient,
        OxaLiquidationRequest,
        fetch_liquidation_history,
    )

    first = copy.deepcopy(VALID_PAGE)
    second = copy.deepcopy(VALID_PAGE)
    first["meta"]["next_cursor"] = "1787313600123_12345"  # type: ignore[index]
    second["meta"]["request_id"] = "liquidations-request-2"  # type: ignore[index]
    second["meta"]["next_cursor"] = "1787313600123_12346"  # type: ignore[index]
    second["data"][0]["trade_id"] = 12_346  # type: ignore[index]
    session = FakeSession([first, second])
    request = OxaLiquidationRequest(
        symbol="BTC",
        start=datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
        end=datetime(2026, 8, 21, 12, 1, tzinfo=UTC),
        limit=5,
        max_pages=2,
    )

    result = fetch_liquidation_history(
        OxaLiquidationClient(api_key="test", session=session), request
    )

    assert session.calls[1]["params"]["cursor"] == "1787313600123_12345"
    assert result.request_ids == (
        "liquidations-request-1",
        "liquidations-request-2",
    )
    assert result.complete is False
    assert result.continuation_cursor == "1787313600123_12346"
    assert [event.trade_id for event in result.events] == [12_345, 12_346]


def test_liquidation_history_deduplicates_overlapping_cursor_boundary() -> None:
    """An event repeated across adjacent pages must not inflate forced flow."""
    from hypervector.data.oxa_liquidations import (
        OxaLiquidationClient,
        OxaLiquidationRequest,
        fetch_liquidation_history,
    )

    first = copy.deepcopy(VALID_PAGE)
    second = copy.deepcopy(VALID_PAGE)
    first["meta"]["next_cursor"] = "1787313600123_12345"  # type: ignore[index]
    second["meta"]["request_id"] = "liquidations-request-2"  # type: ignore[index]
    session = FakeSession([first, second])
    request = OxaLiquidationRequest(
        "BTC",
        datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
        datetime(2026, 8, 21, 12, 1, tzinfo=UTC),
        max_pages=2,
    )

    result = fetch_liquidation_history(
        OxaLiquidationClient(api_key="test", session=session), request
    )

    assert len(result.events) == 1
    assert result.events[0].trade_id == 12_345


def test_liquidation_history_rejects_nonadvancing_cursor() -> None:
    """A repeated vendor cursor must fail instead of claiming bounded progress."""
    from hypervector.data.oxa_liquidations import (
        OxaLiquidationClient,
        OxaLiquidationRequest,
        fetch_liquidation_history,
    )

    first = copy.deepcopy(VALID_PAGE)
    second = copy.deepcopy(VALID_PAGE)
    for payload in (first, second):
        payload["meta"]["next_cursor"] = "same-cursor"  # type: ignore[index]
    request = OxaLiquidationRequest(
        "BTC",
        datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
        datetime(2026, 8, 21, 12, 1, tzinfo=UTC),
        max_pages=2,
    )

    with pytest.raises(ValueError, match="cursor did not advance"):
        fetch_liquidation_history(
            OxaLiquidationClient(api_key="test", session=FakeSession([first, second])),
            request,
        )


def test_liquidation_storage_is_immutable_and_auditable(tmp_path: Path) -> None:
    """Raw pages and normalized labels must publish with hashed provenance."""
    from hypervector.data.oxa_liquidations import (
        OxaLiquidationClient,
        OxaLiquidationRequest,
        fetch_liquidation_history,
        liquidation_output_directory,
        store_liquidation_history,
    )

    request = OxaLiquidationRequest(
        "BTC",
        datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
        datetime(2026, 8, 21, 12, 1, tzinfo=UTC),
    )
    result = fetch_liquidation_history(
        OxaLiquidationClient(
            api_key="test", session=FakeSession([copy.deepcopy(VALID_PAGE)])
        ),
        request,
    )

    stored = store_liquidation_history(tmp_path, request, result)

    assert stored.directory == liquidation_output_directory(tmp_path, request)
    assert stored.directory.name.endswith("_liquidations_v2")
    manifest = json.loads(stored.manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 2
    assert manifest["normalization_version"] == "explicit_vendor_direction_v2"
    assert manifest["source"] == "0xarchive_hyperliquid_liquidations"
    assert manifest["event_count"] == 1
    assert manifest["complete"] is True
    assert manifest["request_ids"] == ["liquidations-request-1"]
    assert manifest["files"]["raw/page-0001.json.gz"]["sha256"]
    assert manifest["files"]["liquidations.jsonl.gz"]["sha256"]
    with gzip.open(stored.events_path, "rt", encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle]
    assert rows[0]["liquidated_direction"] == "short"
    assert rows[0]["vendor_direction"] == "Close Short"
    assert rows[0]["normalization_version"] == "explicit_vendor_direction_v2"
    assert rows[0]["notional_usd"] == "58350.375"
    assert rows[0]["source"] == "0xarchive_hyperliquid_liquidations"
    with pytest.raises(FileExistsError, match="already exists"):
        store_liquidation_history(tmp_path, request, result)

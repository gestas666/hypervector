"""HIP-3-specific 0xArchive L2 acquisition contracts."""

from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from hypervector.data.oxa_archive_audit import (
    OxaArchiveAuditConfig,
    audit_oxa_archive,
)
from hypervector.data.oxa_backfill import OxaBackfillConfig, iter_backfill_tasks
from hypervector.data.oxa_history import (
    OxaBookRequest,
    OxaHistoryClient,
    fetch_orderbook_history,
    output_directory,
    store_orderbook_history,
)


@dataclass
class _Response:
    payload: dict[str, object]
    status_code: int = 200

    def json(self) -> dict[str, object]:
        """Return the configured HIP-3 response."""
        return self.payload


class _Session:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls: list[dict[str, object]] = []

    def get(
        self,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, int | str],
        timeout: float,
    ) -> _Response:
        """Capture the route without making a network request."""
        self.calls.append(
            {"url": url, "headers": headers, "params": params, "timeout": timeout}
        )
        return _Response(self.payload)


def test_hip3_book_uses_distinct_route_storage_and_provenance(tmp_path: Path) -> None:
    """Namespaced books must never be flattened into the core-perp family."""
    request = _request()
    session = _Session(_page())

    result = fetch_orderbook_history(
        OxaHistoryClient(api_key="secret", session=session), request
    )
    stored = store_orderbook_history(tmp_path, request, result)

    assert session.calls[0]["url"] == (
        "https://api.0xarchive.io/v1/hyperliquid/hip3/orderbook/xyz:SP500/history"
    )
    assert stored.directory == output_directory(tmp_path, request)
    assert "/hyperliquid/hip3/xyz:SP500/" in str(stored.directory)
    manifest = json.loads(stored.manifest_path.read_text(encoding="utf-8"))
    assert manifest["market_family"] == "hip3"
    assert manifest["source"] == "0xarchive_hyperliquid_hip3_l2"
    assert "/hip3/orderbook/{symbol}/history" in manifest["source_api"]
    with gzip.open(stored.books_path, "rt", encoding="utf-8") as handle:
        row = json.loads(next(handle))
    assert row["symbol"] == "xyz:SP500"
    assert row["source"] == "0xarchive_hyperliquid_hip3_l2"


def test_hip3_backfill_is_explicitly_book_only(tmp_path: Path) -> None:
    """HIP-3 mode must not route trades or prices through core endpoints."""
    config = OxaBackfillConfig(
        symbol="xyz:SPCX",
        start=datetime(2026, 8, 6, 14, tzinfo=UTC),
        end=datetime(2026, 8, 6, 16, tzinfo=UTC),
        data_root=tmp_path,
        chunk=timedelta(hours=1),
        market_family="hip3",
        book_only=True,
    )

    tasks = tuple(iter_backfill_tasks(config))

    assert [(task.kind, task.start.hour, task.end.hour) for task in tasks] == [
        ("book", 14, 15),
        ("book", 15, 16),
    ]


def test_hip3_backfill_includes_typed_trade_family(tmp_path: Path) -> None:
    """HIP-3 paired acquisition must retain its exact book and trade families."""
    config = OxaBackfillConfig(
        symbol="xyz:SP500",
        start=datetime(2026, 8, 6, 14, tzinfo=UTC),
        end=datetime(2026, 8, 6, 15, tzinfo=UTC),
        data_root=tmp_path,
        market_family="hip3",
    )

    assert [task.kind for task in iter_backfill_tasks(config)] == ["book", "trade"]


def test_hip3_book_only_audit_verifies_all_hourly_evidence(tmp_path: Path) -> None:
    """The final audit must validate checksums without expecting core trades."""
    start = datetime(2026, 8, 6, 14, tzinfo=UTC)
    for offset in range(2):
        left = start + timedelta(hours=offset)
        request = OxaBookRequest(
            "xyz:SP500",
            left,
            left + timedelta(hours=1),
            depth=2,
            limit=5,
            market_family="hip3",
        )
        page = _page()
        page["data"][0]["timestamp"] = (
            (  # type: ignore[index]
                left + timedelta(milliseconds=500)
            )
            .isoformat()
            .replace("+00:00", "Z")
        )
        fetched = fetch_orderbook_history(
            OxaHistoryClient(api_key="secret", session=_Session(page)), request
        )
        store_orderbook_history(tmp_path, request, fetched)

    report = audit_oxa_archive(
        OxaArchiveAuditConfig(
            symbol="xyz:SP500",
            start=start,
            end=start + timedelta(hours=2),
            data_root=tmp_path,
            depth=2,
            market_family="hip3",
            book_only=True,
        )
    )

    assert report.complete is True
    assert report.expected_bundles == 2
    assert report.present_bundles == 2
    assert report.book_snapshots == 2
    assert report.public_trades == 0


@pytest.mark.parametrize(
    ("symbol", "family"),
    [
        ("xyz:SP500", "core"),
        ("XYZ:SP500", "hip3"),
        ("xyz:sp500", "hip3"),
        ("../xyz:SP500", "hip3"),
    ],
)
def test_market_family_rejects_wrong_or_unsafe_symbol_identity(
    symbol: str, family: str
) -> None:
    """Family and symbol casing are part of immutable venue identity."""
    with pytest.raises(ValueError, match="symbol"):
        OxaBookRequest(
            symbol=symbol,
            start=datetime(2026, 8, 6, 14, tzinfo=UTC),
            end=datetime(2026, 8, 6, 15, tzinfo=UTC),
            market_family=family,  # type: ignore[arg-type]
        )


def _request() -> OxaBookRequest:
    return OxaBookRequest(
        symbol="xyz:SP500",
        start=datetime(2026, 8, 6, 14, tzinfo=UTC),
        end=datetime(2026, 8, 6, 15, tzinfo=UTC),
        depth=2,
        limit=5,
        market_family="hip3",
    )


def _page() -> dict[str, object]:
    return {
        "success": True,
        "data": [
            {
                "symbol": "xyz:SP500",
                "timestamp": "2026-08-06T14:00:00.500Z",
                "bids": [
                    {"px": "6317.0", "sz": "3.0", "n": 2},
                    {"px": "6316.9", "sz": "4.0", "n": 1},
                ],
                "asks": [
                    {"px": "6317.1", "sz": "2.0", "n": 1},
                    {"px": "6317.2", "sz": "5.0", "n": 3},
                ],
            }
        ],
        "meta": {"count": 1, "next_cursor": None, "request_id": "hip3-request"},
    }

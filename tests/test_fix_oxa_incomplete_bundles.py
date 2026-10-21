"""Regression: bounded 0xArchive fetches never publish incomplete canonical bundles.

Each fetcher must (a) inspect its canonical directory before any vendor call,
reusing a verified complete bundle and failing fast on anything else, and (b)
refuse to publish an unfinished cursor chain at the canonical path. Explicit
partial fetches go to a ``_partial`` sibling that readers never resolve.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from hypervector.cli import main
from hypervector.data.oxa_archive_audit import (
    OxaArchiveAuditConfig,
    verified_archive_bundles,
)
from hypervector.data.oxa_backfill import (
    OxaBackfillConfig,
    OxaBackfillTask,
    _existing_result,
)
from hypervector.data.oxa_candles import (
    OxaCandleRequest,
    acquire_and_store_candles,
    candle_output_directory,
)
from hypervector.data.oxa_history import (
    OxaBookRequest,
    OxaHistoryClient,
    acquire_and_store_orderbooks,
    fetch_orderbook_history,
    output_directory,
    store_orderbook_history,
)
from hypervector.data.oxa_liquidations import (
    OxaLiquidationClient,
    OxaLiquidationRequest,
    acquire_and_store_liquidations,
    fetch_liquidation_history,
    liquidation_output_directory,
    store_liquidation_history,
)
from hypervector.data.oxa_prices import (
    OxaPriceRequest,
    acquire_and_store_prices,
    price_output_directory,
)
from hypervector.data.oxa_trades import (
    OxaTradeClient,
    OxaTradeRequest,
    acquire_and_store_trades,
    fetch_trade_history,
    store_trade_history,
    trade_output_directory,
)

START = datetime(2026, 7, 26, 23, tzinfo=UTC)
END = datetime(2026, 7, 27, 0, tzinfo=UTC)
SECRET = "never-render-this-key"


@dataclass
class FakeResponse:
    payload: object
    status_code: int = 200
    headers: dict[str, str] | None = None

    def json(self) -> object:
        return self.payload


class FakeSession:
    """Serve queued vendor pages and count every request."""

    def __init__(self, payloads: list[dict[str, object]]) -> None:
        self.payloads = list(payloads)
        self.calls: list[dict[str, object]] = []

    def get(
        self,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, int | str],
        timeout: float,
    ) -> FakeResponse:
        self.calls.append({"url": url, "params": dict(params)})
        if not self.payloads:
            raise AssertionError("unexpected extra vendor call")
        return FakeResponse(self.payloads.pop(0))


def _cursor(index: int, total: int) -> str | None:
    return None if index == total else f"cur-{index}"


def _envelope(kind: str, index: int, total: int, data: list[object]) -> dict:
    return {
        "success": True,
        "data": data,
        "meta": {"request_id": f"{kind}-{index}", "next_cursor": _cursor(index, total)},
    }


def _stamp(index: int) -> str:
    return f"2026-07-26T23:{10 + index:02d}:00Z"


def book_pages(total: int = 3) -> list[dict[str, object]]:
    return [
        _envelope(
            "book",
            index,
            total,
            [
                {
                    "symbol": "BTC",
                    "timestamp": _stamp(index),
                    "bids": [{"px": "65370.0", "sz": "1.0", "n": 1}],
                    "asks": [{"px": "65371.0", "sz": "1.0", "n": 1}],
                }
            ],
        )
        for index in range(1, total + 1)
    ]


def trade_pages(total: int = 3) -> list[dict[str, object]]:
    pages = []
    for index in range(1, total + 1):
        base = {
            "symbol": "BTC",
            "price": "65370",
            "size": "0.1",
            "timestamp": _stamp(index),
            "trade_id": 1000 + index,
        }
        data = [
            {**base, "side": "B", "crossed": False},
            {**base, "side": "A", "crossed": True},
        ]
        pages.append(_envelope("trade", index, total, data))
    return pages


def liquidation_pages(total: int = 3) -> list[dict[str, object]]:
    return [
        _envelope(
            "liquidation",
            index,
            total,
            [
                {
                    "symbol": "BTC",
                    "timestamp": _stamp(index),
                    "liquidated_user": "0x" + "1" * 40,
                    "price": "77800.5",
                    "size": "0.75",
                    "side": "B",
                    "direction": "Close Short",
                    "trade_id": 2000 + index,
                }
            ],
        )
        for index in range(1, total + 1)
    ]


def price_pages(total: int = 3) -> list[dict[str, object]]:
    return [
        _envelope(
            "price",
            index,
            total,
            [
                {
                    "timestamp": _stamp(index),
                    "mark_price": "64356",
                    "oracle_price": "64368",
                    "mid_price": "64355.5",
                }
            ],
        )
        for index in range(1, total + 1)
    ]


def candle_pages(total: int = 3) -> list[dict[str, object]]:
    return [
        _envelope(
            "candle",
            index,
            total,
            [
                {
                    "timestamp": _stamp(index),
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.5,
                    "volume": 2.0,
                    "quote_volume": 201.0,
                    "trade_count": 3,
                }
            ],
        )
        for index in range(1, total + 1)
    ]


@dataclass(frozen=True)
class Kind:
    name: str
    pages: Callable[[int], list[dict[str, object]]]
    request: Callable[[int], object]
    acquire: Callable[..., dict[str, object]]
    directory: Callable[[Path, object], Path]


KINDS = {
    "book": Kind(
        "book",
        book_pages,
        lambda pages: OxaBookRequest("BTC", START, END, max_pages=pages),
        acquire_and_store_orderbooks,
        output_directory,
    ),
    "trade": Kind(
        "trade",
        trade_pages,
        lambda pages: OxaTradeRequest("BTC", START, END, max_pages=pages),
        acquire_and_store_trades,
        trade_output_directory,
    ),
    "liquidation": Kind(
        "liquidation",
        liquidation_pages,
        lambda pages: OxaLiquidationRequest("BTC", START, END, max_pages=pages),
        acquire_and_store_liquidations,
        liquidation_output_directory,
    ),
    "price": Kind(
        "price",
        price_pages,
        lambda pages: OxaPriceRequest("BTC", START, END, max_pages=pages),
        acquire_and_store_prices,
        price_output_directory,
    ),
    "candle": Kind(
        "candle",
        candle_pages,
        lambda pages: OxaCandleRequest("BTC", START, END, "1m", 10_000, pages),
        acquire_and_store_candles,
        candle_output_directory,
    ),
}
PAGINATED_LABEL_KINDS = ("book", "trade", "liquidation")


def _serve(monkeypatch: pytest.MonkeyPatch, session: FakeSession) -> None:
    monkeypatch.setattr("hypervector.data.oxa_api.requests.Session", lambda: session)


def _acquire(
    kind: Kind, root: Path, max_pages: int, **options: object
) -> dict[str, object]:
    return kind.acquire(
        data_root=root, api_key=SECRET, request=kind.request(max_pages), **options
    )


@pytest.mark.parametrize("name", sorted(KINDS))
def test_incomplete_fetch_is_never_published_at_canonical_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    kind = KINDS[name]
    session = FakeSession(kind.pages(3))
    _serve(monkeypatch, session)

    with pytest.raises(ValueError, match="max-pages exhausted") as raised:
        _acquire(kind, tmp_path, 1)

    assert len(session.calls) == 1
    assert SECRET not in str(raised.value)
    directory = kind.directory(tmp_path, kind.request(1))
    assert not directory.exists()
    assert not directory.parent.exists() or list(directory.parent.iterdir()) == []


def _legacy_incomplete_bundle(name: str, root: Path) -> Path:
    """Publish an incomplete bundle the way the pre-fix CLI defaults did."""
    session = FakeSession(KINDS[name].pages(3))
    if name == "book":
        request = OxaBookRequest("BTC", START, END, max_pages=1)
        fetched = fetch_orderbook_history(
            OxaHistoryClient(api_key="k", session=session), request
        )
        return store_orderbook_history(root, request, fetched).directory
    if name == "trade":
        request = OxaTradeRequest("BTC", START, END, max_pages=1)
        fetched = fetch_trade_history(
            OxaTradeClient(api_key="k", session=session), request
        )
        return store_trade_history(root, request, fetched).directory
    request = OxaLiquidationRequest("BTC", START, END, max_pages=1)
    fetched = fetch_liquidation_history(
        OxaLiquidationClient(api_key="k", session=session), request
    )
    return store_liquidation_history(root, request, fetched).directory


@pytest.mark.parametrize("name", PAGINATED_LABEL_KINDS)
def test_existing_incomplete_bundle_fails_before_any_vendor_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    directory = _legacy_incomplete_bundle(name, tmp_path)
    before = sorted(path.name for path in directory.rglob("*"))
    session = FakeSession(KINDS[name].pages(3))
    _serve(monkeypatch, session)

    with pytest.raises(ValueError, match="incomplete") as raised:
        _acquire(KINDS[name], tmp_path, 5)

    assert session.calls == []
    assert "continuation_cursor='cur-1'" in str(raised.value)
    assert "move it aside" in str(raised.value)
    assert sorted(path.name for path in directory.rglob("*")) == before


@pytest.mark.parametrize("name", sorted(KINDS))
def test_existing_complete_bundle_is_reused_without_vendor_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    kind = KINDS[name]
    first = FakeSession(kind.pages(3))
    _serve(monkeypatch, first)
    stored = _acquire(kind, tmp_path, 5)
    assert len(first.calls) == 3
    assert stored["complete"] is True

    second = FakeSession(kind.pages(3))
    _serve(monkeypatch, second)
    reused = _acquire(kind, tmp_path, 5)

    assert second.calls == []
    assert reused["ok"] is True
    assert reused["reused"] is True
    assert reused["complete"] is True
    assert reused["directory"] == stored["directory"]
    assert reused["request_ids"] == stored["request_ids"]
    assert reused["page_count"] == 3


@pytest.mark.parametrize("name", sorted(KINDS))
def test_corrupted_existing_bundle_fails_before_vendor_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    kind = KINDS[name]
    _serve(monkeypatch, FakeSession(kind.pages(1)))
    stored = _acquire(kind, tmp_path, 1)
    page = Path(str(stored["directory"])) / "raw" / "page-0001.json.gz"
    page.write_bytes(page.read_bytes() + b"tampered")

    session = FakeSession(kind.pages(1))
    _serve(monkeypatch, session)
    with pytest.raises(ValueError, match="byte count|checksum"):
        _acquire(kind, tmp_path, 1)
    assert session.calls == []


@pytest.mark.parametrize("name", PAGINATED_LABEL_KINDS)
def test_allow_partial_publishes_only_to_noncanonical_sibling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    kind = KINDS[name]
    _serve(monkeypatch, FakeSession(kind.pages(3)))

    report = _acquire(kind, tmp_path, 1, allow_partial=True)

    canonical = kind.directory(tmp_path, kind.request(1))
    assert report["complete"] is False
    assert report["partial"] is True
    assert report["continuation_cursor"] == "cur-1"
    assert Path(str(report["directory"])).name == canonical.name + "_partial"
    assert not canonical.exists()
    manifest = json.loads(
        (Path(str(report["directory"])) / "manifest.json").read_text("utf-8")
    )
    assert manifest["complete"] is False

    second = FakeSession(kind.pages(3))
    _serve(monkeypatch, second)
    with pytest.raises(ValueError, match="partial .* already exists"):
        _acquire(kind, tmp_path, 1, allow_partial=True)
    assert second.calls == []


def test_partial_book_sibling_is_invisible_to_backfill_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _serve(monkeypatch, FakeSession(book_pages(3)))
    _acquire(KINDS["book"], tmp_path, 1, allow_partial=True)
    config = OxaBackfillConfig("BTC", START, END, tmp_path, book_only=True)

    assert _existing_result(config, OxaBackfillTask("book", START, END)) is None


def test_cli_book_fetch_refuses_an_incomplete_window(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OXA_API_KEY", SECRET)
    session = FakeSession(book_pages(3))
    _serve(monkeypatch, session)

    # The default page budget completes a normal window; a budget smaller than
    # the window still refuses it and stores nothing.
    rc = main(
        [
            "--data-root",
            str(tmp_path),
            "archive",
            "book-fetch",
            "--start",
            START.isoformat(),
            "--end",
            END.isoformat(),
            "--max-pages",
            "1",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""
    error = json.loads(captured.err)
    assert error["ok"] is False
    assert "max-pages exhausted" in error["error"]
    assert SECRET not in captured.err
    assert not output_directory(tmp_path, OxaBookRequest("BTC", START, END)).exists()


def _handler_args(tmp_path: Path, **extra: object) -> argparse.Namespace:
    return argparse.Namespace(
        data_root=tmp_path,
        symbol="BTC",
        start=START,
        end=END,
        depth=20,
        limit=1000,
        max_pages=1,
        timeout=30.0,
        market_family="core",
        **extra,
    )


@pytest.mark.parametrize(
    ("handler", "target"),
    [
        (
            "hypervector.cli_oxa:cmd_oxa_book_fetch",
            "oxa_history.acquire_and_store_orderbooks",
        ),
        (
            "hypervector.cli_oxa:cmd_oxa_trade_fetch",
            "oxa_trades.acquire_and_store_trades",
        ),
        (
            "hypervector.cli_oxa_liquidations:cmd_oxa_liquidation_fetch",
            "oxa_liquidations.acquire_and_store_liquidations",
        ),
    ],
)
@pytest.mark.parametrize("allow_partial", [None, False, True])
def test_cli_handlers_forward_allow_partial_only_when_requested(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    handler: str,
    target: str,
    allow_partial: bool | None,
) -> None:
    import importlib

    captured: dict[str, object] = {}

    def fake_acquire(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr(f"hypervector.data.{target}", fake_acquire)
    module_name, function_name = handler.split(":")
    command = getattr(importlib.import_module(module_name), function_name)
    extra = {} if allow_partial is None else {"allow_partial": allow_partial}

    assert command(_handler_args(tmp_path, **extra)) == 0
    capsys.readouterr()
    if allow_partial:
        assert captured["allow_partial"] is True
    else:
        assert "allow_partial" not in captured


@pytest.mark.parametrize(
    ("command", "target"),
    [
        ("book-fetch", "oxa_history.acquire_and_store_orderbooks"),
        ("trade-fetch", "oxa_trades.acquire_and_store_trades"),
        ("price-fetch", "oxa_prices.acquire_and_store_prices"),
    ],
)
def test_market_family_flag_reaches_book_trade_and_price_requests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
    target: str,
) -> None:
    captured: list[object] = []
    monkeypatch.setattr(
        f"hypervector.data.{target}",
        lambda **kwargs: captured.append(kwargs["request"]) or {"ok": True},
    )

    rc = main(
        [
            "--data-root",
            str(tmp_path),
            "archive",
            command,
            "--symbol",
            "xyz:AAA",
            "--market-family",
            "hip3",
            "--start",
            START.isoformat(),
            "--end",
            END.isoformat(),
        ]
    )

    capsys.readouterr()
    assert rc == 0
    assert captured[0].market_family == "hip3"  # type: ignore[attr-defined]
    assert captured[0].symbol == "xyz:AAA"  # type: ignore[attr-defined]


def test_audit_reports_incomplete_bundle_instead_of_identity_mismatch(
    tmp_path: Path,
) -> None:
    _legacy_incomplete_bundle("book", tmp_path)
    config = OxaArchiveAuditConfig("BTC", START, END, tmp_path, book_only=True)

    with pytest.raises(ValueError, match="incomplete") as raised:
        verified_archive_bundles(config)

    assert "identity mismatch" not in str(raised.value)
    assert "continuation_cursor='cur-1'" in str(raised.value)


def test_backfill_resume_names_cursor_of_incomplete_window(tmp_path: Path) -> None:
    _legacy_incomplete_bundle("book", tmp_path)
    config = OxaBackfillConfig("BTC", START, END, tmp_path, book_only=True)

    with pytest.raises(ValueError, match="incomplete") as raised:
        _existing_result(config, OxaBackfillTask("book", START, END))

    assert "continuation_cursor='cur-1'" in str(raised.value)
    assert "max_pages=1" in str(raised.value)


def test_reuse_requires_same_window_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A manifest naming another window at this path is foreign evidence."""
    _serve(monkeypatch, FakeSession(trade_pages(1)))
    stored = _acquire(KINDS["trade"], tmp_path, 1)
    manifest_path = Path(str(stored["directory"])) / "manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    manifest["requested_end"] = (END + timedelta(hours=1)).isoformat()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    session = FakeSession(trade_pages(1))
    _serve(monkeypatch, session)
    with pytest.raises(ValueError, match="identity differs"):
        _acquire(KINDS["trade"], tmp_path, 1)
    assert session.calls == []

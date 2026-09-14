"""Original vendor responses, normalized bytes and execution clocks must agree."""

import gzip
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from hypervector.data.oxa_history import (
    OxaBookFetch,
    OxaBookRequest,
    _parse_page,
    output_directory,
    store_orderbook_history,
)
from hypervector.data.oxa_storage import (
    file_evidence,
    gzip_text_writer,
    write_gzip_json,
)
from hypervector.research.native_replay_book_source import (
    RecordedBookUnavailable,
    authenticate_book_bundle,
)
from hypervector.research.native_replay_account import ExactFillAccount
from hypervector.research.native_replay_clock import ReplayClock
from hypervector.research.native_replay_depth import RecordedBook
from hypervector.research.native_replay_venue import IocOrder, ReceiptTiming, RecordedIocVenue

FIXTURE = Path(__file__).parent / "fixtures/native_replay_sndk_book_20260701.json"


def make_bundle(root: Path, *, empty: bool = False) -> tuple[OxaBookRequest, Path]:
    """Store a bounded copy of an original raw snapshot without constructing a network client."""
    sample = json.loads(FIXTURE.read_text())
    start = datetime(2026, 7, 1, 12, tzinfo=UTC)
    request = OxaBookRequest("xyz:SNDK", start, start + timedelta(hours=1), market_family="hip3")
    payload = {
        "success": True,
        "data": [] if empty else [sample["raw_row"]],
        "meta": {"request_id": "recorded-fixture", "next_cursor": None},
    }
    page = _parse_page(payload, request)
    result = OxaBookFetch((page,), page.snapshots, True, None, 0)
    store_orderbook_history(root, request, result)
    return request, output_directory(root, request)


def test_authenticated_source_preserves_original_decimal_depth_and_exact_arrival(
    tmp_path: Path,
) -> None:
    """The first eligible exchange snapshot supplies original decimal levels and source identity."""
    request, path = make_bundle(tmp_path)
    bundle = authenticate_book_bundle(tmp_path, request)
    sample = json.loads(FIXTURE.read_text())
    clock = sample["normalized_row"]["ts_exchange_ms"]
    book = bundle.execution_book(clock - 500, maximum_delay_ms=500, quantity_step=Decimal(".001"))
    assert book.source_id == f"0xarchive:{request.symbol}:{clock}"
    assert bundle.manifest_sha256 == file_evidence(path / "manifest.json")["sha256"]
    assert book.exchange_time_ms == clock and book.symbol == request.symbol
    for side in ("bids", "asks"):
        assert [(str(row.price), str(row.quantity)) for row in getattr(book, side)] == [
            (row["px"], row["sz"]) for row in sample["raw_row"][side]
        ]


def test_recaptured_exchange_snapshot_cannot_replenish_liquidity(tmp_path: Path) -> None:
    """Distinct retrieval receipts for one exchange clock describe one finite book."""
    request, first = make_bundle(tmp_path / "first")
    _, second = make_bundle(tmp_path / "second")
    manifest = json.loads((second / "manifest.json").read_text())
    with gzip.open(second / "raw/page-0001.json.gz", "rt") as stream:
        payload = json.load(stream)
    payload["meta"]["request_id"] = "independent-second-retrieval"
    (second / "raw/page-0001.json.gz").unlink()
    write_gzip_json(second / "raw/page-0001.json.gz", payload)
    with gzip.open(second / "books.jsonl.gz", "rt") as stream:
        normalized = json.load(stream)
    normalized["vendor_request_id"] = "independent-second-retrieval"
    (second / "books.jsonl.gz").unlink()
    with gzip_text_writer(second / "books.jsonl.gz") as stream:
        stream.write(json.dumps(normalized) + "\n")
    for name in ("raw/page-0001.json.gz", "books.jsonl.gz"):
        manifest["files"][name] = file_evidence(second / name)
    manifest["request_ids"] = ["independent-second-retrieval"]
    (second / "manifest.json").write_text(json.dumps(manifest))
    bundles = [authenticate_book_bundle(tmp_path / name, request) for name in ("first", "second")]
    assert bundles[0].manifest_sha256 != bundles[1].manifest_sha256
    arrival = bundles[0].snapshots[0].ts_exchange_ms
    books = [
        b.execution_book(arrival, maximum_delay_ms=0, quantity_step=Decimal(".001"))
        for b in bundles
    ]
    assert books[0] == books[1], "retrieval provenance must not create new exchange liquidity"
    assert first != second
    _assert_recapture_has_no_fresh_liquidity(*books)


def _assert_recapture_has_no_fresh_liquidity(first: RecordedBook, second: RecordedBook) -> None:
    """Open and close once; another retrieval cannot fund a second entry from exhausted depth."""
    totals = {
        side: sum((level.quantity for level in levels), Decimal(0))
        for side, levels in (("buy", first.asks), ("sell", first.bids))
    }
    opening = min(totals, key=totals.get)
    closing = "sell" if opening == "buy" else "buy"
    clock = ReplayClock(first.exchange_time_ms)
    account = ExactFillAccount(Decimal("1000000"), (first.symbol,))
    account.mark(
        clock.next_stamp(), source_time_ms=clock.now_ms, prices={first.symbol: first.asks[0].price}
    )
    venue = RecordedIocVenue(account, clock)
    timing = ReceiptTiming(clock.now_ms, clock.now_ms, clock.now_ms, False)
    for index, (side, reduce, book) in enumerate(
        ((opening, False, first), (closing, True, first), (opening, False, second))
    ):
        limit = book.asks[-1].price if side == "buy" else book.bids[-1].price
        order = IocOrder(
            str(index),
            book.symbol,
            side,
            totals[opening],
            limit,
            Decimal(1),
            Decimal(0),
            clock.now_ms,
            clock.now_ms,
            clock.now_ms,
            reduce,
        )
        venue.submit(order, book, timing, maximum_book_delay_ms=0)
        venue.advance_to(clock.now_ms)
        statuses = venue.response(str(index))["response"]["data"]["statuses"]
        assert ("error" in statuses[0]) == (index == 2)
    assert not account.snapshot().positions


@pytest.mark.parametrize(
    "empty,offset,delay", [(False, 1, 500), (False, -501, 500), (True, 0, 500)]
)
def test_missing_or_out_of_window_execution_source_is_explicit(
    tmp_path: Path, empty: bool, offset: int, delay: int
) -> None:
    """A prior, excessively delayed or absent book cannot silently supply an execution price."""
    request, _ = make_bundle(tmp_path, empty=empty)
    bundle = authenticate_book_bundle(tmp_path, request)
    clock = int(request.start.timestamp() * 1000) + 1000
    with pytest.raises(RecordedBookUnavailable):
        bundle.execution_book(clock + offset, maximum_delay_ms=delay, quantity_step=Decimal(".001"))


@pytest.mark.parametrize(
    "change",
    [
        "checksum",
        "missing_file",
        "raw_disagreement",
        "normalized_disagreement",
        "row_count",
        "page_count",
        "request_ids",
        "requested_depth",
        "continuation_cursor",
        "observed_start",
        "raw_cursor",
    ],
)
def test_inconsistent_archived_books_cannot_authorize_replay(tmp_path: Path, change: str) -> None:
    """Even rehashed local derivatives must agree with original vendor rows and completion evidence."""
    request, directory = make_bundle(tmp_path)
    manifest = json.loads((directory / "manifest.json").read_text())
    _corrupt(directory, manifest, change)
    (directory / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises((ValueError, FileNotFoundError)):
        authenticate_book_bundle(tmp_path, request)


def _corrupt(directory: Path, manifest: dict[str, object], change: str) -> None:
    if change in {"checksum", "missing_file"}:
        path = directory / "books.jsonl.gz"
        if change == "checksum":
            path.write_bytes(path.read_bytes() + b"changed")
        else:
            path.unlink()
    elif change.startswith("raw_"):
        relative = "raw/page-0001.json.gz"
        with gzip.open(directory / relative, "rt") as handle:
            raw = json.load(handle)
        if change == "raw_disagreement":
            raw["data"][0]["asks"][0]["sz"] = "12.000"
        else:
            raw["meta"]["next_cursor"] = "unfinished"
        (directory / relative).unlink()
        write_gzip_json(directory / relative, raw)
        manifest["files"][relative] = file_evidence(directory / relative)
    elif change == "normalized_disagreement":
        path = directory / "books.jsonl.gz"
        with gzip.open(path, "rt") as handle:
            normalized = json.loads(next(handle))
        normalized["asks"][0]["sz"] = "12.000"
        path.unlink()
        with gzip_text_writer(path) as handle:
            handle.write(json.dumps(normalized) + "\n")
        manifest["files"][path.name] = file_evidence(path)
    else:
        manifest[change] = {
            "row_count": 2,
            "page_count": 2,
            "request_ids": ["unknown"],
            "requested_depth": 19,
            "continuation_cursor": "unfinished",
            "observed_start": "2026-07-01T12:00:02Z",
        }[change]

"""Page completion and archive ambiguity checks on original vendor-shaped depth."""

from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
import gzip
import json
from pathlib import Path

import pytest
from test_native_replay_book_source import FIXTURE, make_bundle

from hypervector.data.oxa_history import (
    OxaBookFetch,
    _merge_page_snapshots,
    _parse_page,
    output_directory,
    store_orderbook_history,
)
from hypervector.data.oxa_storage import file_evidence, gzip_text_writer, write_gzip_json
from hypervector.research.native_replay_book_source import authenticate_book_bundle


def test_completed_pagination_coalesces_boundary_and_preserves_latest_depth(tmp_path: Path) -> None:
    """An overlapping page boundary must yield one book with canonical last-page provenance."""
    request, _ = make_bundle(tmp_path / "seed")
    request = replace(request, max_pages=2)
    first = json.loads(FIXTURE.read_text())["raw_row"]
    second = deepcopy(first)
    second["asks"][0]["sz"] = "12.000"
    later = deepcopy(second)
    later["timestamp"] = "2026-07-01T12:00:02Z"
    pages = [
        _parse_page(
            {
                "success": True,
                "data": rows,
                "meta": {"request_id": identity, "next_cursor": cursor},
            },
            request,
        )
        for rows, identity, cursor in (
            ([first], "first", "page-2"),
            ([second, later], "second", None),
        )
    ]
    snapshots, coalesced = _merge_page_snapshots(pages)
    store_orderbook_history(
        tmp_path, request, OxaBookFetch(tuple(pages), snapshots, True, None, coalesced)
    )
    bundle = authenticate_book_bundle(tmp_path, request)
    assert len(bundle.snapshots) == 2 and coalesced == 1
    book = bundle.execution_book(
        bundle.snapshots[0].ts_exchange_ms, maximum_delay_ms=0, quantity_step=Decimal(".001")
    )
    assert book.asks[0].quantity == Decimal("12.000")
    directory = output_directory(tmp_path, request)
    with gzip.open(directory / "books.jsonl.gz", "rt") as handle:
        assert [json.loads(line)["vendor_request_id"] for line in handle] == ["second", "second"]


@pytest.mark.parametrize(
    "change",
    [
        "ambiguous_raw",
        "extra_raw",
        "missing_declared_page",
        "ambiguous_normalized",
        "extra_normalized_row",
        "boolean_count",
        "negative_count",
    ],
)
def test_ambiguous_or_unaccounted_archive_bytes_are_rejected(tmp_path: Path, change: str) -> None:
    """Rehashed extra files or rows cannot become unreviewed depth or completion evidence."""
    request, directory = make_bundle(tmp_path)
    manifest = json.loads((directory / "manifest.json").read_text())
    if change in {"ambiguous_raw", "extra_raw", "missing_declared_page"}:
        name = "raw/page-0001.json" if change == "ambiguous_raw" else "raw/page-0002.json"
        with gzip.open(directory / "raw/page-0001.json.gz", "rt") as stream:
            (directory / name).write_text(stream.read())
        manifest["files"][name] = file_evidence(directory / name)
        if change == "missing_declared_page":
            del manifest["files"]["raw/page-0001.json.gz"]
    elif change.startswith("ambiguous_normalized") or change == "extra_normalized_row":
        with gzip.open(directory / "books.jsonl.gz", "rt") as stream:
            text = stream.read()
        if change == "ambiguous_normalized":
            name = "books.jsonl"
            (directory / name).write_text(text)
        else:
            name = "books.jsonl.gz"
            (directory / name).unlink()
            with gzip_text_writer(directory / name) as stream:
                stream.write(text + text)
        manifest["files"][name] = file_evidence(directory / name)
    else:
        manifest["page_count"] = True if change == "boolean_count" else -1
    (directory / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        authenticate_book_bundle(tmp_path, request)


def test_early_terminal_raw_page_cannot_prove_later_pagination(tmp_path: Path) -> None:
    """A rehashed second page does not repair an original first-page termination."""
    request, directory = make_bundle(tmp_path)
    request = replace(request, max_pages=2)
    with gzip.open(directory / "raw/page-0001.json.gz", "rt") as stream:
        payload = json.load(stream)
    write_gzip_json(directory / "raw/page-0002.json.gz", payload)
    manifest = json.loads((directory / "manifest.json").read_text())
    manifest["page_count"] = 2
    manifest["files"]["raw/page-0002.json.gz"] = file_evidence(directory / "raw/page-0002.json.gz")
    (directory / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="complete pagination"):
        authenticate_book_bundle(tmp_path, request)

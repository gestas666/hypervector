"""Shared bounded cursor pagination and raw-page evidence for 0xArchive."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol, TypeVar

from hypervector.data.oxa_storage import file_evidence, write_gzip_json


class CursorPage(Protocol):
    """A validated vendor page that names its continuation cursor."""

    @property
    def next_cursor(self) -> str | None: ...


class RawEvidencePage(Protocol):
    """A validated vendor page that retains its raw response envelope."""

    @property
    def raw_payload(self) -> object: ...


PageT = TypeVar("PageT", bound=CursorPage)


def paginate(
    fetch_page: Callable[[str | None], PageT],
    max_pages: int,
    *,
    label: str,
) -> tuple[tuple[PageT, ...], str | None]:
    """Fetch at most ``max_pages`` cursor pages.

    Returns the pages in request order and the unfinished continuation cursor
    (``None`` when the vendor reported the window complete). A cursor that
    repeats any cursor already requested cannot make progress, so it fails
    instead of spending the remaining page budget on the same request.
    """
    if max_pages < 1:
        raise ValueError("max_pages must be at least 1")
    pages: list[PageT] = []
    requested: set[str] = set()
    cursor: str | None = None
    for _ in range(max_pages):
        page = fetch_page(cursor)
        pages.append(page)
        if cursor is not None:
            requested.add(cursor)
        next_cursor = page.next_cursor
        if next_cursor is None:
            return tuple(pages), None
        if next_cursor in requested:
            raise ValueError(f"0xArchive {label} cursor did not advance")
        cursor = next_cursor
    return tuple(pages), cursor


def write_raw_pages(
    raw_dir: Path,
    pages: Sequence[RawEvidencePage],
) -> dict[str, dict[str, object]]:
    """Write numbered gzip raw pages and return their manifest evidence."""
    evidence: dict[str, dict[str, object]] = {}
    for index, page in enumerate(pages, start=1):
        path = raw_dir / f"page-{index:04d}.json.gz"
        write_gzip_json(path, page.raw_payload)
        evidence[f"raw/{path.name}"] = file_evidence(path)
    return evidence

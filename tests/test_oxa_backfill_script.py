"""Tests for the resumable 0xArchive backfill command boundary."""

from __future__ import annotations

from importlib import import_module
from types import ModuleType


def _load_module() -> ModuleType:
    return import_module("hypervector.operations.oxa_backfill")


def test_cli_uses_resilient_bounded_retry_default() -> None:
    """An unattended multi-month job should not use the old three-attempt budget."""
    module = _load_module()

    args = module.build_parser().parse_args(
        [
            "--symbol",
            "xyz:GOLD",
            "--market-family",
            "hip3",
            "--books-only",
            "--start",
            "2026-02-26T17:00:00Z",
            "--end",
            "2026-08-06T15:00:00Z",
        ]
    )

    assert args.retries == 10


def test_cli_page_bounds_default_to_the_engine_constants_and_can_be_raised() -> None:
    """A busy hour needs more pages than the old single-page default allowed."""
    from hypervector.data.oxa_history import DEFAULT_BOOK_MAX_PAGES
    from hypervector.data.oxa_prices import DEFAULT_PRICE_MAX_PAGES
    from hypervector.data.oxa_trades import DEFAULT_TRADE_MAX_PAGES

    parser = _load_module().build_parser()
    window = ["--start", "2026-01-01T00:00:00Z", "--end", "2026-01-01T01:00:00Z"]
    defaults = parser.parse_args(window)
    assert (
        defaults.book_max_pages,
        defaults.trade_max_pages,
        defaults.price_max_pages,
    ) == (DEFAULT_BOOK_MAX_PAGES, DEFAULT_TRADE_MAX_PAGES, DEFAULT_PRICE_MAX_PAGES)
    raised = parser.parse_args(
        [*window, "--book-max-pages", "80", "--trade-max-pages", "900"]
    )
    assert (raised.book_max_pages, raised.trade_max_pages) == (80, 900)

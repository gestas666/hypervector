"""Run one resumable 0xArchive market-evidence backfill."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from hypervector.data.oxa_backfill import (
    DEFAULT_BOOK_MAX_PAGES,
    DEFAULT_PRICE_MAX_PAGES,
    DEFAULT_RETRIES,
    DEFAULT_TRADE_MAX_PAGES,
    OxaBackfillConfig,
    OxaBackfillResult,
    run_oxa_backfill,
)


def main(argv: Sequence[str] | None = None) -> int:
    """Parse explicit job bounds, emit JSONL progress, and return its status."""
    return run(build_parser().parse_args(argv))


def run(args: argparse.Namespace) -> int:
    """Run one validated backfill job.

    0 when it completed, 1 when it is incomplete or failed, 2 when the job
    bounds or flag combination are invalid (refused before any vendor call).
    """
    try:
        config = OxaBackfillConfig(
            symbol=args.symbol,
            start=args.start,
            end=args.end,
            data_root=Path(args.data_root),
            chunk=timedelta(minutes=args.chunk_minutes),
            workers=args.workers,
            retries=args.retries,
            book_max_pages=getattr(args, "book_max_pages", DEFAULT_BOOK_MAX_PAGES),
            trade_max_pages=getattr(args, "trade_max_pages", DEFAULT_TRADE_MAX_PAGES),
            price_max_pages=getattr(args, "price_max_pages", DEFAULT_PRICE_MAX_PAGES),
            include_prices=args.include_prices,
            price_only=args.prices_only,
            market_family=args.market_family,
            book_only=args.books_only,
        )
    except (TypeError, ValueError) as exc:
        _print_error(args, exc)
        return 2
    try:
        key = os.environ.get("OXA_API_KEY", "")
        results = run_oxa_backfill(config, api_key=key, progress=_print_progress)
    except (OSError, RuntimeError, ValueError) as exc:
        _print_error(args, exc)
        return 1
    rows = sum(result.rows for result in results)
    pages = sum(result.pages for result in results)
    print(json.dumps({"ok": True, "tasks": len(results), "rows": rows, "pages": pages}))
    return 0


def _print_error(args: argparse.Namespace, exc: BaseException) -> None:
    report = {
        "ok": False,
        "command": getattr(args, "command", "archive backfill"),
        "error_type": type(exc).__name__,
        "error": str(exc),
    }
    print(json.dumps(report), file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    """Build the resumable backfill command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="BTC")
    parser.add_argument("--start", type=_utc, required=True)
    parser.add_argument("--end", type=_utc, required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--chunk-minutes", type=int, default=60)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES)
    parser.add_argument("--book-max-pages", type=int, default=DEFAULT_BOOK_MAX_PAGES)
    parser.add_argument(
        "--trade-max-pages", type=int, default=DEFAULT_TRADE_MAX_PAGES
    )
    parser.add_argument(
        "--price-max-pages", type=int, default=DEFAULT_PRICE_MAX_PAGES
    )
    parser.add_argument("--include-prices", action="store_true")
    parser.add_argument("--prices-only", action="store_true")
    parser.add_argument("--market-family", choices=("core", "hip3"), default="core")
    parser.add_argument("--books-only", action="store_true")
    return parser


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("timestamp must include a UTC offset")
    return parsed.astimezone(UTC)


def _print_progress(result: OxaBackfillResult) -> None:
    payload = {
        "kind": result.task.kind,
        "start": result.task.start.isoformat(),
        "end": result.task.end.isoformat(),
        "rows": result.rows,
        "pages": result.pages,
        "status": "skipped" if result.skipped else "downloaded",
    }
    print(json.dumps(payload), flush=True)


if __name__ == "__main__":
    raise SystemExit(main())

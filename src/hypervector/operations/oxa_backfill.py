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
    DEFAULT_RETRIES,
    OxaBackfillConfig,
    OxaBackfillResult,
    run_oxa_backfill,
)


def main(argv: Sequence[str] | None = None) -> int:
    """Parse explicit job bounds, emit JSONL progress, and return its status."""
    return run(build_parser().parse_args(argv))


def run(args: argparse.Namespace) -> int:
    """Run one validated backfill job; 0 when it completed, 1 when it failed."""
    try:
        config = OxaBackfillConfig(
            symbol=args.symbol,
            start=args.start,
            end=args.end,
            data_root=Path(args.data_root),
            chunk=timedelta(minutes=args.chunk_minutes),
            workers=args.workers,
            retries=args.retries,
            include_prices=args.include_prices,
            price_only=args.prices_only,
            market_family=args.market_family,
            book_only=args.books_only,
        )
        key = os.environ.get("OXA_API_KEY", "")
        results = run_oxa_backfill(config, api_key=key, progress=_print_progress)
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    rows = sum(result.rows for result in results)
    pages = sum(result.pages for result in results)
    print(json.dumps({"ok": True, "tasks": len(results), "rows": rows, "pages": pages}))
    return 0


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

"""Run one resumable paired 0xArchive history backfill."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from hypervector.data.oxa_backfill import (
    OxaBackfillConfig,
    OxaBackfillResult,
    run_oxa_backfill,
)


def main() -> int:
    """Parse explicit job bounds, emit JSONL progress, and return its status."""
    args = _parser().parse_args()
    try:
        config = OxaBackfillConfig(
            symbol=args.symbol,
            start=args.start,
            end=args.end,
            data_root=args.data_root,
            chunk=timedelta(minutes=args.chunk_minutes),
            workers=args.workers,
            retries=args.retries,
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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="BTC")
    parser.add_argument("--start", type=_utc, required=True)
    parser.add_argument("--end", type=_utc, required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--chunk-minutes", type=int, default=60)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--retries", type=int, default=3)
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

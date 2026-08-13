"""Audit hourly 0xArchive BTC books/trades for coverage and checksums."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from hypervector.data.oxa_archive_audit import (
    OxaArchiveAuditConfig,
    audit_oxa_archive,
)


def main() -> int:
    """Audit configured bounds and emit a machine-readable report."""
    args = _parser().parse_args()
    try:
        config = OxaArchiveAuditConfig(
            args.symbol,
            args.start,
            args.end,
            args.data_root,
            depth=args.depth,
            market_family=args.market_family,
            book_only=args.books_only,
        )
        report = audit_oxa_archive(config)
    except (OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    rendered = json.dumps(report.to_dict(), indent=2)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report.complete else 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="BTC")
    parser.add_argument("--start", type=_utc, required=True)
    parser.add_argument("--end", type=_utc, required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--depth", type=int, default=20)
    parser.add_argument("--market-family", choices=("core", "hip3"), default="core")
    parser.add_argument("--books-only", action="store_true")
    parser.add_argument("--out", type=Path, default=None)
    return parser


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("timestamp must include a UTC offset")
    return parsed.astimezone(UTC)


if __name__ == "__main__":
    raise SystemExit(main())

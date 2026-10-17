"""0xArchive backfill and coverage-audit handlers; imported only on dispatch."""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timedelta
import json
from pathlib import Path

from hypervector.commands.common import CommandRefused


def cmd_backfill(args: argparse.Namespace) -> int:
    """Run the resumable backfill in-process: 0 complete, 1 incomplete or failed."""
    from hypervector.operations.oxa_backfill import run

    return run(args)


def cmd_audit(args: argparse.Namespace) -> int:
    """Audit archived evidence coverage read-only; exit 0 whenever the audit ran.

    Every expected bundle is checked per chunk, so each missing chunk start is
    listed. Nothing is fetched and no directory is created. A present but corrupt
    bundle raises, which the CLI reports as a technical failure (exit 1).
    """
    from hypervector.data.oxa_archive_audit import (
        OxaArchiveAuditConfig,
        audit_oxa_archive,
    )

    if args.chunk_minutes <= 0:
        raise CommandRefused("--chunk-minutes must be positive")
    try:
        config = OxaArchiveAuditConfig(
            args.symbol,
            args.start,
            args.end,
            Path(args.data_root),
            chunk=timedelta(minutes=args.chunk_minutes),
            depth=args.depth,
            market_family=args.market_family,
            book_only=args.books_only,
        )
    except ValueError as exc:
        raise CommandRefused(str(exc)) from exc
    totals = {
        "expected": 0,
        "present": 0,
        "book_snapshots": 0,
        "public_trades": 0,
        "empty_book_windows": 0,
        "empty_trade_windows": 0,
        "evidence_bytes": 0,
    }
    missing: list[str] = []
    missing_directories: list[str] = []
    for start, end in _windows(config.start, config.end, config.chunk):
        window = audit_oxa_archive(replace(config, start=start, end=end))
        totals["expected"] += window.expected_bundles
        totals["present"] += window.present_bundles
        totals["book_snapshots"] += window.book_snapshots
        totals["public_trades"] += window.public_trades
        totals["empty_book_windows"] += window.empty_book_windows
        totals["empty_trade_windows"] += window.empty_trade_windows
        totals["evidence_bytes"] += window.evidence_bytes
        if not window.complete:
            missing.append(start.isoformat())
            missing_directories.extend(window.missing_directories)
    report: dict[str, object] = {
        "ok": True,
        "command": args.command,
        "read_only": True,
        "symbol": config.symbol,
        "market_family": config.market_family,
        "start": config.start.isoformat(),
        "end": config.end.isoformat(),
        "chunk_minutes": args.chunk_minutes,
        "depth": config.depth,
        "books_only": config.book_only,
        "complete": not missing,
        **totals,
        "missing": missing,
        "missing_directories": missing_directories,
    }
    print(json.dumps(report, indent=2))
    return 0


def _windows(
    start: datetime, end: datetime, chunk: timedelta
) -> list[tuple[datetime, datetime]]:
    """Chunk windows exactly as the backfill and the archive audit lay them out."""
    windows: list[tuple[datetime, datetime]] = []
    cursor = start
    while cursor < end:
        stop = min(cursor + chunk, end)
        windows.append((cursor, stop))
        cursor = stop
    return windows

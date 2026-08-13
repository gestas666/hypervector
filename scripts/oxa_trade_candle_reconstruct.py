#!/usr/bin/env python3
"""Publish continuous candles from native bars and verified public trades."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import UTC, datetime
import json
from pathlib import Path
import sys

from hypervector.data.oxa_archive_audit import OxaArchiveAuditConfig
from hypervector.data.oxa_storage import file_evidence
from hypervector.data.oxa_trade_candle_audit import (
    store_reconstructed_trade_candles,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the explicit reconstruction command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--start", type=_utc, required=True)
    parser.add_argument("--end", type=_utc, required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--candles", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Validate inputs and publish one immutable reconstruction bundle."""
    args = build_parser().parse_args(argv)
    try:
        config = OxaArchiveAuditConfig(
            args.symbol,
            args.start,
            args.end,
            args.data_root,
        )
        stored, report = store_reconstructed_trade_candles(
            config,
            args.candles,
            args.out,
        )
    except (OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "out": str(args.out.resolve()),
                "candles": file_evidence(stored),
                "reconstruction": report.to_dict(),
            },
            sort_keys=True,
        )
    )
    return 0


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("timestamp must include a UTC offset")
    return parsed.astimezone(UTC)


if __name__ == "__main__":
    raise SystemExit(main())

"""Audit normalized public trades against independent venue candles."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from typing import Sequence

from hypervector.data.oxa_archive_audit import OxaArchiveAuditConfig
from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.data.oxa_trade_candle_audit import audit_trade_candle_parity


def build_parser() -> argparse.ArgumentParser:
    """Build the explicit parity-audit command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--start", type=_utc, required=True)
    parser.add_argument("--end", type=_utc, required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--candles", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Verify parity and write one immutable, source-bound report."""
    args = build_parser().parse_args(argv)
    try:
        config = OxaArchiveAuditConfig(
            args.symbol,
            args.start,
            args.end,
            args.data_root,
        )
        report = audit_trade_candle_parity(config, args.candles)
        write_immutable_json(args.out, report.to_dict())
    except (FileExistsError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {"ok": True, "out": str(args.out), "evidence": file_evidence(args.out)},
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

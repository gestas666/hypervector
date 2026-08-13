"""Materialize immutable gap-safe SOL bars for older venue-event replay."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from typing import Sequence

from hypervector.data.oxa_storage import file_evidence
from hypervector.research.sol_range_onset_backward_challenge import (
    load_verified_sol_backward_inputs,
    prepare_gap_safe_blocks,
)
from hypervector.research.sol_range_onset_backward_event_blocks import (
    prepare_backward_event_blocks,
    store_backward_event_blocks,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the explicit immutable event-block command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bars", type=Path, required=True)
    parser.add_argument("--funding", type=Path, required=True)
    parser.add_argument("--start", type=_utc_datetime, required=True)
    parser.add_argument("--end", type=_utc_datetime, required=True)
    parser.add_argument("--max-gap-minutes", type=int, default=30)
    parser.add_argument("--warmup-hours", type=int, default=30)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Verify sources and atomically publish gap-safe replay blocks."""
    args = build_parser().parse_args(argv)
    try:
        bars, _funding = load_verified_sol_backward_inputs(
            bars_path=args.bars,
            funding_path=args.funding,
            start=args.start,
            end=args.end,
        )
        gap_blocks = prepare_gap_safe_blocks(
            bars,
            max_gap_minutes=args.max_gap_minutes,
        )
        event_blocks = prepare_backward_event_blocks(
            gap_blocks,
            warmup_hours=args.warmup_hours,
        )
        manifest = store_backward_event_blocks(
            args.out,
            event_blocks,
            source_evidence=_source_evidence(args.bars, args.funding),
        )
    except (FileExistsError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {"ok": True, "manifest": str(manifest), **file_evidence(manifest)},
            sort_keys=True,
        )
    )
    return 0


def _source_evidence(bars: Path, funding: Path) -> dict[str, object]:
    bars_manifest = bars.parent / "manifest.json"
    funding_manifest = funding.parent / "manifest.json"
    return {
        "bars_path": str(bars.resolve()),
        "bars": file_evidence(bars),
        "bars_manifest": file_evidence(bars_manifest),
        "funding_path": str(funding.resolve()),
        "funding": file_evidence(funding),
        "funding_manifest": file_evidence(funding_manifest),
    }


def _utc_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("timestamp must include a UTC offset")
    return parsed.astimezone(UTC)


if __name__ == "__main__":
    raise SystemExit(main())

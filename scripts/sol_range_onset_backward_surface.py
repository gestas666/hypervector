"""Run the predeclared SOL stop/hold surface on backward validation history."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
import sys
from typing import Sequence

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.sol_range_onset_backward_surface import (
    evaluate_sol_backward_shape_surface,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the immutable backward shape-surface command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bars", type=Path, required=True)
    parser.add_argument("--funding", type=Path, required=True)
    parser.add_argument("--predeclared-surface", type=Path, required=True)
    parser.add_argument("--start", type=_utc, required=True)
    parser.add_argument("--end", type=_utc, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Generate one immutable, execution-incapable robustness surface."""
    args = build_parser().parse_args(argv)
    try:
        report = evaluate_sol_backward_shape_surface(
            bars_path=args.bars,
            funding_path=args.funding,
            predeclared_surface_path=args.predeclared_surface,
            start=args.start,
            end=args.end,
        )
        write_immutable_json(args.out, report)
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
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise argparse.ArgumentTypeError("timestamp must be UTC")
    return parsed.astimezone(UTC)


if __name__ == "__main__":
    raise SystemExit(main())

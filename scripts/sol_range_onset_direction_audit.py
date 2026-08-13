"""Audit direction and block stability of resolved SOL range-onset replays."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.sol_range_onset_direction_audit import (
    audit_sol_range_onset_directions,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the report-only direction-audit command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay", type=Path, action="append", required=True)
    parser.add_argument("--expected-trades", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Generate one immutable no-authority direction audit."""
    args = build_parser().parse_args(argv)
    try:
        report = audit_sol_range_onset_directions(
            tuple(args.replay),
            expected_trades=args.expected_trades,
        )
        write_immutable_json(args.out, report)
    except (FileExistsError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "out": str(args.out),
                "evidence": file_evidence(args.out),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

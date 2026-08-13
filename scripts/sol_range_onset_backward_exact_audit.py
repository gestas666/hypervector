"""Audit four predeclared older SOL exact replay artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.sol_range_onset_backward_exact_audit import (
    audit_backward_exact_blocks,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the declaration-bound report-only audit parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--declaration", type=Path, required=True)
    parser.add_argument("--artifact", type=Path, action="append", required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Validate the four artifacts and write one immutable aggregate report."""
    args = build_parser().parse_args(argv)
    try:
        report = audit_backward_exact_blocks(args.declaration, args.artifact)
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


if __name__ == "__main__":
    raise SystemExit(main())

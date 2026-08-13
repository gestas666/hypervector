"""Generate an immutable cross-era SOL stop-distance reconciliation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.sol_range_onset_stop_reconciliation import (
    reconcile_stop_audits,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the report-only reconciliation command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backward-audit", type=Path, required=True)
    parser.add_argument("--later-audit", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Bind two source audits and write one execution-incapable report."""
    args = build_parser().parse_args(argv)
    try:
        report = reconcile_stop_audits(args.backward_audit, args.later_audit)
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

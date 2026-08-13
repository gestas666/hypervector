"""Preserve creator close/reverse timing as immutable research evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.hypervelocity_creator_close_reverse import (
    creator_close_reverse_evidence,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--positions", type=Path, required=True)
    parser.add_argument("--bars", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def _report(
    positions: pd.DataFrame,
    bars: pd.DataFrame,
    args: argparse.Namespace,
) -> dict[str, object]:
    reconstruction = creator_close_reverse_evidence(positions, bars)
    adverse = int(reconstruction["estimated_outcomes"]["adverse"])
    return {
        "ok": True,
        "experiment": "creator_close_reverse_reconstruction_v1",
        "report_only": True,
        "runtime_strategy_changed": False,
        "exact_exit_fill_available": False,
        "creator_scorecard_reported_losses": 4,
        "estimated_loss_count_matches_scorecard": adverse == 4,
        "source_evidence": {
            "positions": file_evidence(args.positions),
            "bars": file_evidence(args.bars),
        },
        "reconstruction": reconstruction,
        "limitations": [
            "The recorded close second has no exact creator exit fill or PnL.",
            "Hyperliquid close-minute OHLC bounds the estimate but not intraminute fill.",
            "A later opposite position does not prove it caused the prior close.",
        ],
        "falsifier": (
            "Exact creator order logs showing unrelated manual closes, or exact exit "
            "fills that reverse the four adverse classifications."
        ),
    }


def _write(path: Path, report: dict[str, object]) -> None:
    write_immutable_json(path, report)


def main() -> int:
    """Write one immutable creator close/reverse evidence report."""
    args = _parser().parse_args()
    try:
        positions = pd.read_csv(args.positions)
        bars = pd.read_parquet(args.bars)
        _write(args.out, _report(positions, bars, args))
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "out": str(args.out)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

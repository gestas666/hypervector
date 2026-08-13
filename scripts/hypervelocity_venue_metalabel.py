"""Train report-only venue-matched Hypervelocity liquidation challengers."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from hypervector.research.hypervelocity_metalabel_report import (
    assemble_metalabel_dataset,
    generate_metalabel_report,
)


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("timestamp must include a UTC offset")
    return parsed.astimezone(UTC)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--replay", "--recovery", dest="replay", type=Path, required=True
    )
    parser.add_argument("--bars", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--start", type=_utc, required=True)
    parser.add_argument("--end", type=_utc, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--n-splits", type=int, default=3)
    parser.add_argument("--embargo-minutes", type=int, default=60)
    parser.add_argument(
        "--candidate-profile",
        choices=("recovery6", "canonical-pressure", "faithful-stop14"),
        default="recovery6",
    )
    return parser


def main() -> int:
    """Build causal evidence and persist an annotation-only comparison."""
    args = _parser().parse_args()
    try:
        assembly = assemble_metalabel_dataset(
            replay_path=args.replay,
            bars_path=args.bars,
            config_path=args.config,
            data_root=args.data_root,
            start=args.start,
            end=args.end,
            candidate_profile=args.candidate_profile,
        )
        report = generate_metalabel_report(
            assembly=assembly,
            out_path=args.out,
            model_dir=args.model_dir,
            n_splits=args.n_splits,
            embargo_minutes=args.embargo_minutes,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "out": str(args.out),
                "selected_by_mean_log_loss": report["assessment"][
                    "selected_by_mean_log_loss"
                ],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Train five-fold observe-only models on corrected strict-source replay blocks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from hypervector.research.hypervelocity_metalabel_report import (
    generate_metalabel_report,
)
from hypervector.research.hypervelocity_source_metalabel import (
    assemble_source_metalabel_dataset,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay", type=Path, action="append", required=True)
    parser.add_argument("--bars", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--strict-labels", type=Path)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--expected-resolved", type=int, required=True)
    parser.add_argument("--expected-liquidations", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--n-splits", type=int, default=5)
    parser.add_argument("--embargo-minutes", type=int, default=60)
    return parser


def main() -> int:
    """Build immutable evidence and train only report-visible challengers."""
    args = _parser().parse_args()
    try:
        assembly = assemble_source_metalabel_dataset(
            replay_paths=args.replay,
            bars_path=args.bars,
            config_path=args.config,
            data_root=args.data_root,
            expected_resolved=args.expected_resolved,
            expected_liquidations=args.expected_liquidations,
            source_labels_path=args.strict_labels,
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

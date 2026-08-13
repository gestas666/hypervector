"""Attribute Hypervelocity replay outcomes to causal regime and L2 evidence."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from hypervector.research.hypervelocity_attribution_report import (
    generate_attribution_report,
)


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("timestamp must include a UTC offset")
    return parsed.astimezone(UTC)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--bars", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument(
        "--runtime-config",
        type=Path,
        default=Path("configs/hypervelocity_faithful.toml"),
    )
    parser.add_argument("--start", type=_utc, required=True)
    parser.add_argument("--end", type=_utc, required=True)
    parser.add_argument("--candidate", default="single_ema")
    parser.add_argument(
        "--fill-rule",
        choices=("touch", "through", "trade-through"),
        default="trade-through",
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    return parser


def _write_atomic(path: Path, payload: object, *, force: bool) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"output already exists; pass --force to replace: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, indent=2, allow_nan=False) + "\n"
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)


def main() -> int:
    """Generate and atomically publish one report-only attribution artifact."""
    args = _parser().parse_args()
    try:
        report = generate_attribution_report(
            comparison_path=args.comparison,
            bars_path=args.bars,
            data_root=args.data_root,
            runtime_config_path=args.runtime_config,
            start=args.start,
            end=args.end,
            candidate_id=args.candidate,
            fill_rule=args.fill_rule,
        )
        _write_atomic(args.out, report, force=args.force)
    except (OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "out": str(args.out)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

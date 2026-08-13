"""Build the exact report-only v45 variable-sizing candidate snapshot."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.multi_asset_observer_config import with_observer_ledger_root
from hypervector.research.checkpoint_storage import write_atomic_json
from hypervector.research.v45_variable_sizing_snapshot import (
    build_v45_variable_sizing_snapshot,
)

_CONFIG = Path(
    "configs/multi_asset_bidirectional_btc_specialists_growth_sizing_candidate_v45.toml"
)
_LEDGER = Path("data/observe/v45_candidate_shadow/decisions.jsonl")
_OUTPUT = Path("data/runtime/research/v45_variable_sizing_latest.json")


def build_parser() -> argparse.ArgumentParser:
    """Build the no-authority sizing snapshot command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=_CONFIG)
    parser.add_argument("--ledger", type=Path, default=_LEDGER)
    parser.add_argument("--ledger-root", type=Path, default=_LEDGER.parent)
    parser.add_argument("--output", type=Path, default=_OUTPUT)
    return parser


def run(args: argparse.Namespace) -> dict[str, object]:
    """Read one stable ledger prefix and atomically publish its snapshot."""
    config = load_multi_asset_live_config(args.config, mode="observe")
    config = with_observer_ledger_root(config, args.ledger_root)
    rows, source = _ledger_prefix(args.ledger)
    report = build_v45_variable_sizing_snapshot(rows, config)
    report["generated_at_utc"] = datetime.now(tz=UTC).isoformat()
    report["source"] = source
    write_atomic_json(args.output, report)
    return report


def _ledger_prefix(path: Path) -> tuple[list[dict[str, object]], dict[str, object]]:
    if not path.is_file():
        raise FileNotFoundError(f"v45 sizing ledger is missing: {path}")
    content = path.read_bytes()
    rows: list[dict[str, object]] = []
    for number, line in enumerate(content.splitlines(), start=1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"v45 sizing ledger line {number} must be an object")
        rows.append(value)
    source = {
        "path": str(path.resolve()),
        "prefix_bytes": len(content),
        "prefix_sha256": hashlib.sha256(content).hexdigest(),
        "rows": len(rows),
    }
    return rows, source


def main() -> int:
    """Publish the snapshot and print a compact status boundary."""
    report = run(build_parser().parse_args())
    print(
        json.dumps(
            {
                "ok": True,
                "execution_authority": "none",
                "evaluations": report["evaluations"],
                "eligible_candidates": report["eligible_candidates"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

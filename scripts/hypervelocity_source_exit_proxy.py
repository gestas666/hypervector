"""Write provenance-rich tracker-only Hyperliquid exit proxies."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_json
from hypervector.research.hypervelocity_metalabel_report import (
    runtime_observe_contract,
)
from hypervector.research.hypervelocity_reentry_compare import (
    logical_source_positions,
)
from hypervector.research.hypervelocity_source_exit_proxy import (
    build_tracker_exit_proxies,
    summarize_tracker_exit_proxies,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--positions", type=Path, required=True)
    parser.add_argument("--price-context", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--leverage", type=float, default=40.0)
    parser.add_argument("--tolerance-seconds", type=float, default=120.0)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def _json_records(frame: pd.DataFrame) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for row in frame.to_dict("records"):
        record: dict[str, object] = {}
        for key, value in row.items():
            if isinstance(value, pd.Timestamp):
                record[str(key)] = value.isoformat()
            elif pd.isna(value):
                record[str(key)] = None
            else:
                record[str(key)] = value
        output.append(record)
    return output


def _report(args: argparse.Namespace) -> dict[str, object]:
    if not args.positions.is_file():
        raise FileNotFoundError(f"source positions are missing: {args.positions}")
    if not args.price_context.is_file():
        raise FileNotFoundError(
            f"Hyperliquid price context is missing: {args.price_context}"
        )
    logical = logical_source_positions(pd.read_csv(args.positions))
    prices = pd.read_parquet(args.price_context)
    proxies = build_tracker_exit_proxies(
        logical,
        prices,
        leverage=args.leverage,
        tolerance_seconds=args.tolerance_seconds,
    )
    return {
        "ok": True,
        "report_only": True,
        "experiment": "tracker_close_hyperliquid_mark_proxy_v1",
        "source_evidence": {
            "positions": file_evidence(args.positions),
            "price_context": file_evidence(args.price_context),
            "runtime_config": file_evidence(args.config),
        },
        "contract": {
            "leverage": args.leverage,
            "mark_tolerance_seconds": args.tolerance_seconds,
            "backward_mark_role": "causal_observation_before_tracker_close",
            "nearest_mark_role": "noncausal_timestamp_sensitivity_only",
        },
        "summary": summarize_tracker_exit_proxies(proxies),
        "positions": _json_records(proxies),
        "metalabel_policy": runtime_observe_contract(args.config),
        "runtime_strategy_changed": False,
        "limitations": [
            "Tracker disappearance is not an authoritative order or fill timestamp.",
            "Hyperliquid marks may differ from the creator's execution venue.",
            "Nearest marks can occur after disappearance and are sensitivity only.",
            "Gross margin proxies exclude fees, funding, slippage, and partial exits.",
        ],
    }


def main() -> int:
    """Write one immutable report-only source exit proxy artifact."""
    args = _parser().parse_args()
    try:
        if args.out.exists():
            raise FileExistsError(f"source exit proxy output exists: {args.out}")
        args.out.parent.mkdir(parents=True, exist_ok=True)
        write_json(args.out, _report(args))
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "out": str(args.out)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

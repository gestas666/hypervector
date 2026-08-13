#!/usr/bin/env python3
"""Screen a causal confirmed-pivot stop on the frozen source-follow leader."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.hypertrader_source_adapter import (
    load_hyperliquid_candles,
)
from hypervector.research.hypervelocity_stop_counterfactual import (
    evaluate_confirmed_pivot_stops,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-artifact", type=Path, required=True)
    parser.add_argument("--candles", type=Path, action="append", required=True)
    parser.add_argument("--pivot-left-bars", type=int, default=2)
    parser.add_argument("--pivot-right-bars", type=int, default=2)
    parser.add_argument("--pivot-buffer-bps", type=float, default=0.0)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def _experiment_contract() -> dict[str, object]:
    return {
        "candidate": "source_follow_confirmed_pivot_stop",
        "report_only": True,
        "runtime_strategy_changed": False,
        "model_authority": "observe",
        "entry_policy_changed": False,
        "stop_kind": "confirmed_strict_pivot",
        "pivot_left_bars": 2,
        "pivot_right_bars": 2,
        "pivot_buffer_bps": 0.0,
        "stateful_replay_performed": False,
    }


def _validate_source_payload(payload: dict[str, object]) -> None:
    if payload.get("candidate_family") not in {
        "source-follow-only",
        "source-follow-all-day",
    }:
        raise ValueError(
            "source artifact must be the source-follow-only or "
            "source-follow-all-day candidate"
        )
    if payload.get("report_only") is not True:
        raise ValueError("source artifact must be report-only")
    if payload.get("runtime_strategy_changed") is not False:
        raise ValueError("source artifact must not change runtime strategy")
    if payload.get("stop_policy") != "none":
        raise ValueError("source artifact must use the no-stop control")
    expected = {
        "fill_rule": "trade-through",
        "entry_ttl_seconds": 60.0,
        "initial_equity": 10_000.0,
        "allocation_fraction": 0.70,
        "leverage": 40.0,
        "gross_margin_target_pct": 8.0,
    }
    mismatches = [key for key, value in expected.items() if payload.get(key) != value]
    if mismatches:
        raise ValueError(
            "source artifact does not match the frozen leader: " + ", ".join(mismatches)
        )


def _source_payload(path: Path) -> dict[str, object]:
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("source artifact must contain a JSON object")
    _validate_source_payload(value)
    return value


def _lifecycle_frame(payload: dict[str, object], section_name: str) -> pd.DataFrame:
    section = payload.get(section_name)
    if not isinstance(section, dict):
        raise ValueError(f"source artifact section is missing: {section_name}")
    replay = section.get("replay")
    if not isinstance(replay, dict):
        raise ValueError(f"source replay is missing: {section_name}")
    lifecycles = replay.get("lifecycles")
    if not isinstance(lifecycles, list):
        raise ValueError(f"source lifecycles are missing: {section_name}")
    return pd.DataFrame(lifecycles)


def _qualification(
    development: dict[str, object],
    fresh: dict[str, object],
) -> dict[str, object]:
    development_delta = float(development["counterfactual_net_pnl_usd"]) - float(
        development["original_net_pnl_usd"]
    )
    development_improved = development_delta > 0.0
    fresh_has_evidence = int(fresh["filled_lifecycles"]) > 0
    fresh_target_preserved = int(fresh["target_stop_regret"]) == 0
    qualified = development_improved and fresh_has_evidence and fresh_target_preserved
    return {
        "qualified": qualified,
        "development_net_pnl_delta_usd": development_delta,
        "development_improved": development_improved,
        "fresh_has_evidence": fresh_has_evidence,
        "fresh_target_preserved": fresh_target_preserved,
        "next_action": "stateful_l2_replay" if qualified else "reject_candidate",
    }


def _screen(
    bars: pd.DataFrame,
    lifecycles: pd.DataFrame,
    args: argparse.Namespace,
) -> dict[str, object]:
    report = evaluate_confirmed_pivot_stops(
        bars,
        lifecycles,
        left_bars=args.pivot_left_bars,
        right_bars=args.pivot_right_bars,
        buffer_bps=args.pivot_buffer_bps,
    )
    return report.to_dict()


def _report(args: argparse.Namespace) -> dict[str, object]:
    contract = _experiment_contract()
    requested = (
        args.pivot_left_bars,
        args.pivot_right_bars,
        args.pivot_buffer_bps,
    )
    frozen = (
        contract["pivot_left_bars"],
        contract["pivot_right_bars"],
        contract["pivot_buffer_bps"],
    )
    if requested != frozen:
        raise ValueError("first pivot-stop screen is frozen at 2/2 bars and 0 bps")
    payload = _source_payload(args.source_artifact)
    bars = load_hyperliquid_candles(args.candles)
    development = _screen(bars, _lifecycle_frame(payload, "development"), args)
    fresh = _screen(bars, _lifecycle_frame(payload, "fresh_20260727"), args)
    qualification = _qualification(development, fresh)
    return {
        **contract,
        "source_candidate": {
            "upstream_revision": payload.get("upstream_revision"),
            "candidate_family": payload["candidate_family"],
            "fill_rule": payload["fill_rule"],
            "entry_ttl_seconds": payload["entry_ttl_seconds"],
            "maximum_signal_range_bps": payload.get("maximum_signal_range_bps"),
        },
        "source_evidence": {
            "artifact": file_evidence(args.source_artifact),
            "candles": [file_evidence(path) for path in args.candles],
        },
        "development": development,
        "fresh_20260727": fresh,
        "qualification": qualification,
        "limitations": [
            "This screen preserves original fills and is not a stateful replay.",
            "Full-bar stop ordering cannot resolve entry or outcome partial minutes.",
            "The fresh window contains only one filled lifecycle.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    """Write one immutable report-only pivot-stop screen."""
    args = _parser().parse_args(argv)
    if args.out.exists():
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_immutable_json(args.out, _report(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

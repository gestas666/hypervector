#!/usr/bin/env python3
"""Replay a frozen BTC allocation/leverage surface on authentic maker evidence."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import importlib.util
from pathlib import Path
from types import ModuleType

import pandas as pd

from hypervector.data.oxa_storage import write_immutable_json
from hypervector.research.hypertrader_label_evidence import load_label_evidence
from hypervector.research.hypertrader_source_adapter import (
    selective_recipe_maker_decisions,
)
from hypervector.research.maker_replay_context_io import context_coverage_report
from hypervector.research.maker_replay_stream import replay_maker_order_grid_chunks
from hypervector.research.maker_risk_surface import (
    ALLOCATION_FRACTIONS,
    LEVERAGES,
    risk_surface_candidate_configs,
    selected_peak_candidate_configs,
    selected_sizing_candidate_configs,
)
from hypervector.research.replay_window import (
    add_replay_window_arguments,
    partition_replay_events,
    validate_replay_window,
)
from hypervector.research.research_evidence_source import MakerReplayEvidence

_CANDIDATE_FAMILY = "btc_allocation_leverage_surface_v1"
_PEAK_CANDIDATE_FAMILY = "btc_selected_peak_surface_v1"
_SIZING_CANDIDATE_FAMILY = "btc_selected_sizing_surface_v1"
_ENTRY_FAMILIES = (
    "source-follow-session-06-15-confidence-70",
    "source-follow-all-day-confidence-70",
)


def _load_source_replay() -> ModuleType:
    path = Path(__file__).with_name("hypervelocity_hypertrader_maker_replay.py")
    spec = importlib.util.spec_from_file_location("source_replay_helpers", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"source replay helpers could not be loaded: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


source_replay = _load_source_replay()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--labels-metadata", type=Path)
    parser.add_argument("--candles", action="append", type=Path, default=[])
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--research-database", type=Path)
    parser.add_argument(
        "--initial-equity", type=source_replay._positive_equity, default=15_000.0
    )
    add_replay_window_arguments(parser)
    parser.add_argument(
        "--development-price-context", action="append", type=Path, required=True
    )
    parser.add_argument(
        "--development-funding-context", action="append", type=Path, required=True
    )
    parser.add_argument(
        "--fresh-price-context", action="append", type=Path, required=True
    )
    parser.add_argument(
        "--fresh-funding-context", action="append", type=Path, required=True
    )
    parser.add_argument(
        "--entry-eligibility-seconds",
        type=source_replay._positive_seconds,
        default=60.0,
    )
    parser.add_argument(
        "--maximum-signal-range-bps",
        type=source_replay._positive_seconds,
        default=100.0,
    )
    parser.add_argument(
        "--fill-rule",
        choices=("touch", "through", "trade-through"),
        default="trade-through",
    )
    parser.add_argument(
        "--surface-mode",
        choices=("risk-surface", "selected-peak", "selected-sizing"),
        default="risk-surface",
    )
    parser.add_argument(
        "--entry-family",
        choices=_ENTRY_FAMILIES,
        default="source-follow-session-06-15-confidence-70",
    )
    parser.add_argument("--out", type=Path, required=True)
    return parser


def _surface_contract(args: argparse.Namespace) -> dict[str, object]:
    if args.surface_mode == "selected-peak":
        return {
            "candidate_family": _PEAK_CANDIDATE_FAMILY,
            "allocation_fractions": [0.5, 0.7],
            "leverages": [30.0, 40.0],
            "peak_protection": {"activation_margin_pct": 7.0, "lock_ratio": 0.55},
        }
    if args.surface_mode == "selected-sizing":
        return {
            "candidate_family": _SIZING_CANDIDATE_FAMILY,
            "allocation_fractions": [0.5, 0.7],
            "leverages": [30.0, 40.0],
            "peak_protection": False,
        }
    return {
        "candidate_family": _CANDIDATE_FAMILY,
        "allocation_fractions": list(ALLOCATION_FRACTIONS),
        "leverages": list(LEVERAGES),
        "peak_protection": False,
    }


def _experiment_contract(args: argparse.Namespace) -> dict[str, object]:
    return {
        **_surface_contract(args),
        "entry_family": args.entry_family,
        "report_only": True,
        "runtime_strategy_changed": False,
        "selection_is_promotion": False,
        "model_authority": "observe",
        "initial_equity": args.initial_equity,
        "gross_margin_target_pct": 8.0,
        "margin_mode": "isolated",
        "one_position_per_symbol": True,
        "entry": f"post-only maker {args.fill_rule}",
        "fill_rule": args.fill_rule,
        "entry_ttl_seconds": args.entry_eligibility_seconds,
        "maximum_signal_range_bps": args.maximum_signal_range_bps,
        "same_direction_reentry_policy": "regime_reset",
        "daily_profit_lockout": False,
    }


def _run_window(
    events: pd.DataFrame,
    evidence: MakerReplayEvidence,
    price_context: Sequence[Path],
    funding_context: Sequence[Path],
    args: argparse.Namespace,
) -> dict[str, object]:
    decisions = selective_recipe_maker_decisions(
        events,
        entry_eligibility_seconds=args.entry_eligibility_seconds,
    )
    context = source_replay._load_context_parts(price_context, funding_context)
    config_factory = {
        "risk-surface": risk_surface_candidate_configs,
        "selected-peak": selected_peak_candidate_configs,
        "selected-sizing": selected_sizing_candidate_configs,
    }[args.surface_mode]
    configs = config_factory(
        initial_equity=args.initial_equity,
        entry_eligibility_seconds=args.entry_eligibility_seconds,
        fill_rule=args.fill_rule,
    )
    reports = replay_maker_order_grid_chunks(
        evidence.chunks,
        decisions,
        configs,
        context=context,
    )
    candidates: dict[str, object] = {}
    for name, report in reports.items():
        config = configs[name]
        payload = report.to_dict()
        candidates[name] = {
            "margin_fraction": config.margin_fraction,
            "leverage": config.leverage,
            "target_margin_pct": config.target_margin_pct,
            "peak_protection_activation_margin_pct": (
                config.peak_protection_activation_margin_pct
            ),
            "peak_protection_lock_ratio": config.peak_protection_lock_ratio,
            "event_outcomes": source_replay._event_outcomes(events, payload),
            "replay": payload,
        }
    return {
        "events": len(events),
        "archive": evidence.summary,
        "context": context_coverage_report(context),
        "candidates": candidates,
    }


def _report(args: argparse.Namespace) -> dict[str, object]:
    window = validate_replay_window(args)
    label_evidence = load_label_evidence(args.labels, args.labels_metadata)
    events = source_replay._events(
        args.labels,
        args.candles,
        args.maximum_signal_range_bps,
        args.entry_family,
    )
    development, fresh = partition_replay_events(events, args)
    development_evidence, fresh_evidence = source_replay._window_evidence(args)
    return {
        **_experiment_contract(args),
        "upstream_revision": label_evidence.revision,
        "replay_window": window.to_dict(),
        "source_evidence": source_replay._source_evidence(args, label_evidence),
        "development": _run_window(
            development,
            development_evidence,
            args.development_price_context,
            args.development_funding_context,
            args,
        ),
        "fresh": _run_window(
            fresh,
            fresh_evidence,
            args.fresh_price_context,
            args.fresh_funding_context,
            args,
        ),
        "limitations": [
            "Public trade-through cannot identify private queue rank.",
            "Gap-free blocks reset portfolio equity independently.",
            "The surface is development evidence and cannot alter runtime.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    """Write one immutable report-only maker risk-surface artifact."""
    args = _parser().parse_args(argv)
    write_immutable_json(args.out, _report(args))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Compare a 24h hold with target-or-liquidation on exact short signals."""

from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType

import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.maker_replay_context import MakerReplayContext
from hypervector.research.maker_replay_context_io import (
    context_coverage_report,
    load_verified_replay_context_parts,
)
from hypervector.research.maker_replay_models import (
    FillRule,
    MakerReplayConfig,
    MakerReplayReport,
)
from hypervector.research.maker_replay_stream import (
    replay_maker_order_decision_grid_chunks,
)
from hypervector.research.research_evidence_source import maker_replay_evidence


def _load_short_surface() -> ModuleType:
    path = Path(__file__).with_name("hypervelocity_short_risk_surface.py")
    spec = importlib.util.spec_from_file_location("short_surface_helpers", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"short risk-surface helpers could not be loaded: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


short_surface = _load_short_surface()
shared_replay = short_surface.shared_replay


def _parser() -> argparse.ArgumentParser:
    parser = short_surface._parser()
    parser.description = __doc__
    return parser


def _configs(
    initial_equity: float,
    fill_rule: FillRule,
) -> dict[str, MakerReplayConfig]:
    """Return only the frozen hold-duration alternatives."""
    control = short_surface._config(initial_equity, fill_rule, 0.35, 30.0)
    return {
        "max_hold_24h_control": control,
        "target_or_liquidation": replace(control, maximum_hold_seconds=None),
    }


def _contract(initial_equity: float, fill_rule: FillRule) -> dict[str, object]:
    """Return the immutable report-only experiment contract."""
    return {
        "candidate": "source_follow_short_maximum_hold_v2",
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "model_authority": "observe",
        "signal_changed": False,
        "candidate_count": 2,
        "candidate_difference": "maximum_hold_seconds_only",
        "initial_equity": initial_equity,
        "allocation_fraction": 0.35,
        "leverage": 30.0,
        "gross_margin_target_pct": 8.0,
        "entry_ttl_seconds": 60.0,
        "fill_rule": fill_rule,
    }


def _decision_grid(decisions: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Clear the source-level deadline only for the no-timeout candidate."""
    target_or_liquidation = decisions.copy()
    target_or_liquidation["maximum_hold_seconds"] = None
    return {
        "max_hold_24h_control": decisions,
        "target_or_liquidation": target_or_liquidation,
    }


def _comparison(
    reports: dict[str, MakerReplayReport],
) -> dict[str, dict[str, float | int]]:
    control = reports["max_hold_24h_control"]
    return {
        name: {
            "final_equity_delta": report.final_equity - control.final_equity,
            "maximum_drawdown_pct_delta": (
                report.maximum_drawdown_pct - control.maximum_drawdown_pct
            ),
            "submitted_entries_delta": (
                report.submitted_entries - control.submitted_entries
            ),
            "liquidations_delta": report.liquidations - control.liquidations,
            "time_exits_delta": report.time_exits - control.time_exits,
        }
        for name, report in reports.items()
    }


def _payload(
    args: argparse.Namespace,
    configs: dict[str, MakerReplayConfig],
    reports: dict[str, MakerReplayReport],
    market_evidence: dict[str, object],
    context: MakerReplayContext,
    context_parts: list[tuple[Path, Path]],
) -> dict[str, object]:
    return {
        "schema": "hypervelocity_short_maximum_hold_v2",
        "report_only": True,
        "experiment_contract": _contract(args.initial_equity, args.fill_rule),
        "candidate_configs": {name: asdict(config) for name, config in configs.items()},
        "summaries": {
            name: shared_replay._summary(report) for name, report in reports.items()
        },
        "comparison": _comparison(reports),
        "event_replays": {name: report.to_dict() for name, report in reports.items()},
        "market_evidence": market_evidence,
        "context_evidence": context_coverage_report(context),
        "source_evidence": {
            "bars": shared_replay._path_evidence(args.bars),
            "labels": shared_replay._path_evidence(args.labels),
            "labels_metadata": shared_replay._path_evidence(args.labels_metadata),
            "control_artifact": {
                "path": str(args.control_artifact.resolve()),
                **file_evidence(args.control_artifact),
            },
            "price_context": [
                shared_replay._path_evidence(path) for path, _ in context_parts
            ],
            "funding_context": [
                shared_replay._path_evidence(path) for _, path in context_parts
            ],
        },
        "limitations": [
            "The 24h time exit in this same interval motivated the comparison.",
            "A position unresolved at the data boundary is right-censored.",
            "Public trade-through cannot identify private maker queue rank.",
            "No candidate changes runtime or ML execution authority.",
            "A v1 artifact was invalid because both arms inherited source deadlines.",
        ],
    }


def _report(args: argparse.Namespace) -> dict[str, object]:
    bars = shared_replay.load_minute_bars(args.bars)
    shared_replay._validate_inputs(args, bars)
    labels = shared_replay._load_labels(args)
    decisions = shared_replay._decision_grid(args, bars, labels).short_control
    context_parts = shared_replay._context_parts(args)
    context = load_verified_replay_context_parts(context_parts)
    configs = _configs(args.initial_equity, args.fill_rule)
    evidence = maker_replay_evidence(
        args.data_root,
        "BTC",
        args.start,
        args.end,
        include_trades=args.fill_rule == "trade-through",
        database_path=args.research_database,
    )
    reports = replay_maker_order_decision_grid_chunks(
        evidence.chunks,
        _decision_grid(decisions),
        configs,
        context=context,
    )
    expected = short_surface._control_replay(args.control_artifact)
    short_surface._verify_control_parity(
        reports["max_hold_24h_control"].to_dict(),
        expected,
    )
    return _payload(args, configs, reports, evidence.summary, context, context_parts)


def main(argv: list[str] | None = None) -> int:
    """Write one immutable report-only maximum-hold comparison."""
    args = _parser().parse_args(argv)
    try:
        write_immutable_json(args.out, _report(args))
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "out": str(args.out.resolve())}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

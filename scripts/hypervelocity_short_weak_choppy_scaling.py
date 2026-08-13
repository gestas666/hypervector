#!/usr/bin/env python3
"""Compare uniform and weak/choppy half-sized shorts on exact venue tape."""

from __future__ import annotations

import argparse
from dataclasses import asdict
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
from hypervector.research.source_follow_risk_scaling import (
    annotate_maker_decisions_with_source_sizing,
)


def _load_risk_surface() -> ModuleType:
    path = Path(__file__).with_name("hypervelocity_short_risk_surface.py")
    spec = importlib.util.spec_from_file_location("short_risk_helpers", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"short risk helpers could not be loaded: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


risk_surface = _load_risk_surface()
shared_replay = risk_surface.shared_replay


def _parser() -> argparse.ArgumentParser:
    parser = risk_surface._parser()
    parser.description = __doc__
    return parser


def _configs(
    initial_equity: float,
    fill_rule: FillRule,
) -> dict[str, MakerReplayConfig]:
    """Return identical risk contracts for decision-only sizing comparison."""
    config = risk_surface._config(initial_equity, fill_rule, 0.35, 30.0)
    return {"uniform_control": config, "weak_choppy_half": config}


def _contract(initial_equity: float, fill_rule: FillRule) -> dict[str, object]:
    """Return the bounded report-only sizing experiment contract."""
    return {
        "candidate": "source_follow_short_weak_choppy_scaling_v1",
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "model_authority": "observe",
        "signal_changed": False,
        "initial_equity": initial_equity,
        "allocation_fraction": 0.35,
        "leverage": 30.0,
        "gross_margin_target_pct": 8.0,
        "maximum_hold_seconds": 86_400.0,
        "fill_rule": fill_rule,
        "weak_choppy_allocation_multiplier": 0.5,
        "parameter_selection_allowed": False,
    }


def _decision_grids(
    uniform: pd.DataFrame,
    labels: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    """Return signal-identical control and causal sizing annotations."""
    scaled = annotate_maker_decisions_with_source_sizing(uniform, labels)
    return {"uniform_control": uniform, "weak_choppy_half": scaled}


def _summary(report: MakerReplayReport) -> dict[str, object]:
    return shared_replay._summary(report)


def _comparison(reports: dict[str, MakerReplayReport]) -> dict[str, object]:
    control = reports["uniform_control"]
    candidate = reports["weak_choppy_half"]
    return {
        "candidate_minus_control_final_equity": (
            candidate.final_equity - control.final_equity
        ),
        "candidate_minus_control_maximum_drawdown_pct": (
            candidate.maximum_drawdown_pct - control.maximum_drawdown_pct
        ),
        "submitted_entries_delta": (
            candidate.submitted_entries - control.submitted_entries
        ),
        "entry_fills_delta": candidate.entry_fills - control.entry_fills,
        "target_completions_delta": sum(
            trade.status == "target_completed" for trade in candidate.trades
        )
        - sum(trade.status == "target_completed" for trade in control.trades),
        "liquidations_delta": candidate.liquidations - control.liquidations,
    }


def _sizing_counts(decisions: pd.DataFrame) -> dict[str, int]:
    entries = decisions["entry_direction"].isin(("long", "short"))
    multipliers = decisions.loc[entries, "entry_allocation_multiplier"]
    return {
        "half_size": int(multipliers.eq(0.5).sum()),
        "full_size": int(multipliers.eq(1.0).sum()),
    }


def _payload(
    args: argparse.Namespace,
    configs: dict[str, MakerReplayConfig],
    decisions: dict[str, pd.DataFrame],
    reports: dict[str, MakerReplayReport],
    market_evidence: dict[str, object],
    context: MakerReplayContext,
    context_parts: list[tuple[Path, Path]],
) -> dict[str, object]:
    return {
        "schema": "hypervelocity_short_weak_choppy_scaling_v1",
        "report_only": True,
        "experiment_contract": _contract(args.initial_equity, args.fill_rule),
        "candidate_configs": {name: asdict(value) for name, value in configs.items()},
        "source_sizing": _sizing_counts(decisions["weak_choppy_half"]),
        "summaries": {name: _summary(report) for name, report in reports.items()},
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
            "This subtype sizing rule was selected on earlier historical evidence.",
            "The recent interval is diagnostic rather than independent holdout evidence.",
            "Public trade-through cannot identify private maker queue rank.",
            "No candidate changes runtime or ML execution authority.",
        ],
    }


def _report(args: argparse.Namespace) -> dict[str, object]:
    bars = shared_replay.load_minute_bars(args.bars)
    shared_replay._validate_inputs(args, bars)
    labels = shared_replay._load_labels(args)
    uniform = shared_replay._decision_grid(args, bars, labels).short_control
    decisions = _decision_grids(uniform, labels)
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
        decisions,
        configs,
        context=context,
    )
    control = reports["uniform_control"].to_dict()
    risk_surface._verify_control_parity(
        control,
        risk_surface._control_replay(args.control_artifact),
    )
    return _payload(
        args,
        configs,
        decisions,
        reports,
        evidence.summary,
        context,
        context_parts,
    )


def main(argv: list[str] | None = None) -> int:
    """Write one immutable report-only weak/choppy sizing comparison."""
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

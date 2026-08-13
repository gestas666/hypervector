#!/usr/bin/env python3
"""Compare all-day and frozen 06:00-15:00 UTC shorts on exact venue tape."""

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
from hypervector.research.hypertrader_source_adapter import (
    resample_hyperliquid_5m,
)
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
from hypervector.research.shared_direction_portfolio import (
    build_shared_btc_decision_grid,
)
from hypervector.research.source_follow_portfolio_artifact import (
    select_source_follow_signals,
)
from hypervector.research.source_follow_portfolio_models import SourceSignal

_SESSION_START_HOUR = 6
_SESSION_END_HOUR = 15


def _load_risk_surface() -> ModuleType:
    path = Path(__file__).with_name("hypervelocity_short_risk_surface.py")
    spec = importlib.util.spec_from_file_location("short_session_helpers", path)
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
    """Return identical risk contracts for signal-window comparison."""
    config = risk_surface._config(initial_equity, fill_rule, 0.35, 30.0)
    return {"all_day_control": config, "session_06_15": config}


def _contract(initial_equity: float, fill_rule: FillRule) -> dict[str, object]:
    """Return the frozen report-only session experiment contract."""
    return {
        "candidate": "source_follow_short_session_06_15_v1",
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "model_authority": "observe",
        "session_utc": "[06:00,15:00)",
        "initial_equity": initial_equity,
        "allocation_fraction": 0.35,
        "leverage": 30.0,
        "gross_margin_target_pct": 8.0,
        "maximum_hold_seconds": 86_400.0,
        "fill_rule": fill_rule,
        "parameter_selection_allowed": False,
    }


def _session_signals(signals: tuple[SourceSignal, ...]) -> tuple[SourceSignal, ...]:
    """Retain the previously frozen half-open UTC source session."""
    return tuple(
        signal
        for signal in signals
        if _SESSION_START_HOUR
        <= pd.Timestamp(signal.decision_time_utc).hour
        < _SESSION_END_HOUR
    )


def _signal_bars(minute_bars: pd.DataFrame) -> pd.DataFrame:
    return resample_hyperliquid_5m(minute_bars)


def _empty_long_decisions() -> pd.DataFrame:
    return pd.DataFrame(
        {"entry_direction": pd.Series(dtype=object)},
        index=pd.DatetimeIndex([], tz="UTC"),
    )


def _decision_grids(
    args: argparse.Namespace,
    bars: pd.DataFrame,
    labels: pd.DataFrame,
) -> tuple[dict[str, pd.DataFrame], dict[str, int]]:
    signals = select_source_follow_signals(labels, bars, args.start, args.end)
    session = _session_signals(signals)
    empty_longs = _empty_long_decisions()
    all_day_grid = build_shared_btc_decision_grid(
        signals,
        empty_longs,
        start=args.start,
        end=args.end,
    )
    session_grid = build_shared_btc_decision_grid(
        session,
        empty_longs,
        start=args.start,
        end=args.end,
    )
    return (
        {
            "all_day_control": all_day_grid.short_control,
            "session_06_15": session_grid.short_control,
        },
        {"all_day": len(signals), "session_06_15": len(session)},
    )


def _comparison(reports: dict[str, MakerReplayReport]) -> dict[str, object]:
    control = reports["all_day_control"]
    candidate = reports["session_06_15"]
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


def _payload(
    args: argparse.Namespace,
    configs: dict[str, MakerReplayConfig],
    signal_counts: dict[str, int],
    reports: dict[str, MakerReplayReport],
    market_evidence: dict[str, object],
    context: MakerReplayContext,
    context_parts: list[tuple[Path, Path]],
) -> dict[str, object]:
    return {
        "schema": "hypervelocity_short_session_replay_v1",
        "report_only": True,
        "experiment_contract": _contract(args.initial_equity, args.fill_rule),
        "candidate_configs": {name: asdict(value) for name, value in configs.items()},
        "signal_counts": signal_counts,
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
            "The 06:00-15:00 UTC window was selected on older development data.",
            "Creator waking hours can confound a true market-session effect.",
            "Public trade-through cannot identify private maker queue rank.",
            "No candidate changes runtime or ML execution authority.",
        ],
    }


def _report(args: argparse.Namespace) -> dict[str, object]:
    minute_bars = shared_replay.load_minute_bars(args.bars)
    shared_replay._validate_inputs(args, minute_bars)
    bars = _signal_bars(minute_bars)
    labels = shared_replay._load_labels(args)
    decisions, signal_counts = _decision_grids(args, bars, labels)
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
    risk_surface._verify_control_parity(
        reports["all_day_control"].to_dict(),
        risk_surface._control_replay(args.control_artifact),
    )
    return _payload(
        args,
        configs,
        signal_counts,
        reports,
        evidence.summary,
        context,
        context_parts,
    )


def main(argv: list[str] | None = None) -> int:
    """Write one immutable all-day versus source-session comparison."""
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

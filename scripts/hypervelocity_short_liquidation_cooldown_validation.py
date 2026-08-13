#!/usr/bin/env python3
"""Validate frozen short liquidation cooldowns on an older exact interval."""

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


def _load_cooldown_surface() -> ModuleType:
    path = Path(__file__).with_name("hypervelocity_short_liquidation_cooldown.py")
    spec = importlib.util.spec_from_file_location("cooldown_surface_helpers", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cooldown-surface helpers could not be loaded: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cooldown_surface = _load_cooldown_surface()
shared_replay = cooldown_surface.shared_replay


def _parser() -> argparse.ArgumentParser:
    parser = shared_replay._parser()
    parser.description = __doc__
    parser.add_argument("--development-artifact", type=Path, required=True)
    return parser


def _configs(
    initial_equity: float,
    fill_rule: FillRule,
) -> dict[str, MakerReplayConfig]:
    """Return only the frozen 20x control and cooldown candidates."""
    source = cooldown_surface._configs(initial_equity, fill_rule)
    names = (
        "alloc35_lev20_control",
        "alloc35_lev20_lq_cd48h",
        "alloc35_lev20_lq_cd72h",
    )
    return {name: source[name] for name in names}


def _contract(initial_equity: float, fill_rule: FillRule) -> dict[str, object]:
    """Return the immutable validation contract."""
    return {
        "candidate": "source_follow_short_liquidation_cooldown_validation_v1",
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "model_authority": "observe",
        "signal_changed": False,
        "parameter_selection_allowed": False,
        "candidate_count": 3,
        "initial_equity": initial_equity,
        "gross_margin_target_pct": 8.0,
        "maximum_hold_seconds": 86_400.0,
        "entry_ttl_seconds": 60.0,
        "fill_rule": fill_rule,
        "cooldown_scope": "same_direction_after_liquidation_only",
        "blocked_signal_policy": "consume_without_delayed_submission",
    }


def _validate_development_artifact(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"development artifact is missing: {path}")
    payload: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("development artifact must contain a JSON object")
    if payload.get("schema") != "hypervelocity_short_liquidation_cooldown_v1":
        raise ValueError("development artifact has an unexpected schema")


def _comparison(
    reports: dict[str, MakerReplayReport],
) -> dict[str, dict[str, float | int]]:
    control = reports["alloc35_lev20_control"]
    return {
        name: {
            "final_equity_delta": report.final_equity - control.final_equity,
            "maximum_drawdown_pct_delta": (
                report.maximum_drawdown_pct - control.maximum_drawdown_pct
            ),
            "submitted_entries_delta": report.submitted_entries
            - control.submitted_entries,
            "liquidations_delta": report.liquidations - control.liquidations,
        }
        for name, report in reports.items()
    }


def _validate_inputs(args: argparse.Namespace, bars: pd.DataFrame) -> None:
    shared_replay._validate_inputs(args, bars)
    if args.initial_equity != 15_000.0:
        raise ValueError("validation initial equity is frozen at 15000")
    _validate_development_artifact(args.development_artifact)


def _payload(
    args: argparse.Namespace,
    configs: dict[str, MakerReplayConfig],
    reports: dict[str, MakerReplayReport],
    market_evidence: dict[str, object],
    context: MakerReplayContext,
    context_parts: list[tuple[Path, Path]],
) -> dict[str, object]:
    return {
        "schema": "hypervelocity_short_liquidation_cooldown_validation_v1",
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
            "development_artifact": {
                "path": str(args.development_artifact.resolve()),
                **file_evidence(args.development_artifact),
            },
            "price_context": [
                shared_replay._path_evidence(path) for path, _ in context_parts
            ],
            "funding_context": [
                shared_replay._path_evidence(path) for _, path in context_parts
            ],
        },
        "limitations": [
            "The interval did not select cooldown duration but selected source logic.",
            "Public trade-through cannot identify private maker queue rank.",
            "Empty archive hours can make execution economics inconclusive.",
            "No candidate changes runtime or ML execution authority.",
        ],
    }


def _report(args: argparse.Namespace) -> dict[str, object]:
    bars = shared_replay.load_minute_bars(args.bars)
    _validate_inputs(args, bars)
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
        {name: decisions for name in configs},
        configs,
        context=context,
    )
    return _payload(args, configs, reports, evidence.summary, context, context_parts)


def main(argv: list[str] | None = None) -> int:
    """Write one immutable report-only independent cooldown validation."""
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

#!/usr/bin/env python3
"""Replay bounded post-liquidation cooldowns on exact venue tape."""

from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType

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


def _with_cooldown(
    config: MakerReplayConfig,
    cooldown_seconds: float,
) -> MakerReplayConfig:
    return replace(
        config,
        liquidation_reentry_cooldown_seconds=cooldown_seconds,
    )


def _configs(
    initial_equity: float,
    fill_rule: FillRule,
) -> dict[str, MakerReplayConfig]:
    """Return the predeclared liquidation-cooldown surface."""
    lev30 = short_surface._config(initial_equity, fill_rule, 0.35, 30.0)
    lev20 = short_surface._config(initial_equity, fill_rule, 0.35, 20.0)
    return {
        "alloc35_lev30_control": lev30,
        "alloc35_lev30_lq_cd48h": _with_cooldown(lev30, 172_800.0),
        "alloc35_lev20_control": lev20,
        "alloc35_lev20_lq_cd48h": _with_cooldown(lev20, 172_800.0),
        "alloc35_lev20_lq_cd72h": _with_cooldown(lev20, 259_200.0),
    }


def _contract(initial_equity: float, fill_rule: FillRule) -> dict[str, object]:
    """Return the immutable report-only experiment contract."""
    return {
        "candidate": "source_follow_short_liquidation_cooldown_v1",
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "model_authority": "observe",
        "signal_changed": False,
        "candidate_count": 5,
        "initial_equity": initial_equity,
        "gross_margin_target_pct": 8.0,
        "maximum_hold_seconds": 86_400.0,
        "entry_ttl_seconds": 60.0,
        "fill_rule": fill_rule,
        "cooldown_scope": "same_direction_after_liquidation_only",
        "blocked_signal_policy": "consume_without_delayed_submission",
    }


def _control_replays(path: Path) -> dict[str, dict[str, object]]:
    if not path.is_file():
        raise FileNotFoundError(f"risk-surface control artifact is missing: {path}")
    payload: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("risk-surface control artifact must contain a JSON object")
    replays = payload.get("event_replays")
    if not isinstance(replays, dict):
        raise ValueError("risk-surface control artifact is missing event_replays")
    expected: dict[str, dict[str, object]] = {}
    for name in ("alloc35_lev30_control", "alloc35_lev20"):
        replay = replays.get(name)
        if not isinstance(replay, dict):
            raise ValueError(f"risk-surface control artifact is missing {name}")
        expected[name] = replay
    return expected


def _verify_controls(
    reports: dict[str, MakerReplayReport],
    expected: dict[str, dict[str, object]],
) -> None:
    short_surface._verify_control_parity(
        reports["alloc35_lev30_control"].to_dict(),
        expected["alloc35_lev30_control"],
    )
    short_surface._verify_control_parity(
        reports["alloc35_lev20_control"].to_dict(),
        expected["alloc35_lev20"],
    )


def _comparison(
    reports: dict[str, MakerReplayReport],
) -> dict[str, dict[str, float | int]]:
    result: dict[str, dict[str, float | int]] = {}
    for name, report in reports.items():
        control_name = (
            "alloc35_lev30_control" if "lev30" in name else "alloc35_lev20_control"
        )
        control = reports[control_name]
        result[name] = {
            "final_equity_delta": report.final_equity - control.final_equity,
            "maximum_drawdown_pct_delta": (
                report.maximum_drawdown_pct - control.maximum_drawdown_pct
            ),
            "submitted_entries_delta": (
                report.submitted_entries - control.submitted_entries
            ),
            "liquidations_delta": report.liquidations - control.liquidations,
        }
    return result


def _payload(
    args: argparse.Namespace,
    configs: dict[str, MakerReplayConfig],
    reports: dict[str, MakerReplayReport],
    market_evidence: dict[str, object],
    context: MakerReplayContext,
    context_parts: list[tuple[Path, Path]],
) -> dict[str, object]:
    return {
        "schema": "hypervelocity_short_liquidation_cooldown_v1",
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
            "The recent liquidation cluster motivated this same-window experiment.",
            "Public trade-through cannot identify private maker queue rank.",
            "A profitable cooldown requires independent validation without retuning.",
            "No candidate changes runtime or ML execution authority.",
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
        {name: decisions for name in configs},
        configs,
        context=context,
    )
    _verify_controls(reports, _control_replays(args.control_artifact))
    return _payload(args, configs, reports, evidence.summary, context, context_parts)


def main(argv: list[str] | None = None) -> int:
    """Write one immutable report-only liquidation-cooldown comparison."""
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

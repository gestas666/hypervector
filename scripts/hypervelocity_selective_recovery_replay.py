"""Replay the canonical Recipe C recovery-long hypothesis report-only."""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import UTC, datetime
import json
from pathlib import Path
import sys

import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_json
from hypervector.regime.classifier import classify_timeframe
from hypervector.regime.composite import classify_multitimeframe
from hypervector.research.hypervelocity_metalabel_report import (
    runtime_observe_contract,
)
from hypervector.research.hypervelocity_selective_recipe import (
    build_selective_recipe_events,
    load_selective_recipe_bars,
    selective_recipe_replay_inputs,
)
from hypervector.research.maker_replay_context_io import (
    context_coverage_report,
    load_verified_replay_context,
)
from hypervector.research.maker_replay_models import FillRule, MakerReplayConfig
from hypervector.research.maker_replay_stream import replay_maker_order_chunks
from hypervector.research.research_evidence_source import maker_replay_evidence
from hypervector.strategies.hypervelocity_profile import load_hypervelocity_profile

_RECOVERY_CANDIDATE = "c_1m_recovery_in_5m_down"


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("timestamp must include a UTC offset")
    return parsed.astimezone(UTC)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bars", action="append", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--research-database", type=Path)
    parser.add_argument("--start", type=_utc, required=True)
    parser.add_argument("--end", type=_utc, required=True)
    parser.add_argument("--price-context", type=Path, required=True)
    parser.add_argument("--funding-context", type=Path, required=True)
    parser.add_argument("--initial-equity", type=float, default=10_000.0)
    parser.add_argument(
        "--fill-rule",
        choices=("touch", "through", "trade-through"),
        required=True,
    )
    parser.add_argument("--out", type=Path, required=True)
    return parser


def _recovery_inputs(
    decisions: pd.DataFrame,
    raw_1m: pd.DataFrame,
    *,
    initial_equity: float,
    fill_rule: FillRule,
) -> tuple[pd.DataFrame, MakerReplayConfig, int]:
    events = build_selective_recipe_events(decisions, raw_1m)
    grids, configs = selective_recipe_replay_inputs(
        decisions,
        events,
        initial_equity=initial_equity,
    )
    event_count = int(
        events["candidate_id"].eq("c_1m_trend_up_recovery_in_5m_down").sum()
    )
    return (
        grids[_RECOVERY_CANDIDATE],
        replace(configs[_RECOVERY_CANDIDATE], fill_rule=fill_rule),
        event_count,
    )


def _replay_contract(args: argparse.Namespace) -> dict[str, object]:
    return {
        "candidate": _RECOVERY_CANDIDATE,
        "initial_equity": args.initial_equity,
        "allocation_fraction": 0.70,
        "leverage": 40.0,
        "gross_margin_target_pct": 8.0,
        "maximum_hold_seconds": 86_400.0,
        "entry_ttl_seconds": 300.0,
        "reentry_cooldown_seconds": 60.0,
        "same_direction_reentry_policy": "regime_reset",
        "fill_rule": args.fill_rule,
        "stop_policy": "none",
    }


def _classified_inputs(
    args: argparse.Namespace,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    bars = load_selective_recipe_bars(*args.bars)
    profile = load_hypervelocity_profile(args.config)
    decisions = classify_multitimeframe(bars, config=profile.regime_config)
    raw_1m = classify_timeframe(bars, config=profile.regime_config)
    return decisions, raw_1m


def _source_evidence(args: argparse.Namespace) -> dict[str, object]:
    return {
        "bars": [file_evidence(path) for path in args.bars],
        "runtime_config": file_evidence(args.config),
        "price_context": file_evidence(args.price_context),
        "funding_context": file_evidence(args.funding_context),
    }


def _execute_replay(
    args: argparse.Namespace,
    decisions: pd.DataFrame,
    config: MakerReplayConfig,
) -> tuple[dict[str, object], dict[str, object]]:
    include_trades = args.fill_rule == "trade-through"
    evidence = maker_replay_evidence(
        args.data_root,
        "BTC",
        args.start,
        args.end,
        include_trades=include_trades,
        database_path=args.research_database,
    )
    context = load_verified_replay_context(
        args.price_context,
        args.funding_context,
    )
    replay = replay_maker_order_chunks(
        evidence.chunks,
        decisions,
        config,
        context=context,
    )
    archive = {
        "start": args.start.isoformat(),
        "end": args.end.isoformat(),
        "market": evidence.summary,
        "context": context_coverage_report(context),
    }
    return replay.to_dict(), archive


def _window_event_count(
    decisions: pd.DataFrame,
    start: datetime,
    end: datetime,
) -> int:
    signals = decisions.index[decisions["entry_direction"].notna()]
    available = signals + pd.Timedelta(minutes=1)
    return int(((available >= start) & (available < end)).sum())


def _limitations() -> list[str]:
    return [
        "The same historical window motivated and evaluates this candidate.",
        "Public trade-through volume cannot identify private queue rank.",
        "Queue cancellations and partial maker fills remain unobservable.",
        "Creator screenshots are selected winners and do not estimate precision.",
        "A fresh frozen shadow window is required before runtime promotion.",
    ]


def _report(args: argparse.Namespace) -> dict[str, object]:
    if args.end <= args.start:
        raise ValueError("recovery replay end must follow start")
    decisions, raw_1m = _classified_inputs(args)
    selected, config, total_events = _recovery_inputs(
        decisions,
        raw_1m,
        initial_equity=args.initial_equity,
        fill_rule=args.fill_rule,
    )
    replay, archive = _execute_replay(args, selected, config)
    return {
        "ok": True,
        "report_only": True,
        "execution_authority": "none",
        "experiment": "canonical_1m_recovery_inside_5m_down_long_v1",
        "candidate_events": _window_event_count(selected, args.start, args.end),
        "candidate_events_full_history": total_events,
        "source_evidence": _source_evidence(args),
        "archive": archive,
        "replay_contract": _replay_contract(args),
        "event_replay": replay,
        "metalabel_policy": runtime_observe_contract(args.config),
        "runtime_strategy_changed": False,
        "limitations": _limitations(),
    }


def main(argv: list[str] | None = None) -> int:
    """Write one immutable report-only canonical recovery replay artifact."""
    args = _parser().parse_args(argv)
    try:
        if args.out.exists():
            raise FileExistsError(f"recovery replay output exists: {args.out}")
        args.out.parent.mkdir(parents=True, exist_ok=True)
        write_json(args.out, _report(args))
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "out": str(args.out)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

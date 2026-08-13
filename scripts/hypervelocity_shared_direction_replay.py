#!/usr/bin/env python3
"""Compare short, long, and one shared BTC portfolio on exact venue tape."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import math
from pathlib import Path
import sys

import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.hypertrader_label_evidence import load_label_evidence
from hypervector.research.hypertrader_source_adapter import (
    PINNED_HYPERTRADER_REVISION,
    resample_hyperliquid_5m,
)
from hypervector.research.liquidity_sweep_long import (
    build_liquidity_sweep_long_decisions,
    load_minute_bars,
)
from hypervector.research.maker_replay_context_io import (
    context_coverage_report,
    load_verified_replay_context_parts,
)
from hypervector.research.maker_replay_models import (
    MakerReplayConfig,
    MakerReplayReport,
)
from hypervector.research.maker_replay_stream import (
    replay_maker_order_decision_grid_chunks,
)
from hypervector.research.research_evidence_source import maker_replay_evidence
from hypervector.research.shared_direction_portfolio import (
    SharedDecisionGrid,
    build_shared_btc_decision_grid,
)
from hypervector.research.source_follow_portfolio_artifact import (
    select_source_follow_signals,
)
from hypervector.research.source_follow_portfolio_models import SourceSignal


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("timestamp must include a UTC offset")
    return parsed.astimezone(UTC)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bars", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--labels-metadata", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--research-database", type=Path, required=True)
    parser.add_argument("--start", type=_utc, required=True)
    parser.add_argument("--end", type=_utc, required=True)
    parser.add_argument("--price-context", type=Path, action="append", required=True)
    parser.add_argument("--funding-context", type=Path, action="append", required=True)
    parser.add_argument("--initial-equity", type=float, default=15_000.0)
    parser.add_argument(
        "--short-entry-session",
        choices=("24/7", "[06:00,15:00)"),
        default="24/7",
    )
    parser.add_argument(
        "--fill-rule",
        choices=("touch", "through", "trade-through"),
        required=True,
    )
    parser.add_argument("--out", type=Path, required=True)
    return parser


def _configs(args: argparse.Namespace) -> dict[str, MakerReplayConfig]:
    shared = MakerReplayConfig(
        initial_equity=args.initial_equity,
        margin_fraction=0.35,
        leverage=30.0,
        target_margin_pct=8.0,
        fill_rule=args.fill_rule,
        entry_ttl_seconds=60.0,
        reentry_cooldown_seconds=60.0,
        same_direction_reentry_policy="regime_reset",
        maximum_hold_seconds=86_400.0,
        occupied_signal_policy="ignore",
    )
    return {name: shared for name in ("short_control", "long_control", "combined")}


def _contract(args: argparse.Namespace) -> dict[str, object]:
    session_tag = "all_day" if args.short_entry_session == "24/7" else "session_06_15"
    return {
        "candidate": f"shared_source_short_{session_tag}_liquidity_sweep_long_v2",
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "model_authority": "observe",
        "shared_position_limit": 1,
        "shared_pending_entry_limit": 1,
        "simultaneous_signal_priority": "source_follow_short",
        "occupied_signal_policy": "ignore_and_require_fresh_after_flat",
        "initial_equity": args.initial_equity,
        "allocation_fraction": 0.35,
        "leverage": 30.0,
        "gross_margin_target_pct": 8.0,
        "long_fixed_margin_stop_pct": 18.0,
        "long_fixed_price_stop_bps": 60.0,
        "short_stop": None,
        "short_entry_session_utc": args.short_entry_session,
        "short_entry_session_clock": "decision_time_utc",
        "maximum_hold_seconds": 86_400.0,
        "fill_rule": args.fill_rule,
    }


def _context_parts(args: argparse.Namespace) -> list[tuple[Path, Path]]:
    if len(args.price_context) != len(args.funding_context):
        raise ValueError("price and funding context part counts must match")
    return list(zip(args.price_context, args.funding_context, strict=True))


def _load_labels(args: argparse.Namespace) -> pd.DataFrame:
    evidence = load_label_evidence(args.labels, args.labels_metadata)
    if not evidence.metadata_verified:
        raise ValueError("source labels failed metadata verification")
    if evidence.revision != PINNED_HYPERTRADER_REVISION:
        raise ValueError("source labels do not match the pinned revision")
    labels = pd.read_parquet(args.labels)
    if not isinstance(labels.index, pd.DatetimeIndex) or labels.index.tz is None:
        raise ValueError("source labels require a timezone-aware index")
    return labels


def _validate_inputs(args: argparse.Namespace, bars: pd.DataFrame) -> None:
    if args.end <= args.start:
        raise ValueError("shared replay end must follow start")
    if not math.isfinite(args.initial_equity) or args.initial_equity <= 0.0:
        raise ValueError("shared replay initial equity must be positive")
    warmup_start = pd.Timestamp(args.start) - pd.Timedelta(hours=55)
    required_end = pd.Timestamp(args.end) - pd.Timedelta(minutes=1)
    if bars.index[0] > warmup_start or bars.index[-1] < required_end:
        raise ValueError("shared replay bars do not cover the window and warmup")


def _decision_grid(
    args: argparse.Namespace,
    bars: pd.DataFrame,
    labels: pd.DataFrame,
) -> SharedDecisionGrid:
    short_signals = _filter_short_signals(
        select_source_follow_signals(
            labels,
            _short_signal_bars(bars),
            args.start,
            args.end,
        ),
        args.short_entry_session,
    )
    long_decisions = build_liquidity_sweep_long_decisions(bars)
    return build_shared_btc_decision_grid(
        short_signals,
        long_decisions,
        start=args.start,
        end=args.end,
    )


def _short_signal_bars(minute_bars: pd.DataFrame) -> pd.DataFrame:
    return resample_hyperliquid_5m(minute_bars)


def _filter_short_signals(
    signals: tuple[SourceSignal, ...], session: str
) -> tuple[SourceSignal, ...]:
    """Filter source shorts by their causal decision-clock UTC session."""
    if session == "24/7":
        return signals
    if session != "[06:00,15:00)":
        raise ValueError(f"unsupported short entry session: {session!r}")
    return tuple(
        signal for signal in signals if 6 <= _utc(signal.decision_time_utc).hour < 15
    )


def _profit_factor(report: MakerReplayReport) -> float | None:
    gains = sum(max(trade.net_pnl, 0.0) for trade in report.trades)
    losses = -sum(min(trade.net_pnl, 0.0) for trade in report.trades)
    return gains / losses if losses > 0.0 else None


def _summary(report: MakerReplayReport) -> dict[str, object]:
    return {
        "final_equity": report.final_equity,
        "net_pnl": report.final_equity - report.initial_equity,
        "profit_factor": _profit_factor(report),
        "submitted_entries": report.submitted_entries,
        "entry_fills": report.entry_fills,
        "completed_trades": report.completed_trades,
        "long_trades": sum(trade.direction == "long" for trade in report.trades),
        "short_trades": sum(trade.direction == "short" for trade in report.trades),
        "target_completions": sum(
            trade.status == "target_completed" for trade in report.trades
        ),
        "stops": report.stops,
        "time_exits": report.time_exits,
        "liquidations": report.liquidations,
        "maximum_drawdown_pct": report.maximum_drawdown_pct,
        "funding_cashflow": report.funding_cashflow,
        "active_book_gap_windows": report.active_book_gap_windows,
        "execution_economics_conclusive": report.execution_economics_conclusive,
    }


def _filled_short_signals(report: MakerReplayReport) -> set[str]:
    return {
        lifecycle.signal_time_utc
        for lifecycle in report.lifecycles
        if lifecycle.direction == "short" and lifecycle.entry_time_utc is not None
    }


def _comparison(reports: dict[str, MakerReplayReport]) -> dict[str, object]:
    short = reports["short_control"]
    long = reports["long_control"]
    combined = reports["combined"]
    control_short_fills = _filled_short_signals(short)
    combined_short_fills = _filled_short_signals(combined)
    return {
        "combined_minus_short_final_equity": combined.final_equity - short.final_equity,
        "combined_minus_long_final_equity": combined.final_equity - long.final_equity,
        "combined_minus_short_maximum_drawdown_pct": (
            combined.maximum_drawdown_pct - short.maximum_drawdown_pct
        ),
        "short_control_filled_signals": len(control_short_fills),
        "combined_filled_short_signals": len(combined_short_fills),
        "short_control_fills_not_reproduced_in_combined": sorted(
            control_short_fills - combined_short_fills
        ),
        "new_short_fills_in_combined": sorted(
            combined_short_fills - control_short_fills
        ),
    }


def _path_evidence(path: Path) -> dict[str, object]:
    return {"path": str(path.resolve()), **file_evidence(path)}


def _report(args: argparse.Namespace) -> dict[str, object]:
    bars = load_minute_bars(args.bars)
    _validate_inputs(args, bars)
    labels = _load_labels(args)
    grid = _decision_grid(args, bars, labels)
    context_parts = _context_parts(args)
    context = load_verified_replay_context_parts(context_parts)
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
        grid.as_mapping(),
        _configs(args),
        context=context,
    )
    return {
        "schema": "hypervelocity_shared_direction_replay_v2",
        "report_only": True,
        "experiment_contract": _contract(args),
        "signal_counts": {
            "short": grid.short_events,
            "long": grid.long_events,
            "simultaneous_long_events_dropped": (grid.simultaneous_long_events_dropped),
        },
        "summaries": {name: _summary(report) for name, report in reports.items()},
        "comparison": _comparison(reports),
        "event_replays": {name: report.to_dict() for name, report in reports.items()},
        "market_evidence": evidence.summary,
        "context_evidence": context_coverage_report(context),
        "source_evidence": {
            "bars": _path_evidence(args.bars),
            "labels": _path_evidence(args.labels),
            "labels_metadata": _path_evidence(args.labels_metadata),
            "price_context": [_path_evidence(path) for path, _ in context_parts],
            "funding_context": [_path_evidence(path) for _, path in context_parts],
        },
        "limitations": [
            "This interval informed both candidate selection and is not a holdout.",
            "Public trade-through cannot identify private maker queue rank.",
            "The source one-minute bar file contains declared gap-fill rows.",
            "Any active empty-book interval makes execution economics inconclusive.",
            (
                "Shared-equity gains change order quantity, so a control fill may "
                "expire in the combined lane under the same public queue volume."
            ),
            "The long remains annotation-only pending prospective evidence.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    """Write one immutable report-only shared-direction comparison."""
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

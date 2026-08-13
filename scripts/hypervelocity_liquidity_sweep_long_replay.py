"""Replay the frozen liquidity-sweep long challenger on exact Hyperliquid tape."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sys

import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.liquidity_sweep_long import (
    build_liquidity_sweep_long_decisions,
    load_minute_bars,
)
from hypervector.research.maker_replay_context_io import (
    context_coverage_report,
    load_verified_replay_context_parts,
)
from hypervector.research.maker_replay_models import MakerReplayConfig
from hypervector.research.maker_replay_stream import replay_maker_order_chunks
from hypervector.research.research_evidence_source import maker_replay_evidence


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("timestamp must include a UTC offset")
    return parsed.astimezone(UTC)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bars", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--research-database", type=Path)
    parser.add_argument("--start", type=_utc, required=True)
    parser.add_argument("--end", type=_utc, required=True)
    parser.add_argument("--price-context", type=Path, action="append", required=True)
    parser.add_argument("--funding-context", type=Path, action="append", required=True)
    parser.add_argument("--initial-equity", type=float, default=15_000.0)
    parser.add_argument(
        "--fill-rule",
        choices=("touch", "through", "trade-through"),
        required=True,
    )
    parser.add_argument("--out", type=Path, required=True)
    return parser


def _replay_config(args: argparse.Namespace) -> MakerReplayConfig:
    return MakerReplayConfig(
        initial_equity=args.initial_equity,
        margin_fraction=0.35,
        leverage=30.0,
        target_margin_pct=8.0,
        fill_rule=args.fill_rule,
        entry_ttl_seconds=60.0,
        reentry_cooldown_seconds=60.0,
        same_direction_reentry_policy="regime_reset",
        fixed_margin_stop_pct=18.0,
        maximum_hold_seconds=86_400.0,
    )


def _context_parts(args: argparse.Namespace) -> list[tuple[Path, Path]]:
    if len(args.price_context) != len(args.funding_context):
        raise ValueError("price and funding context part counts must match")
    return list(zip(args.price_context, args.funding_context, strict=True))


def _path_evidence(path: Path) -> dict[str, object]:
    return {"path": str(path.resolve()), **file_evidence(path)}


def _window_signal_times(
    decisions: pd.DataFrame,
    start: datetime,
    end: datetime,
) -> list[str]:
    signals = decisions.index[decisions["entry_direction"].eq("long")]
    available = signals + pd.Timedelta(minutes=1)
    selected = available[(available >= start) & (available < end)]
    return [value.isoformat() for value in selected]


def _validate_bar_coverage(
    bars: pd.DataFrame,
    start: datetime,
    end: datetime,
) -> None:
    warmup_start = pd.Timestamp(start) - pd.Timedelta(hours=55)
    required_end = pd.Timestamp(end) - pd.Timedelta(minutes=1)
    if bars.index[0] > warmup_start or bars.index[-1] < required_end:
        raise ValueError("long replay bars do not cover the window and 55-hour warmup")


def _contract(args: argparse.Namespace) -> dict[str, object]:
    return {
        "candidate": "liquidity_sweep_long_1h_stop60_v1",
        "allocation_fraction": 0.35,
        "leverage": 30.0,
        "gross_margin_target_pct": 8.0,
        "fixed_margin_stop_pct": 18.0,
        "fixed_price_stop_bps": 60.0,
        "maximum_hold_seconds": 86_400.0,
        "entry_ttl_seconds": 60.0,
        "reentry_cooldown_seconds": 60.0,
        "same_direction_reentry_policy": "regime_reset",
        "fill_rule": args.fill_rule,
    }


def _report(args: argparse.Namespace) -> dict[str, object]:
    if args.end <= args.start:
        raise ValueError("long replay end must follow start")
    bars = load_minute_bars(args.bars)
    _validate_bar_coverage(bars, args.start, args.end)
    decisions = build_liquidity_sweep_long_decisions(bars)
    signal_times = _window_signal_times(decisions, args.start, args.end)
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
    replay = replay_maker_order_chunks(
        evidence.chunks,
        decisions,
        _replay_config(args),
        context=context,
    )
    return {
        "schema": "hypervelocity_liquidity_sweep_long_replay_v1",
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "candidate_signal_count": len(signal_times),
        "candidate_signal_times_utc": signal_times,
        "replay_contract": _contract(args),
        "event_replay": replay.to_dict(),
        "market_evidence": evidence.summary,
        "context_evidence": context_coverage_report(context),
        "source_evidence": {
            "bars": _path_evidence(args.bars),
            "price_context": [_path_evidence(path) for path, _ in context_parts],
            "funding_context": [_path_evidence(path) for _, path in context_parts],
        },
        "model_policy": {
            "mode": "observe",
            "execution_authority": "none",
            "used_for_entry": False,
            "used_for_sizing": False,
        },
        "limitations": [
            "This historical interval has already informed the long hypothesis.",
            "Public trade-through cannot identify private maker queue rank.",
            "Queue cancellations and partial maker fills remain unobservable.",
            "The source bar file contains declared gap-fill rows.",
            "A fresh frozen shadow window is required before runtime promotion.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    """Write one immutable report-only exact long replay artifact."""
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

#!/usr/bin/env python3
"""Compare source revision and entry minima inside one fixed BTC session."""

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
    LEGACY_HYPERTRADER_REVISION,
    PINNED_HYPERTRADER_REVISION,
    load_hyperliquid_candle_segments,
    resample_hyperliquid_5m,
)
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

_CANDIDATES = (
    "strict_tuned",
    "legacy_tuned",
    "strict_source_native",
    "legacy_source_native",
)
_CANDIDATE_SETS = {
    "all": _CANDIDATES,
    "strict-tuned-only": ("strict_tuned",),
    "strict-only": ("strict_tuned", "strict_source_native"),
    "strict-range-pair": ("strict_tuned", "strict_range_relaxed"),
    "strict-one-factor": (
        "strict_tuned",
        "strict_range_relaxed",
        "strict_confidence_relaxed",
    ),
    "strict-factorial": (
        "strict_tuned",
        "strict_range_relaxed",
        "strict_confidence_relaxed",
        "strict_source_native",
    ),
}
_SIGNAL_POLICIES = {
    "strict_tuned": ("strict", 0.70, 12.0),
    "legacy_tuned": ("legacy", 0.70, 12.0),
    "strict_range_relaxed": ("strict", 0.70, 0.0),
    "strict_confidence_relaxed": ("strict", 0.0, 12.0),
    "strict_source_native": ("strict", 0.0, 0.0),
    "legacy_source_native": ("legacy", 0.0, 0.0),
}
_SESSION_START_HOUR = 6
_SESSION_END_HOUR = 15
_DEFAULT_ENTRY_SESSION = "[06:00,15:00)"
_ENTRY_SESSIONS = (_DEFAULT_ENTRY_SESSION, "24/7")


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("timestamp must include a UTC offset")
    return parsed.astimezone(UTC)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bars", type=Path, required=True)
    parser.add_argument("--strict-labels", type=Path, required=True)
    parser.add_argument("--strict-metadata", type=Path, required=True)
    parser.add_argument("--legacy-labels", type=Path)
    parser.add_argument("--legacy-metadata", type=Path)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--research-database", type=Path, required=True)
    parser.add_argument("--start", type=_utc, required=True)
    parser.add_argument("--end", type=_utc, required=True)
    parser.add_argument("--price-context", type=Path, action="append", required=True)
    parser.add_argument("--funding-context", type=Path, action="append", required=True)
    parser.add_argument("--initial-equity", type=float, default=15_000.0)
    parser.add_argument(
        "--entry-session",
        choices=_ENTRY_SESSIONS,
        default=_DEFAULT_ENTRY_SESSION,
    )
    parser.add_argument(
        "--candidate-set",
        choices=tuple(_CANDIDATE_SETS),
        default="all",
    )
    parser.add_argument(
        "--fill-rule",
        choices=("touch", "through", "trade-through"),
        required=True,
    )
    parser.add_argument("--out", type=Path, required=True)
    return parser


def _configs(
    initial_equity: float,
    fill_rule: FillRule,
    candidate_set: str = "all",
) -> dict[str, MakerReplayConfig]:
    config = MakerReplayConfig(
        initial_equity=initial_equity,
        margin_fraction=0.35,
        leverage=30.0,
        target_margin_pct=8.0,
        fill_rule=fill_rule,
        entry_ttl_seconds=60.0,
        reentry_cooldown_seconds=60.0,
        same_direction_reentry_policy="regime_reset",
        maximum_hold_seconds=86_400.0,
        occupied_signal_policy="ignore",
    )
    return {name: config for name in _candidate_names(candidate_set)}


def _candidate_names(candidate_set: str) -> tuple[str, ...]:
    try:
        return _CANDIDATE_SETS[candidate_set]
    except KeyError as exc:
        choices = ", ".join(_CANDIDATE_SETS)
        raise ValueError(f"candidate set must be one of: {choices}") from exc


def _candidate_set_uses_legacy(candidate_set: str) -> bool:
    return any(
        _SIGNAL_POLICIES[name][0] == "legacy"
        for name in _candidate_names(candidate_set)
    )


def _contract(
    initial_equity: float,
    fill_rule: FillRule,
    candidate_set: str = "all",
    entry_session: str = _DEFAULT_ENTRY_SESSION,
) -> dict[str, object]:
    return {
        "candidate": "source_session_revision_gate_factorial_v1",
        "candidate_set": candidate_set,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "model_authority": "observe",
        "entry_session_utc": entry_session,
        "entry_session_clock": "decision_time_utc",
        "strict_revision": PINNED_HYPERTRADER_REVISION,
        "legacy_revision": (
            LEGACY_HYPERTRADER_REVISION
            if _candidate_set_uses_legacy(candidate_set)
            else None
        ),
        "tuned_minimum_confidence": 0.70,
        "tuned_minimum_range_bps": 12.0,
        "strict_range_relaxed_minimum_confidence": 0.70,
        "strict_range_relaxed_minimum_range_bps": 0.0,
        "strict_confidence_relaxed_minimum_confidence": 0.0,
        "strict_confidence_relaxed_minimum_range_bps": 12.0,
        "source_native_minimum_confidence": 0.0,
        "source_native_minimum_range_bps": 0.0,
        "maximum_range_bps": 100.0,
        "initial_equity": initial_equity,
        "allocation_fraction": 0.35,
        "leverage": 30.0,
        "gross_margin_target_pct": 8.0,
        "maximum_hold_seconds": 86_400.0,
        "fill_rule": fill_rule,
        "parameter_selection_allowed": False,
    }


def _load_labels(path: Path, metadata: Path, revision: str) -> pd.DataFrame:
    evidence = load_label_evidence(path, metadata)
    if not evidence.metadata_verified:
        raise ValueError(f"source labels failed metadata verification: {path}")
    if evidence.revision != revision:
        raise ValueError(f"source label revision mismatch: {path}")
    labels = pd.read_parquet(path)
    if not isinstance(labels.index, pd.DatetimeIndex) or labels.index.tz is None:
        raise ValueError("source labels require a timezone-aware index")
    return labels


def _entry_signals(
    signals: tuple[SourceSignal, ...], entry_session: str
) -> tuple[SourceSignal, ...]:
    if entry_session == "24/7":
        return signals
    if entry_session != _DEFAULT_ENTRY_SESSION:
        raise ValueError(f"unsupported entry session: {entry_session!r}")
    return tuple(
        signal
        for signal in signals
        if _SESSION_START_HOUR
        <= pd.Timestamp(signal.decision_time_utc).hour
        < _SESSION_END_HOUR
    )


def _signal_bars(minute_bars: pd.DataFrame) -> pd.DataFrame:
    return resample_hyperliquid_5m(minute_bars)


def _load_signal_bars(path: Path) -> pd.DataFrame:
    """Load only complete native five-minute bars across explicit data gaps."""
    segments = load_hyperliquid_candle_segments([path])
    return pd.concat([_signal_bars(frame) for frame in segments]).sort_index()


def _select(
    labels: pd.DataFrame,
    bars: pd.DataFrame,
    start: datetime,
    end: datetime,
    *,
    minimum_confidence: float,
    minimum_signal_range_bps: float,
    entry_session: str,
) -> tuple[SourceSignal, ...]:
    return _entry_signals(
        select_source_follow_signals(
            labels,
            bars,
            start,
            end,
            minimum_confidence=minimum_confidence,
            minimum_signal_range_bps=minimum_signal_range_bps,
            maximum_signal_range_bps=100.0,
        ),
        entry_session,
    )


def _candidate_signals(
    strict: pd.DataFrame,
    legacy: pd.DataFrame | None,
    bars: pd.DataFrame,
    start: datetime,
    end: datetime,
    entry_session: str = _DEFAULT_ENTRY_SESSION,
    candidate_set: str | None = None,
) -> dict[str, tuple[SourceSignal, ...]]:
    label_sets = {"strict": strict, "legacy": legacy}
    candidates: dict[str, tuple[SourceSignal, ...]] = {}
    names = (
        tuple(_SIGNAL_POLICIES)
        if candidate_set is None
        else _candidate_names(candidate_set)
    )
    for name in names:
        revision, confidence, signal_range = _SIGNAL_POLICIES[name]
        labels = label_sets[revision]
        if labels is None:
            raise ValueError("legacy labels are required by the selected candidate set")
        candidates[name] = _select(
            labels,
            bars,
            start,
            end,
            minimum_confidence=confidence,
            minimum_signal_range_bps=signal_range,
            entry_session=entry_session,
        )
    return candidates


def _load_legacy_labels(args: argparse.Namespace) -> pd.DataFrame | None:
    labels_path = args.legacy_labels
    metadata_path = args.legacy_metadata
    if (labels_path is None) != (metadata_path is None):
        raise ValueError("legacy labels and metadata must be provided together")
    if labels_path is None:
        if _candidate_set_uses_legacy(args.candidate_set):
            raise ValueError("legacy labels are required by the selected candidate set")
        return None
    return _load_labels(labels_path, metadata_path, LEGACY_HYPERTRADER_REVISION)


def _empty_long_decisions() -> pd.DataFrame:
    return pd.DataFrame(
        {"entry_direction": pd.Series(dtype=object)},
        index=pd.DatetimeIndex([], tz="UTC"),
    )


def _decision_frames(
    candidates: dict[str, tuple[SourceSignal, ...]],
    start: datetime,
    end: datetime,
) -> dict[str, pd.DataFrame]:
    empty_longs = _empty_long_decisions()
    return {
        name: build_shared_btc_decision_grid(
            signals,
            empty_longs,
            start=start,
            end=end,
        ).short_control
        for name, signals in candidates.items()
    }


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
        "target_completions": sum(
            trade.status == "target_completed" for trade in report.trades
        ),
        "liquidations": report.liquidations,
        "partial_liquidations": report.partial_liquidations,
        "time_exits": report.time_exits,
        "maximum_drawdown_pct": report.maximum_drawdown_pct,
        "funding_cashflow": report.funding_cashflow,
        "authentic_price_updates": report.authentic_price_updates,
        "missing_mark_events": report.missing_mark_events,
        "stale_mark_events": report.stale_mark_events,
        "missing_oracle_settlements": report.missing_oracle_settlements,
        "stale_oracle_settlements": report.stale_oracle_settlements,
        "active_book_gap_windows": report.active_book_gap_windows,
        "execution_economics_conclusive": report.execution_economics_conclusive,
    }


def _comparison(reports: dict[str, MakerReplayReport]) -> dict[str, object]:
    control = reports["strict_tuned"]
    result: dict[str, object] = {}
    for name, report in reports.items():
        result[name] = {
            "final_equity_delta_vs_strict_tuned": (
                report.final_equity - control.final_equity
            ),
            "maximum_drawdown_delta_vs_strict_tuned": (
                report.maximum_drawdown_pct - control.maximum_drawdown_pct
            ),
            "entry_fill_delta_vs_strict_tuned": (
                report.entry_fills - control.entry_fills
            ),
            "liquidation_delta_vs_strict_tuned": (
                report.liquidations - control.liquidations
            ),
        }
    return result


def _path_evidence(path: Path) -> dict[str, object]:
    return {"path": str(path.resolve()), **file_evidence(path)}


def _context_parts(args: argparse.Namespace) -> list[tuple[Path, Path]]:
    if len(args.price_context) != len(args.funding_context):
        raise ValueError("price and funding context part counts must match")
    return list(zip(args.price_context, args.funding_context, strict=True))


def _validate_inputs(args: argparse.Namespace, bars: pd.DataFrame) -> None:
    if args.end <= args.start:
        raise ValueError("factorial end must follow start")
    if not math.isfinite(args.initial_equity) or args.initial_equity <= 0.0:
        raise ValueError("factorial initial equity must be positive")
    if bars.index[0] > pd.Timestamp(args.start):
        raise ValueError("factorial bars start after the replay window")
    if bars.index[-1] < pd.Timestamp(args.end) - pd.Timedelta(minutes=5):
        raise ValueError("factorial bars end before the replay window")


def _report(args: argparse.Namespace) -> dict[str, object]:
    bars = _load_signal_bars(args.bars)
    _validate_inputs(args, bars)
    strict = _load_labels(
        args.strict_labels, args.strict_metadata, PINNED_HYPERTRADER_REVISION
    )
    legacy = _load_legacy_labels(args)
    candidates = _candidate_signals(
        strict,
        legacy,
        bars,
        args.start,
        args.end,
        args.entry_session,
        args.candidate_set,
    )
    parts = _context_parts(args)
    context = load_verified_replay_context_parts(parts)
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
        _decision_frames(candidates, args.start, args.end),
        _configs(args.initial_equity, args.fill_rule, args.candidate_set),
        context=context,
    )
    return _payload(args, candidates, reports, evidence.summary, context, parts)


def _payload(
    args: argparse.Namespace,
    candidates: dict[str, tuple[SourceSignal, ...]],
    reports: dict[str, MakerReplayReport],
    market_evidence: dict[str, object],
    context: object,
    parts: list[tuple[Path, Path]],
) -> dict[str, object]:
    legacy_evidence: dict[str, object] = {}
    if args.legacy_labels is not None and args.legacy_metadata is not None:
        legacy_evidence = {
            "legacy_labels": _path_evidence(args.legacy_labels),
            "legacy_metadata": _path_evidence(args.legacy_metadata),
        }
    return {
        "schema": "hypervelocity_source_session_factorial_v1",
        "report_only": True,
        "experiment_contract": _contract(
            args.initial_equity,
            args.fill_rule,
            args.candidate_set,
            args.entry_session,
        ),
        "signal_counts": {name: len(value) for name, value in candidates.items()},
        "summaries": {name: _summary(report) for name, report in reports.items()},
        "comparison": _comparison(reports),
        "event_replays": {name: report.to_dict() for name, report in reports.items()},
        "market_evidence": market_evidence,
        "context_evidence": context_coverage_report(context),
        "source_evidence": {
            "bars": _path_evidence(args.bars),
            "strict_labels": _path_evidence(args.strict_labels),
            "strict_metadata": _path_evidence(args.strict_metadata),
            **legacy_evidence,
            "price_context": [_path_evidence(path) for path, _ in parts],
            "funding_context": [_path_evidence(path) for _, path in parts],
        },
        "limitations": [
            "The session and tuned minima were selected on older development data.",
            "The legacy revision is a constant-revision counterfactual.",
            "Public trade-through cannot identify private maker queue rank.",
            "The source-native lanes remove minima but retain the 100 bps ceiling.",
            "No lane changes runtime, model, or execution authority.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    """Write one immutable report-only revision/gate factorial."""
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

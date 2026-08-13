#!/usr/bin/env python3
"""Carry the frozen source-follow lead across verified gap-free segments."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import timedelta
import json
import math
from pathlib import Path
from typing import cast

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.source_follow_portfolio_artifact import (
    SourcePortfolioSelection,
    load_source_portfolio_selection,
)
from hypervector.research.source_follow_portfolio_io import (
    SourcePortfolioArchive,
    SourcePortfolioArchiveConfig,
)
from hypervector.research.source_follow_portfolio_models import (
    SourceDirection,
    SourcePortfolioReplayConfig,
    SourceSignal,
)
from hypervector.research.source_follow_portfolio_replay import (
    SourcePortfolioReplaySession,
)
from hypervector.research.source_follow_risk_scaling import (
    SourceSizingProfile,
    apply_source_sizing_profile,
    load_source_sizing_labels,
    source_sizing_summary,
)
from hypervector.research.source_follow_sparse_replay import (
    advance_sparse_source_portfolio,
)

_MINIMUM_RANGE_BPS = 12.0
_ALL_DAY_FAMILY = "btc_selected_sizing_surface_v1"
_ALL_DAY_ENTRY = "source-follow-all-day-confidence-70"
_ALL_DAY_RECIPE = "follow_td_all_day_conf70"
_RISK_PROFILES = {
    "alloc25_lev30": (0.25, 30.0),
    "alloc35_lev30": (0.35, 30.0),
    "alloc40_lev30": (0.40, 30.0),
    "alloc50_lev25": (0.50, 25.0),
    "alloc50_lev30": (0.50, 30.0),
}
_SIZING_PROFILES = ("uniform", "weak_choppy_half")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse immutable evidence inputs for the frozen lead only."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--artifact", type=Path, action="append", required=True)
    parser.add_argument("--prices", type=Path, required=True)
    parser.add_argument("--funding", type=Path, required=True)
    parser.add_argument("--candidate", default="alloc50_lev30")
    parser.add_argument(
        "--signal-direction",
        choices=("long", "short"),
        default="short",
    )
    parser.add_argument(
        "--risk-profile",
        choices=tuple(_RISK_PROFILES),
        default="alloc50_lev30",
    )
    parser.add_argument(
        "--sizing-profile",
        choices=_SIZING_PROFILES,
        default="uniform",
    )
    parser.add_argument(
        "--minimum-signal-range-bps",
        type=_nonnegative_float,
        default=_MINIMUM_RANGE_BPS,
    )
    parser.add_argument("--source-labels", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args(argv)


def _nonnegative_float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise argparse.ArgumentTypeError("value must be finite and non-negative")
    return result


def experiment_contract(
    signal_direction: SourceDirection = "short",
    risk_profile: str = "alloc50_lev30",
    sizing_profile: str = "uniform",
    minimum_signal_range_bps: float = _MINIMUM_RANGE_BPS,
) -> dict[str, object]:
    """Return the frozen risk and evidence-selection identity."""
    if not math.isfinite(minimum_signal_range_bps) or minimum_signal_range_bps < 0.0:
        raise ValueError("minimum signal range must be finite and non-negative")
    config = risk_config(risk_profile)
    range_label = f"{minimum_signal_range_bps:g}"
    return {
        "candidate": f"source_follow_minrange{range_label}_continuous_v1",
        "minimum_signal_range_bps": minimum_signal_range_bps,
        "risk_profile": risk_profile,
        "margin_fraction": config.margin_fraction,
        "leverage": config.leverage,
        "gross_margin_target_pct": 8.0,
        "maximum_hold_seconds": 86_400.0,
        "signal_direction": signal_direction,
        "sizing_profile": sizing_profile,
        "weak_choppy_allocation_multiplier": 0.5,
        "execution_authority": "none",
        "model_authority": "observe",
    }


def risk_config(risk_profile: str) -> SourcePortfolioReplayConfig:
    """Resolve one predeclared liquidation-distance challenger."""
    values = _RISK_PROFILES.get(risk_profile)
    if values is None:
        raise ValueError(f"unsupported source-follow risk profile: {risk_profile}")
    margin_fraction, leverage = values
    return SourcePortfolioReplayConfig(
        margin_fraction=margin_fraction,
        leverage=leverage,
        target_price_fraction=8.0 / leverage / 100.0,
    )


def with_signal_direction(
    signals: Sequence[SourceSignal],
    direction: SourceDirection,
) -> tuple[SourceSignal, ...]:
    """Apply one explicit direction challenger without changing signal evidence."""
    return tuple(replace(signal, direction=direction) for signal in signals)


def validate_ordered_selections(
    selections: Sequence[SourcePortfolioSelection],
) -> None:
    """Reject overlap or reordering before sharing portfolio state."""
    if not selections:
        raise ValueError("continuous replay requires at least one segment")
    for previous, current in zip(selections, selections[1:], strict=False):
        if current.start < previous.end:
            raise ValueError("segments must be chronological and non-overlapping")


def _artifact_object(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"all-day source artifact {name} must be an object")
    return cast(dict[str, object], value)


def validate_frozen_artifact(path: Path, candidate: str) -> None:
    """Reject source files outside the frozen all-day confidence-70 family."""
    artifact = _artifact_object(json.loads(path.read_text()), "root")
    identity = (artifact.get("candidate_family"), artifact.get("entry_family"))
    if identity != (_ALL_DAY_FAMILY, _ALL_DAY_ENTRY):
        raise ValueError("all-day source artifact identity does not match frozen lead")
    fresh = _artifact_object(artifact.get("fresh"), "fresh")
    candidates = _artifact_object(fresh.get("candidates"), "candidates")
    selected = _artifact_object(candidates.get(candidate), candidate)
    outcomes = selected.get("event_outcomes")
    if not isinstance(outcomes, list) or not outcomes:
        raise ValueError("all-day source artifact event outcomes must be non-empty")
    recipes = {
        _artifact_object(value, "event outcome").get("recipe_id") for value in outcomes
    }
    if recipes != {_ALL_DAY_RECIPE}:
        raise ValueError("all-day source artifact recipe identity is inconsistent")


def _prepared_signals(
    args: argparse.Namespace,
    selections: Sequence[SourcePortfolioSelection],
) -> tuple[SourceSignal, ...]:
    direction = cast(SourceDirection, args.signal_direction)
    signals = with_signal_direction(
        tuple(signal for item in selections for signal in item.signals),
        direction,
    )
    labels = (
        load_source_sizing_labels(args.source_labels)
        if args.source_labels is not None
        else None
    )
    return apply_source_sizing_profile(
        signals,
        cast(SourceSizingProfile, args.sizing_profile),
        labels,
    )


def main(argv: list[str] | None = None) -> int:
    """Replay all segments through one production matcher and equity account."""
    args = parse_args(argv)
    for path in args.artifact:
        validate_frozen_artifact(path, args.candidate)
    selections = tuple(
        load_source_portfolio_selection(
            path,
            args.candidate,
            minimum_signal_range_bps=args.minimum_signal_range_bps,
        )
        for path in args.artifact
    )
    validate_ordered_selections(selections)
    signals = _prepared_signals(args, selections)
    config = risk_config(args.risk_profile)
    session = SourcePortfolioReplaySession(signals, config)
    segments: list[dict[str, object]] = []
    total_intervals = 0
    total_seconds = 0.0
    total_segments = len(selections)
    for index, (path, selection) in enumerate(
        zip(args.artifact, selections, strict=True),
        start=1,
    ):
        segment = _advance_segment(args, path, selection, session)
        segments.append(segment)
        total_intervals += int(segment["queried_intervals"])
        total_seconds += float(segment["queried_seconds"])
        print(format_progress(index, total_segments, segment), flush=True)
    payload = _payload(
        args,
        selections,
        session,
        signals,
        segments,
        total_intervals,
        total_seconds,
    )
    write_immutable_json(args.out, payload)
    print(f"wrote {args.out}")
    return 0


def format_progress(
    index: int,
    total: int,
    segment: Mapping[str, object],
) -> str:
    """Format bounded progress without exposing mutable strategy controls."""
    signals = int(segment["selected_signal_count"])
    equity = float(segment["ending_equity"])
    return f"completed segment {index}/{total} signals={signals} equity=${equity:.2f}"


def _advance_segment(
    args: argparse.Namespace,
    path: Path,
    selection: SourcePortfolioSelection,
    session: SourcePortfolioReplaySession,
) -> dict[str, object]:
    if not session.is_idle:
        raise RuntimeError("continuous portfolio entered a data gap while active")
    archive_config = SourcePortfolioArchiveConfig(
        args.database,
        args.prices,
        args.funding,
        "BTC",
        selection.start,
        selection.end,
        timedelta(hours=1),
    )
    with SourcePortfolioArchive(archive_config) as archive:
        advance = advance_sparse_source_portfolio(
            session,
            archive,
            selection.start,
            selection.end,
            selection.signals,
        )
    if not session.is_idle:
        raise RuntimeError("continuous portfolio ended a segment while active")
    return {
        "source_artifact": file_evidence(path),
        "start_utc": selection.start.isoformat(),
        "end_utc": selection.end.isoformat(),
        "source_signal_count": selection.source_signal_count,
        "selected_signal_count": len(selection.signals),
        "queried_intervals": advance.queried_intervals,
        "queried_seconds": advance.queried_seconds,
        "verified_window_seconds": advance.window_seconds,
        "ending_equity": session.report().final_equity,
    }


def _payload(
    args: argparse.Namespace,
    selections: tuple[SourcePortfolioSelection, ...],
    session: SourcePortfolioReplaySession,
    signals: tuple[SourceSignal, ...],
    segments: list[dict[str, object]],
    intervals: int,
    seconds: float,
) -> dict[str, object]:
    verified = sum(float(row["verified_window_seconds"]) for row in segments)
    span = (selections[-1].end - selections[0].start).total_seconds()
    return {
        "schema": "hypervelocity_source_continuous_production_replay_v1",
        "report_only": True,
        "runtime_strategy_changed": False,
        "experiment_contract": experiment_contract(
            cast(SourceDirection, args.signal_direction),
            args.risk_profile,
            args.sizing_profile,
            args.minimum_signal_range_bps,
        ),
        "database": str(args.database.resolve()),
        "price_context": file_evidence(args.prices),
        "funding_context": file_evidence(args.funding),
        "segments": segments,
        "segment_count": len(segments),
        "source_signal_count": sum(item.source_signal_count for item in selections),
        "selected_signal_count": sum(len(item.signals) for item in selections),
        "source_sizing": source_sizing_summary(signals),
        "source_labels": (
            file_evidence(args.source_labels)
            if args.source_labels is not None
            else None
        ),
        "sparse_execution_evidence": {
            "queried_intervals": intervals,
            "queried_seconds": seconds,
            "verified_window_seconds": verified,
            "calendar_span_seconds": span,
            "omitted_gap_seconds": span - verified,
            "gaps_crossed_only_while_execution_idle": True,
        },
        "production_replay": session.report().to_dict(),
        "limitations": [
            "The range-floor comparison uses these development periods.",
            "Missing archive intervals are crossed only while flat and idle.",
            "Displayed public depth cannot reveal private cancellations.",
            "Archive exchange timestamps stand in for unavailable receipt time.",
        ],
    }


if __name__ == "__main__":
    raise SystemExit(main())

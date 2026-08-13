#!/usr/bin/env python3
"""Carry the frozen 06:00-15:00 source session across older archive gaps."""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import cast

from hypervector.data.oxa_storage import write_immutable_json
from hypervector.research.source_follow_portfolio_artifact import (
    SourcePortfolioSelection,
    load_source_portfolio_selection,
)
from hypervector.research.source_follow_portfolio_replay import (
    SourcePortfolioReplaySession,
)
from hypervector.research.source_follow_portfolio_models import SourceSignal

_ALL_DAY_FAMILY = "btc_selected_sizing_surface_v1"
_ALL_DAY_ENTRY = "source-follow-all-day-confidence-70"
_ALL_DAY_RECIPE = "follow_td_all_day_conf70"
_RISK_PROFILE = "alloc35_lev30"
_SESSION_START_HOUR = 6
_SESSION_END_HOUR = 15


def _load_continuous_base() -> ModuleType:
    path = Path(__file__).with_name("hypervelocity_source_continuous_replay.py")
    spec = importlib.util.spec_from_file_location("source_continuous_base", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"continuous replay helpers could not be loaded: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


base = _load_continuous_base()


def experiment_contract(
    risk_profile: str = _RISK_PROFILE,
    minimum_signal_range_bps: float = base._MINIMUM_RANGE_BPS,
) -> dict[str, object]:
    """Return the exact older-validation identity for the later session lead."""
    if risk_profile != _RISK_PROFILE:
        raise ValueError(f"session validation risk profile must be {_RISK_PROFILE}")
    range_label = f"{minimum_signal_range_bps:g}"
    return {
        **base.experiment_contract(
            "short",
            risk_profile,
            "uniform",
            minimum_signal_range_bps,
        ),
        "candidate": (
            f"source_follow_session_06_15_minrange{range_label}_continuous_v1"
        ),
        "source_session_utc": "[06:00,15:00)",
        "session_clock": "decision_time_utc",
        "parameter_selection_allowed": False,
    }


def _object(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"session source artifact {name} must be an object")
    return cast(dict[str, object], value)


def validate_session_artifact(path: Path, candidate: str) -> None:
    """Require all-day source evidence before decision-time session filtering."""
    artifact = _object(json.loads(path.read_text(encoding="utf-8")), "root")
    identity = (artifact.get("candidate_family"), artifact.get("entry_family"))
    if identity != (_ALL_DAY_FAMILY, _ALL_DAY_ENTRY):
        raise ValueError("all-day source artifact identity is inconsistent")
    fresh = _object(artifact.get("fresh"), "fresh")
    candidates = _object(fresh.get("candidates"), "candidates")
    selected = _object(candidates.get(candidate), candidate)
    outcomes = selected.get("event_outcomes")
    if not isinstance(outcomes, list) or not outcomes:
        raise ValueError("session source artifact outcomes must be non-empty")
    recipes = {_object(row, "outcome").get("recipe_id") for row in outcomes}
    if recipes != {_ALL_DAY_RECIPE}:
        raise ValueError("all-day source artifact recipe is inconsistent")


def decision_session_signals(
    signals: tuple[SourceSignal, ...],
) -> tuple[SourceSignal, ...]:
    """Return decisions inside the exact half-open runtime entry window."""
    return tuple(
        signal
        for signal in signals
        if _SESSION_START_HOUR
        <= datetime.fromisoformat(signal.decision_time_utc.replace("Z", "+00:00")).hour
        < _SESSION_END_HOUR
    )


def _validate_args(args: argparse.Namespace) -> None:
    if args.signal_direction != "short":
        raise ValueError("session validation requires short signal direction")
    if args.risk_profile != _RISK_PROFILE:
        raise ValueError(f"session validation requires {_RISK_PROFILE}")
    if args.sizing_profile != "uniform":
        raise ValueError("session validation requires uniform sizing")


def _session_selection(
    path: Path,
    candidate: str,
    minimum_signal_range_bps: float,
) -> SourcePortfolioSelection:
    selection = load_source_portfolio_selection(
        path,
        candidate,
        minimum_signal_range_bps=minimum_signal_range_bps,
    )
    return replace(
        selection,
        signals=decision_session_signals(selection.signals),
    )


def _selections(args: argparse.Namespace) -> tuple[SourcePortfolioSelection, ...]:
    for path in args.artifact:
        validate_session_artifact(path, args.candidate)
    result = tuple(
        _session_selection(path, args.candidate, args.minimum_signal_range_bps)
        for path in args.artifact
    )
    base.validate_ordered_selections(result)
    return result


def _payload(
    args: argparse.Namespace,
    selections: tuple[SourcePortfolioSelection, ...],
    session: SourcePortfolioReplaySession,
    signals: tuple[SourceSignal, ...],
    segments: list[dict[str, object]],
    intervals: int,
    seconds: float,
) -> dict[str, object]:
    payload = base._payload(
        args,
        selections,
        session,
        signals,
        segments,
        intervals,
        seconds,
    )
    payload["schema"] = "hypervelocity_source_session_continuous_replay_v1"
    payload["experiment_contract"] = experiment_contract(
        args.risk_profile,
        args.minimum_signal_range_bps,
    )
    payload["limitations"] = [
        "The UTC session was selected on older development evidence.",
        "Session membership uses causal decision_time_utc, not label time.",
        "Missing archive intervals are crossed only while flat and idle.",
        "Displayed public depth cannot reveal private cancellations.",
        "Archive exchange timestamps stand in for unavailable receipt time.",
    ]
    return payload


def main(argv: list[str] | None = None) -> int:
    """Replay the exact session contract through one continuous portfolio."""
    args = base.parse_args(argv)
    _validate_args(args)
    selections = _selections(args)
    signals = base._prepared_signals(args, selections)
    session = SourcePortfolioReplaySession(signals, base.risk_config(_RISK_PROFILE))
    segments: list[dict[str, object]] = []
    intervals = 0
    seconds = 0.0
    for index, (path, selection) in enumerate(
        zip(args.artifact, selections, strict=True),
        start=1,
    ):
        segment = base._advance_segment(args, path, selection, session)
        segments.append(segment)
        intervals += int(segment["queried_intervals"])
        seconds += float(segment["queried_seconds"])
        print(base.format_progress(index, len(selections), segment), flush=True)
    payload = _payload(
        args,
        selections,
        session,
        signals,
        segments,
        intervals,
        seconds,
    )
    write_immutable_json(args.out, payload)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

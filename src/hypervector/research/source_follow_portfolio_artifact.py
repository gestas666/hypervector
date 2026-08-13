"""Validated signal selection from historical source-follow replay artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import math
from pathlib import Path
from typing import cast

import pandas as pd

from hypervector.research.hypertrader_source_adapter import (
    annotate_signal_range_eligibility,
    extract_source_follow_all_day_events,
)
from hypervector.research.source_follow_portfolio_models import SourceSignal
from hypervector.research.source_follow_portfolio_models import SourceDirection

_LIVE_MINIMUM_CONFIDENCE = 0.70
_LIVE_MINIMUM_RANGE_BPS = 12.0
_LIVE_MAXIMUM_RANGE_BPS = 100.0


@dataclass(frozen=True)
class SourcePortfolioSelection:
    """Window, all source decisions, and the optimistic baseline report."""

    start: datetime
    end: datetime
    signals: tuple[SourceSignal, ...]
    baseline_replay: dict[str, object]
    source_signal_count: int


def load_source_portfolio_selection(
    path: Path,
    candidate: str,
    *,
    minimum_signal_range_bps: float | None = None,
) -> SourcePortfolioSelection:
    """Load every eligible signal regardless of old portfolio admission."""
    _validate_minimum_range(minimum_signal_range_bps)
    artifact = _mapping(_load_json(path), "artifact")
    window = _mapping(artifact.get("replay_window"), "replay_window")
    start = _utc(_text(window, "fresh_start"))
    end = _utc(_text(window, "data_end"))
    if start >= end:
        raise ValueError("source artifact fresh window must be positive")
    fresh = _mapping(artifact.get("fresh"), "fresh")
    candidates = _mapping(fresh.get("candidates"), "fresh.candidates")
    selected = _mapping(candidates.get(candidate), candidate)
    outcomes = selected.get("event_outcomes")
    if not isinstance(outcomes, list):
        raise ValueError("source candidate event_outcomes must be a list")
    source_signal_count = sum(
        _mapping(value, "event outcome").get("entry_eligible") is True
        for value in outcomes
    )
    signals = _signals(outcomes, start, end, minimum_signal_range_bps)
    replay = _mapping(selected.get("replay"), f"{candidate}.replay")
    return SourcePortfolioSelection(
        start,
        end,
        signals,
        replay,
        source_signal_count,
    )


def select_source_follow_signals(
    labels: pd.DataFrame,
    bars: pd.DataFrame,
    start: datetime,
    end: datetime,
    *,
    minimum_confidence: float = _LIVE_MINIMUM_CONFIDENCE,
    minimum_signal_range_bps: float = _LIVE_MINIMUM_RANGE_BPS,
    maximum_signal_range_bps: float = _LIVE_MAXIMUM_RANGE_BPS,
) -> tuple[SourceSignal, ...]:
    """Select the frozen causal all-day source-follow decisions."""
    _validate_utc_window(start, end)
    _validate_signal_thresholds(
        minimum_confidence,
        minimum_signal_range_bps,
        maximum_signal_range_bps,
    )
    events = annotate_signal_range_eligibility(
        extract_source_follow_all_day_events(labels),
        bars,
        maximum_range_bps=maximum_signal_range_bps,
    )
    decision = pd.to_datetime(events["decision_time_utc"], utc=True)
    confidence = pd.to_numeric(events["confidence"], errors="raise")
    signal_range = pd.to_numeric(events["signal_range_bps"], errors="raise")
    selected = events.loc[
        events["entry_eligible"]
        & confidence.ge(minimum_confidence)
        & signal_range.ge(minimum_signal_range_bps)
        & decision.ge(pd.Timestamp(start))
        & decision.lt(pd.Timestamp(end))
    ]
    return tuple(
        SourceSignal(
            pd.Timestamp(row.decision_time_utc).isoformat(),
            confidence=float(row.confidence),
            signal_range_bps=float(row.signal_range_bps),
            direction="short",
        )
        for row in selected.itertuples(index=False)
    )


def _validate_signal_thresholds(
    minimum_confidence: float,
    minimum_range_bps: float,
    maximum_range_bps: float,
) -> None:
    if not math.isfinite(minimum_confidence) or not 0.0 <= minimum_confidence <= 1.0:
        raise ValueError("minimum confidence must be within [0, 1]")
    values = (minimum_range_bps, maximum_range_bps)
    if any(not math.isfinite(value) or value < 0.0 for value in values):
        raise ValueError("signal range thresholds must be finite and non-negative")
    if minimum_range_bps > maximum_range_bps:
        raise ValueError("minimum signal range cannot exceed maximum")


def _signals(
    outcomes: list[object],
    start: datetime,
    end: datetime,
    minimum_signal_range_bps: float | None,
) -> tuple[SourceSignal, ...]:
    signals: list[SourceSignal] = []
    for value in outcomes:
        outcome = _mapping(value, "event outcome")
        if outcome.get("entry_eligible") is not True:
            continue
        signal = SourceSignal(
            _text(outcome, "decision_time_utc"),
            confidence=_optional_number(outcome, "confidence"),
            signal_range_bps=_optional_number(outcome, "signal_range_bps"),
            direction=_direction(outcome),
        )
        timestamp = _utc(signal.decision_time_utc)
        if not start <= timestamp < end:
            raise ValueError("source decision falls outside the fresh replay window")
        if minimum_signal_range_bps is not None:
            if signal.signal_range_bps is None:
                raise ValueError("minimum range selection requires signal_range_bps")
            if signal.signal_range_bps < minimum_signal_range_bps:
                continue
        signals.append(signal)
    times = [signal.decision_time_utc for signal in signals]
    if times != sorted(times) or len(times) != len(set(times)):
        raise ValueError("source artifact signals must be unique and chronological")
    return tuple(signals)


def _direction(row: dict[str, object]) -> SourceDirection:
    value = row.get("side", "short")
    if value not in {"long", "short"}:
        raise ValueError("source event side must be long or short")
    return cast(SourceDirection, value)


def _load_json(path: Path) -> object:
    if not path.is_file():
        raise FileNotFoundError(f"source portfolio artifact is missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _mapping(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return cast(dict[str, object], value)


def _text(row: dict[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _optional_number(row: dict[str, object], key: str) -> float | None:
    value = row.get(key)
    if value is None:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{key} must be numeric when present")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{key} must be finite when present")
    return result


def _validate_minimum_range(value: float | None) -> None:
    if value is not None and (not math.isfinite(value) or value < 0.0):
        raise ValueError("minimum_signal_range_bps must be finite and non-negative")


def _validate_utc_window(start: datetime, end: datetime) -> None:
    offsets = (start.utcoffset(), end.utcoffset())
    if any(offset is None or offset.total_seconds() != 0.0 for offset in offsets):
        raise ValueError("source-follow live selection requires UTC bounds")
    if start >= end:
        raise ValueError("source-follow live selection requires positive bounds")


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    offset = parsed.utcoffset()
    if offset is None or offset.total_seconds() != 0.0:
        raise ValueError("source artifact timestamps must be UTC")
    return parsed.astimezone(UTC)

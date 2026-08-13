"""Causal entry policy boundary for the pinned source-follow candidate."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import math
from typing import Literal, Protocol

from hypervector.regime.source_regime_diagnostics import SourceRegimeDiagnostics

EntryDirection = Literal["long", "short"]
SourceDirectionMode = Literal["short_only", "trend_bidirectional"]
SourceLongRecipeId = Literal[
    "bk_up_asia_conf06",
    "fade_td_eu",
    "bk_up_24h_challenger",
    "trend_up_24h_challenger",
    "trend_down_24h_direction_challenger",
]
_PRIMARY_CODES = frozenset(
    {"TREND_UP", "TREND_DOWN", "RANGE", "TRANSITION", "BREAKOUT", "UNKNOWN"}
)
_MINIMUM_CONFIDENCE = 0.70
_MINIMUM_RANGE_BPS = 0.0
_MAXIMUM_RANGE_BPS = 100.0
_MAXIMUM_HOLD_SECONDS = 86_400.0
_ENTRY_PULSE_SECONDS = 60.0


@dataclass(frozen=True)
class FiveMinuteBar:
    """One completed UTC five-minute Hyperliquid OHLCV bar."""

    timestamp_utc: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self) -> None:
        _validate_utc(self.timestamp_utc, "bar timestamp")
        if (
            self.timestamp_utc.minute % 5
            or self.timestamp_utc.second
            or self.timestamp_utc.microsecond
        ):
            raise ValueError("source bar timestamp must be on a five-minute boundary")
        prices = (self.open, self.high, self.low, self.close)
        if not all(math.isfinite(value) and value > 0.0 for value in prices):
            raise ValueError("source bar prices must be positive and finite")
        if self.high < max(self.open, self.low, self.close):
            raise ValueError("source bar high is inconsistent with OHLC")
        if self.low > min(self.open, self.high, self.close):
            raise ValueError("source bar low is inconsistent with OHLC")
        if not math.isfinite(self.volume) or self.volume < 0.0:
            raise ValueError("source bar volume must be nonnegative and finite")


@dataclass(frozen=True)
class _OneMinuteBar:
    timestamp_utc: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class FiveMinuteBarAssembler:
    """Aggregate completed contiguous 1m observations into causal 5m bars."""

    def __init__(self) -> None:
        self._last_timestamp: datetime | None = None
        self._pending: list[_OneMinuteBar] = []

    def update(
        self,
        *,
        timestamp_utc: datetime,
        open: float,
        high: float,
        low: float,
        close: float,
        volume: float,
    ) -> FiveMinuteBar | None:
        """Consume one completed 1m bar and emit a completed aligned 5m bar."""
        minute = _OneMinuteBar(timestamp_utc, open, high, low, close, volume)
        self._validate_minute(minute)
        self._last_timestamp = timestamp_utc
        if not self._pending and timestamp_utc.minute % 5:
            return None
        self._pending.append(minute)
        if len(self._pending) < 5:
            return None
        completed = self._aggregate()
        self._pending.clear()
        return completed

    def _validate_minute(self, bar: _OneMinuteBar) -> None:
        _validate_utc(bar.timestamp_utc, "one-minute bar timestamp")
        if bar.timestamp_utc.second or bar.timestamp_utc.microsecond:
            raise ValueError("one-minute bar timestamp must be minute-aligned")
        if self._last_timestamp is not None and bar.timestamp_utc != (
            self._last_timestamp + timedelta(minutes=1)
        ):
            raise ValueError("source assembler requires contiguous one-minute bars")
        FiveMinuteBar(
            timestamp_utc=bar.timestamp_utc.replace(
                minute=bar.timestamp_utc.minute // 5 * 5
            ),
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
        )

    def _aggregate(self) -> FiveMinuteBar:
        first = self._pending[0]
        if first.timestamp_utc.minute % 5 or len(self._pending) != 5:
            raise RuntimeError("source assembler has an incomplete five-minute group")
        return FiveMinuteBar(
            timestamp_utc=first.timestamp_utc,
            open=first.open,
            high=max(bar.high for bar in self._pending),
            low=min(bar.low for bar in self._pending),
            close=self._pending[-1].close,
            volume=sum(bar.volume for bar in self._pending),
        )


@dataclass(frozen=True)
class SourceRegimeLabel:
    """One confirmed label emitted by the pinned source classifier."""

    label_time_utc: datetime
    primary: str
    secondary: str | None
    confidence: float
    diagnostics: SourceRegimeDiagnostics | None = None

    def __post_init__(self) -> None:
        _validate_utc(self.label_time_utc, "source label timestamp")
        if self.primary not in _PRIMARY_CODES:
            raise ValueError(f"unsupported source primary regime: {self.primary!r}")
        if not math.isfinite(self.confidence) or not 0.0 <= self.confidence <= 1.0:
            raise ValueError("source confidence must be finite and within [0, 1]")


@dataclass(frozen=True)
class SourceLongObservation:
    """One exact pinned creator long recipe with no execution authority."""

    recipe_id: SourceLongRecipeId
    maximum_hold_seconds: float
    side: Literal["long"] = "long"
    authority: Literal["observe_only"] = "observe_only"

    def __post_init__(self) -> None:
        expected = {
            "bk_up_asia_conf06": 14_400.0,
            "fade_td_eu": 86_400.0,
            "bk_up_24h_challenger": 14_400.0,
            "trend_up_24h_challenger": 86_400.0,
            "trend_down_24h_direction_challenger": 86_400.0,
        }[self.recipe_id]
        if self.maximum_hold_seconds != expected:
            raise ValueError(
                f"{self.recipe_id} maximum hold must equal {expected:.0f} seconds"
            )


@dataclass(frozen=True)
class SourceFollowDecision:
    """One source label plus its causal entry-policy decision."""

    label_time_utc: datetime
    available_at_utc: datetime
    primary: str
    secondary: str | None
    confidence: float
    primary_onset: bool
    source_event: bool
    signal_range_bps: float
    entry_eligible: bool
    entry_direction: EntryDirection | None
    maximum_hold_seconds: float | None
    exclusion_reason: str | None
    bar_open: float
    bar_high: float
    bar_low: float
    bar_close: float
    bar_volume: float
    source_long_observation: SourceLongObservation | None = None
    regime_diagnostics: SourceRegimeDiagnostics | None = None


class SourceRegimeClassifier(Protocol):
    """Classifier boundary required by the source-follow policy."""

    def classify(self, bar: FiveMinuteBar) -> SourceRegimeLabel:
        """Return the confirmed source label for one completed bar."""


class SourceFollowRuntime:
    """Stateful causal source-follow entry policy."""

    def __init__(
        self,
        classifier: SourceRegimeClassifier,
        *,
        minimum_confidence: float = _MINIMUM_CONFIDENCE,
        minimum_range_bps: float = _MINIMUM_RANGE_BPS,
        maximum_range_bps: float = _MAXIMUM_RANGE_BPS,
        maximum_hold_seconds: float = _MAXIMUM_HOLD_SECONDS,
        entry_pulse_seconds: float = _ENTRY_PULSE_SECONDS,
        direction_mode: SourceDirectionMode = "short_only",
    ) -> None:
        _validate_policy(
            minimum_confidence,
            minimum_range_bps,
            maximum_range_bps,
            maximum_hold_seconds,
            entry_pulse_seconds,
        )
        self._classifier = classifier
        self._minimum_confidence = minimum_confidence
        self._minimum_range_bps = minimum_range_bps
        self._maximum_range_bps = maximum_range_bps
        self._maximum_hold_seconds = maximum_hold_seconds
        self._entry_pulse_seconds = entry_pulse_seconds
        self._direction_mode = direction_mode
        self._last_bar_time: datetime | None = None
        self._previous_primary: str | None = None
        self._active_from: datetime | None = None
        self._active_until: datetime | None = None
        self._active_direction: EntryDirection | None = None

    def update(self, bar: FiveMinuteBar) -> SourceFollowDecision:
        """Classify one completed bar and update the entry pulse."""
        self._validate_continuity(bar.timestamp_utc)
        label = self._classifier.classify(bar)
        if label.label_time_utc != bar.timestamp_utc:
            raise ValueError("source classifier label timestamp differs from input bar")
        onset = label.primary != self._previous_primary
        direction = _source_entry_direction(label, onset, self._direction_mode)
        source_event = (
            direction is not None and label.confidence >= self._minimum_confidence
        )
        range_bps = 10_000.0 * (bar.high - bar.low) / bar.open
        eligible = source_event and (
            self._minimum_range_bps <= range_bps <= self._maximum_range_bps
        )
        available = bar.timestamp_utc + timedelta(minutes=5)
        long_observation = _source_long_observation(
            label,
            onset,
            range_admitted=(
                self._minimum_range_bps <= range_bps <= self._maximum_range_bps
            ),
            minimum_confidence=self._minimum_confidence,
        )
        self._set_pulse(available, direction if eligible else None)
        self._last_bar_time = bar.timestamp_utc
        self._previous_primary = label.primary
        return SourceFollowDecision(
            label_time_utc=bar.timestamp_utc,
            available_at_utc=available,
            primary=label.primary,
            secondary=label.secondary,
            confidence=label.confidence,
            primary_onset=onset,
            source_event=source_event,
            signal_range_bps=range_bps,
            entry_eligible=eligible,
            entry_direction=direction if eligible else None,
            maximum_hold_seconds=self._maximum_hold_seconds if eligible else None,
            exclusion_reason=_exclusion_reason(
                label,
                onset,
                range_bps,
                minimum_confidence=self._minimum_confidence,
                minimum_range_bps=self._minimum_range_bps,
                maximum_range_bps=self._maximum_range_bps,
                direction_mode=self._direction_mode,
            ),
            bar_open=bar.open,
            bar_high=bar.high,
            bar_low=bar.low,
            bar_close=bar.close,
            bar_volume=bar.volume,
            source_long_observation=long_observation,
            regime_diagnostics=label.diagnostics,
        )

    def entry_direction_at(self, observed_at: datetime) -> EntryDirection | None:
        """Return the active one-minute entry pulse at an observed time."""
        _validate_utc(observed_at, "entry observation timestamp")
        if self._active_from is None or self._active_until is None:
            return None
        if self._active_from <= observed_at < self._active_until:
            return self._active_direction
        return None

    def _validate_continuity(self, timestamp: datetime) -> None:
        if self._last_bar_time is None:
            return
        if timestamp != self._last_bar_time + timedelta(minutes=5):
            raise ValueError("source classifier requires contiguous five-minute bars")

    def _set_pulse(
        self,
        available: datetime,
        direction: EntryDirection | None,
    ) -> None:
        if direction is None:
            return
        self._active_from = available
        self._active_until = available + timedelta(seconds=self._entry_pulse_seconds)
        self._active_direction = direction


def _validate_utc(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must be timezone-aware UTC")
    if value.tzinfo is not UTC:
        value.astimezone(UTC)


def _exclusion_reason(
    label: SourceRegimeLabel,
    onset: bool,
    range_bps: float,
    *,
    minimum_confidence: float,
    minimum_range_bps: float,
    maximum_range_bps: float,
    direction_mode: SourceDirectionMode,
) -> str | None:
    if not onset:
        return "not_primary_onset"
    if _source_entry_direction(label, onset, direction_mode) is None:
        if direction_mode == "short_only":
            return "primary_not_trend_down"
        return "primary_not_aligned_trend_or_upward_breakout"
    if label.confidence < minimum_confidence:
        return "source_confidence"
    if range_bps < minimum_range_bps:
        return "signal_range_below_minimum"
    if range_bps > maximum_range_bps:
        return "signal_range"
    return None


def _source_entry_direction(
    label: SourceRegimeLabel,
    onset: bool,
    direction_mode: SourceDirectionMode,
) -> EntryDirection | None:
    if not onset:
        return None
    if label.primary == "TREND_DOWN":
        return "short"
    if direction_mode == "short_only":
        return None
    if label.primary == "TREND_UP":
        return "long"
    secondary = (label.secondary or "").upper()
    if label.primary == "BREAKOUT" and secondary == "BK_UPWARD":
        return "long"
    return None


def _source_long_observation(
    label: SourceRegimeLabel,
    onset: bool,
    *,
    range_admitted: bool,
    minimum_confidence: float,
) -> SourceLongObservation | None:
    if not onset:
        return None
    hour = label.label_time_utc.hour
    secondary = (label.secondary or "").upper()
    if (
        label.primary == "BREAKOUT"
        and secondary == "BK_UPWARD"
        and label.confidence >= 0.6
        and hour < 8
    ):
        return SourceLongObservation("bk_up_asia_conf06", 14_400.0)
    if label.primary == "TREND_DOWN" and 7 <= hour < 16:
        return SourceLongObservation("fade_td_eu", 86_400.0)
    if (
        label.primary == "BREAKOUT"
        and secondary == "BK_UPWARD"
        and label.confidence >= 0.6
    ):
        return SourceLongObservation("bk_up_24h_challenger", 14_400.0)
    if not range_admitted or label.confidence < minimum_confidence:
        return None
    if label.primary == "TREND_UP":
        return SourceLongObservation("trend_up_24h_challenger", 86_400.0)
    if label.primary == "TREND_DOWN":
        return SourceLongObservation(
            "trend_down_24h_direction_challenger",
            86_400.0,
        )
    return None


def _validate_policy(
    minimum_confidence: float,
    minimum_range_bps: float,
    maximum_range_bps: float,
    maximum_hold_seconds: float,
    entry_pulse_seconds: float,
) -> None:
    if not math.isfinite(minimum_confidence) or not 0.0 <= minimum_confidence <= 1.0:
        raise ValueError("minimum confidence must be within [0, 1]")
    ranges = (minimum_range_bps, maximum_range_bps)
    if not all(math.isfinite(value) and value >= 0.0 for value in ranges):
        raise ValueError("source range bounds must be finite and non-negative")
    if minimum_range_bps > maximum_range_bps:
        raise ValueError("minimum range must not exceed maximum range")
    if not math.isfinite(maximum_hold_seconds) or maximum_hold_seconds <= 0.0:
        raise ValueError("maximum hold seconds must be finite and positive")
    if not math.isfinite(entry_pulse_seconds) or entry_pulse_seconds <= 0.0:
        raise ValueError("entry pulse seconds must be finite and positive")

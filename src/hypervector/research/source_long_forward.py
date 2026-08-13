"""Forward-only outcome accounting for source-faithful long observations."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Iterable, Literal

from hypervector.data.hl_event_stream import RecordedEvent
from hypervector.data.hl_events import (
    AssetContextEvent,
    L2SnapshotEvent,
    PublicTradeEvent,
    StreamGap,
)
from hypervector.regime.source_follow_runtime import (
    SourceLongObservation,
    SourceLongRecipeId,
)
from hypervector.research.source_follow_portfolio_models import (
    SourcePortfolioReplayConfig,
    SourcePortfolioReport,
    SourceReplayFunding,
    SourceReplayMark,
    SourceSignal,
    utc_ms,
)
from hypervector.research.source_follow_portfolio_replay import (
    SourcePortfolioReplaySession,
)

ForwardStatus = Literal[
    "awaiting_evidence",
    "entry_pending",
    "open",
    "no_fill",
    "target_completed",
    "time_exited",
    "liquidated",
]
_HOUR_MS = 3_600_000


@dataclass(frozen=True)
class SourceLongForwardSpec:
    """Identity and source-frozen holding policy for one long observation."""

    recipe_id: SourceLongRecipeId
    signal_time_utc: str
    maximum_hold_seconds: float

    def __post_init__(self) -> None:
        SourceLongObservation(self.recipe_id, self.maximum_hold_seconds)
        utc_ms(self.signal_time_utc)

    @property
    def observation_id(self) -> str:
        """Return the stable signal identity used by append-only ledgers."""
        return f"{self.signal_time_utc}|{self.recipe_id}"


@dataclass(frozen=True)
class SourceLongForwardResult:
    """One point-in-time counterfactual outcome backed by venue evidence."""

    observation_id: str
    recipe_id: SourceLongRecipeId
    status: ForwardStatus
    evidence_complete: bool
    active_stream_gaps: int
    funding_evidence_gaps: int
    last_event_time_utc: str | None
    report: SourcePortfolioReport

    def to_dict(self) -> dict[str, object]:
        """Return an append-only JSON-compatible telemetry payload."""
        return {
            "observation_id": self.observation_id,
            "recipe_id": self.recipe_id,
            "status": self.status,
            "evidence_complete": self.evidence_complete,
            "active_stream_gaps": self.active_stream_gaps,
            "funding_evidence_gaps": self.funding_evidence_gaps,
            "last_event_time_utc": self.last_event_time_utc,
            "report": self.report.to_dict(),
        }


def evaluate_source_long_forward(
    events: Iterable[RecordedEvent],
    spec: SourceLongForwardSpec,
    config: SourcePortfolioReplayConfig,
) -> SourceLongForwardResult:
    """Resolve one long observation through production maker matching."""
    resolved_config = replace(
        config,
        maximum_hold_seconds=spec.maximum_hold_seconds,
        receipt_timestamp_source="recorded",
    )
    session = SourcePortfolioReplaySession(
        (SourceSignal(spec.signal_time_utc, direction="long"),),
        resolved_config,
    )
    signal_ms = utc_ms(spec.signal_time_utc)
    state = _EvaluationState(last_funding_hour_ms=_hour_floor(signal_ms))
    for event in sorted(events, key=_event_sort_key):
        timestamp = _event_time_ms(event)
        if timestamp < signal_ms:
            continue
        _apply_recorded_event(session, event, state)
        state.last_event_ms = timestamp
        if session.report().completed_trades:
            break
    report = session.report()
    return SourceLongForwardResult(
        observation_id=spec.observation_id,
        recipe_id=spec.recipe_id,
        status=_status(session, report, state.last_event_ms),
        evidence_complete=(
            state.active_stream_gaps == 0 and state.funding_evidence_gaps == 0
        ),
        active_stream_gaps=state.active_stream_gaps,
        funding_evidence_gaps=state.funding_evidence_gaps,
        last_event_time_utc=_iso_ms(state.last_event_ms),
        report=report,
    )


@dataclass
class _EvaluationState:
    last_funding_hour_ms: int
    last_event_ms: int | None = None
    active_stream_gaps: int = 0
    funding_evidence_gaps: int = 0


def _apply_recorded_event(
    session: SourcePortfolioReplaySession,
    event: RecordedEvent,
    state: _EvaluationState,
) -> None:
    if isinstance(event, StreamGap):
        if not session.is_idle:
            state.active_stream_gaps += 1
        return
    if isinstance(event, AssetContextEvent):
        _apply_context(session, event, state)
        return
    if not isinstance(event, (L2SnapshotEvent, PublicTradeEvent)):
        raise TypeError(f"unsupported forward event {type(event).__name__}")
    session.apply(event)


def _apply_context(
    session: SourcePortfolioReplaySession,
    event: AssetContextEvent,
    state: _EvaluationState,
) -> None:
    timestamp = event.observed_ts_ms
    session.apply(SourceReplayMark(timestamp, event.mark_price, event.oracle_price))
    current_hour = _hour_floor(timestamp)
    if session.report().open_positions == 0:
        state.last_funding_hour_ms = current_hour
        return
    elapsed_hours = (current_hour - state.last_funding_hour_ms) // _HOUR_MS
    if elapsed_hours <= 0:
        return
    if elapsed_hours == 1:
        session.apply(SourceReplayFunding(timestamp, event.funding_rate_hourly))
    else:
        state.funding_evidence_gaps += int(elapsed_hours - 1)
    state.last_funding_hour_ms = current_hour


def _status(
    session: SourcePortfolioReplaySession,
    report: SourcePortfolioReport,
    last_event_ms: int | None,
) -> ForwardStatus:
    if report.trades:
        return report.trades[-1].status
    if report.open_positions:
        return "open"
    if not session.is_idle:
        return "entry_pending"
    if report.submitted_entries and report.entry_filled_quantity == 0.0:
        return "no_fill"
    if last_event_ms is None:
        return "awaiting_evidence"
    return "awaiting_evidence"


def _event_sort_key(event: RecordedEvent) -> tuple[int, int, int]:
    timestamp = _event_time_ms(event)
    if isinstance(event, AssetContextEvent):
        return timestamp, 0, 0
    if isinstance(event, StreamGap):
        return timestamp, 1, 0
    if isinstance(event, L2SnapshotEvent):
        return timestamp, 2, 0
    return timestamp, 3, event.trade_id


def _event_time_ms(event: RecordedEvent) -> int:
    if isinstance(event, AssetContextEvent):
        return event.observed_ts_ms
    if isinstance(event, StreamGap):
        return event.detected_ts_ns // 1_000_000
    return event.exchange_ts_ms


def _hour_floor(timestamp_ms: int) -> int:
    return timestamp_ms // _HOUR_MS * _HOUR_MS


def _iso_ms(timestamp_ms: int | None) -> str | None:
    if timestamp_ms is None:
        return None
    return datetime.fromtimestamp(timestamp_ms / 1_000, tz=UTC).isoformat()

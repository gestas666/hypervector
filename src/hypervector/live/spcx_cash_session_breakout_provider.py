"""US cash-session-only SPCX long breakout probation provider."""

from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import replace
from typing import Protocol
from zoneinfo import ZoneInfo

import pandas as pd

from hypervector.live.bidirectional_intents import StrategyIntent
from hypervector.live.provider_evaluation import IntentBatch, ProviderEvaluation
from hypervector.live.provider_readiness import SignalReadiness
from hypervector.research.hip3_cash_open_gap_reversal_signals import (
    Hip3CashOpenGapReversalConfig,
    spcx_cash_open_live_config,
)

SPCX_CASH_SESSION_LONG_STRATEGY = "hip3_spcx_cash_session_fresh15_long_v4"
_NEW_YORK = ZoneInfo("America/New_York")
_BAR_MINUTES = 15
_CASH_OPEN_MINUTE = 9 * 60 + 30
_REGULAR_CLOSE_BAR_OPEN_MINUTE = 15 * 60 + 45
_SESSION_CONFIG = spcx_cash_open_live_config()


class SpcxSourceCollectorProtocol(Protocol):
    """Callable contract for the frozen HIP-3 breakout source."""

    def __call__(
        self,
        bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> IntentBatch: ...


class SpcxCashSessionBreakoutCollector:
    """Restrict SPCX breakout authority to cash-session long signals."""

    def __init__(self, *, source_collector: SpcxSourceCollectorProtocol) -> None:
        """Bind the causal source whose signals will be narrowed."""
        self._source = source_collector

    @property
    def source_collector(self) -> SpcxSourceCollectorProtocol:
        """Return the causally corrected source used by this narrowed route."""
        return self._source

    def __call__(
        self,
        bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> IntentBatch:
        """Return long entries only inside the New York regular session."""
        if symbol != "xyz:SPCX":
            raise ValueError("SPCX cash-session provider supports xyz:SPCX only")
        source = self._source(
            bars,
            symbol=symbol,
            observed_at=observed_at,
            after_decision_time_ms=after_decision_time_ms,
        )
        evaluations = _evaluations_with_missed_close_recovery(source.evaluations)
        intents = tuple(_intent(row) for row in evaluations if row.eligible)
        return IntentBatch(intents, source.latest_decision_time_ms, evaluations)


def _evaluations_with_missed_close_recovery(
    source: tuple[ProviderEvaluation, ...],
) -> tuple[ProviderEvaluation, ...]:
    evaluations: list[ProviderEvaluation] = []
    missed_close = False
    for row in source:
        evaluation = _evaluation(row)
        missed_close |= evaluation.exit_reason == "spcx_cash_session_close"
        if missed_close and not evaluation.exit_sides:
            evaluation = replace(
                evaluation,
                decision_action="close_long",
                eligible=False,
                reason="spcx_cash_session_close_recovery",
                exit_sides=frozenset({"long"}),
                exit_reason="spcx_cash_session_close_recovery",
            )
        evaluations.append(evaluation)
    return tuple(evaluations)


def _evaluation(source: ProviderEvaluation) -> ProviderEvaluation:
    cash_session = _is_regular_cash_session(source.decision_time_ms)
    session_exit_reason = _session_exit_reason(source.decision_time_ms)
    session_close = session_exit_reason == "spcx_cash_session_close"
    long_side = source.side == "long"
    eligible = source.eligible and cash_session and long_side
    reason = _reason(source, cash_session, long_side, session_close)
    readiness = _readiness(source.readiness, cash_session, long_side, reason)
    return replace(
        source,
        strategy_id=SPCX_CASH_SESSION_LONG_STRATEGY,
        decision_action=(
            "enter_long"
            if eligible
            else "close_long"
            if session_exit_reason is not None
            else "hold"
        ),
        eligible=eligible,
        reason=reason,
        readiness=readiness,
        trigger="spcx_cash_session_long_breakout" if eligible else "none",
        exit_sides=(
            frozenset({"long"}) if session_exit_reason is not None else frozenset()
        ),
        exit_reason=session_exit_reason,
    )


def _readiness(
    source: SignalReadiness,
    cash_session: bool,
    long_side: bool,
    reason: str,
) -> SignalReadiness:
    extra_blockers = (
        () if (cash_session and long_side) or reason in source.blockers else (reason,)
    )
    return SignalReadiness(
        side=source.side,
        conditions_met=source.conditions_met + int(cash_session) + int(long_side),
        conditions_required=source.conditions_required + 2,
        blockers=source.blockers + extra_blockers,
        indicators=source.indicators
        + (
            f"US CASH SESSION {'OPEN' if cash_session else 'CLOSED'}",
            f"SPCX LONG SIDE {'YES' if long_side else 'NO'}",
        ),
        metrics={
            **source.metrics,
            "us_regular_cash_session": cash_session,
            "execution_side": "long",
        },
    )


def _reason(
    source: ProviderEvaluation,
    cash_session: bool,
    long_side: bool,
    session_close: bool,
) -> str:
    if session_close:
        return "spcx_cash_session_close"
    if source.eligible and not long_side:
        return "spcx_long_only"
    if source.eligible and _is_cash_session_bar_incomplete(source.decision_time_ms):
        return "cash_session_bar_incomplete"
    if source.eligible and not cash_session:
        return "outside_us_regular_cash_session"
    return "spcx_cash_session_long_breakout" if source.eligible else source.reason


def _is_regular_cash_session(decision_time_ms: int) -> bool:
    local = _local_time(decision_time_ms)
    minute = local.hour * 60 + local.minute
    close_minute = _session_close_boundary_minute(local, _SESSION_CONFIG)
    return bool(
        _is_scheduled_session(local, _SESSION_CONFIG)
        and _CASH_OPEN_MINUTE + _BAR_MINUTES <= minute < close_minute
    )


def _is_cash_session_bar_incomplete(decision_time_ms: int) -> bool:
    local = _local_time(decision_time_ms)
    minute = local.hour * 60 + local.minute
    return _is_scheduled_session(local, _SESSION_CONFIG) and minute == _CASH_OPEN_MINUTE


def _session_exit_reason(decision_time_ms: int) -> str | None:
    if _is_regular_cash_session(decision_time_ms):
        return None
    local = _local_time(decision_time_ms)
    close_minute = _session_close_boundary_minute(local, _SESSION_CONFIG)
    minute = local.hour * 60 + local.minute
    if _is_scheduled_session(local, _SESSION_CONFIG) and minute == close_minute:
        return "spcx_cash_session_close"
    return "spcx_cash_session_closed"


def _local_time(decision_time_ms: int) -> datetime:
    value = datetime.fromtimestamp(decision_time_ms / 1_000, tz=timezone.utc)
    return value.astimezone(_NEW_YORK)


def _is_scheduled_session(
    local: datetime,
    config: Hip3CashOpenGapReversalConfig,
) -> bool:
    return local.weekday() < 5 and local.date() not in config.closed_session_dates


def _session_close_boundary_minute(
    local: datetime,
    config: Hip3CashOpenGapReversalConfig,
) -> int:
    close_bar_open = dict(config.early_close_minutes).get(
        local.date(), _REGULAR_CLOSE_BAR_OPEN_MINUTE
    )
    return close_bar_open + _BAR_MINUTES


def _intent(evaluation: ProviderEvaluation) -> StrategyIntent:
    return StrategyIntent(
        strategy_id=evaluation.strategy_id,
        symbol=evaluation.symbol,
        side="long",
        decision_time_ms=evaluation.decision_time_ms,
        reference_price=evaluation.reference_price,
        reason="spcx_cash_session_long_breakout",
    )

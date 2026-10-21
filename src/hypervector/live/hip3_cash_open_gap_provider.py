"""Live-candidate SPCX cash-open gap-reversal provider."""

from __future__ import annotations

from dataclasses import replace
from typing import Protocol

import pandas as pd

from hypervector.live.bidirectional_intents import StrategyIntent
from hypervector.live.provider_evaluation import IntentBatch, ProviderEvaluation
from hypervector.live.provider_readiness import SignalReadiness
from hypervector.research.hip3_cash_open_gap_reversal_signals import (
    Hip3CashOpenGapReversalConfig,
    build_hip3_cash_open_gap_reversal_signals,
    latest_completed_cash_session_boundary_ms,
    spcx_cash_open_live_config,
)

HIP3_SPCX_CASH_OPEN_STRATEGY = "hip3_spcx_cash_open_gap_reversal_bidirectional_15m_v1"
HIP3_SPCX_CASH_OPEN_PROFILE = "spcx_cash_open_gap_reversal_15m_live_candidate_v1"
_SYMBOL = "xyz:SPCX"
_BAR_MS = 900_000
_LOOKBACK_MS = 7 * 86_400_000


class CashOpenTradeBarSourceProtocol(Protocol):
    """Return exact completed public-trade bars at one receipt cutoff."""

    def completed_bars(
        self, *, observed_at_ms: int, minimum_start_ms: int
    ) -> pd.DataFrame:
        """Return an ordered gap-aware 15-minute frame."""


class Hip3CashOpenGapCollector:
    """Translate frozen SPCX cash-open signals into attributed intents."""

    def __init__(
        self,
        *,
        source: CashOpenTradeBarSourceProtocol,
        config: Hip3CashOpenGapReversalConfig | None = None,
    ) -> None:
        self._source = source
        self._config = config or spcx_cash_open_live_config()

    def __call__(
        self,
        bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> IntentBatch:
        """Evaluate unseen completed bars without replaying startup entries."""
        del bars
        if symbol != _SYMBOL:
            raise ValueError("SPCX cash-open collector received the wrong symbol")
        observed_ms = _timestamp_ms(observed_at)
        minimum_start_ms = observed_ms - _LOOKBACK_MS
        completed_boundary = latest_completed_cash_session_boundary_ms(
            observed_ms,
            minimum_start_ms,
            self._config,
        )
        if after_decision_time_ms is not None and (
            completed_boundary is None or completed_boundary <= after_decision_time_ms
        ):
            return IntentBatch((), after_decision_time_ms, ())
        frame = self._source.completed_bars(
            observed_at_ms=observed_ms,
            minimum_start_ms=minimum_start_ms,
        )
        boundary = int(frame.index[-1].timestamp() * 1_000) + _BAR_MS
        if after_decision_time_ms is not None and boundary <= after_decision_time_ms:
            return IntentBatch((), after_decision_time_ms, ())
        signals = build_hip3_cash_open_gap_reversal_signals(frame, self._config)
        positions = _new_positions(frame, after_decision_time_ms)
        if after_decision_time_ms is None:
            evaluation = replace(
                _evaluation(frame, signals, positions[-1], self._config),
                backend_non_action_reason="activation_readiness_seed",
            )
            return IntentBatch((), boundary, (evaluation,))
        evaluations = tuple(
            _evaluation(frame, signals, value, self._config) for value in positions
        )
        intents = tuple(_intent(value) for value in evaluations if value.eligible)
        return IntentBatch(intents, boundary, evaluations)


def _new_positions(
    frame: pd.DataFrame, after_decision_time_ms: int | None
) -> tuple[pd.Timestamp, ...]:
    prior = -1 if after_decision_time_ms is None else after_decision_time_ms
    positions = tuple(
        value
        for value in frame.index
        if int(value.timestamp() * 1_000) + _BAR_MS > prior
    )
    if not positions:
        raise ValueError("SPCX cash-open source did not advance its decision boundary")
    return positions


def _evaluation(
    frame: pd.DataFrame,
    signals: pd.DataFrame,
    timestamp: pd.Timestamp,
    config: Hip3CashOpenGapReversalConfig,
) -> ProviderEvaluation:
    signal = signals.loc[timestamp]
    side = (
        "long"
        if bool(signal["long_entry"])
        else "short"
        if bool(signal["short_entry"])
        else None
    )
    exiting = bool(signal["long_exit"]) or bool(signal["short_exit"])
    exit_reason = _exit_reason(frame, timestamp, exiting)
    reason = _reason(signal, side, exit_reason, config.gap_threshold_bps)
    target = float(signal["target_price"]) if side is not None else None
    trade_count = int(frame.loc[timestamp, "public_trade_count"])
    source_gap_count = int(frame.loc[timestamp, "gap_before_bars"])
    readiness = _readiness(
        signal,
        side,
        trade_count,
        source_gap_count,
        config.gap_threshold_bps,
    )
    return ProviderEvaluation(
        strategy_id=HIP3_SPCX_CASH_OPEN_STRATEGY,
        symbol=_SYMBOL,
        decision_time_ms=int(timestamp.timestamp() * 1_000) + _BAR_MS,
        reference_price=float(frame.loc[timestamp, "close"]),
        decision_action=f"enter_{side}" if side else "exit_both" if exiting else "hold",
        eligible=side is not None,
        reason=reason,
        side=side,
        readiness=readiness,
        trigger="cash_open_gap_fade" if side else "none",
        exit_sides=frozenset({"long", "short"}) if exiting else frozenset(),
        exit_reason=exit_reason,
        target_anchor=target,
    )


def _readiness(
    signal: pd.Series,
    side: str | None,
    public_trade_count: int,
    source_gap_count: int,
    gap_threshold_bps: float,
) -> SignalReadiness:
    raw_gap = signal["opening_gap_bps"]
    gap = None if pd.isna(raw_gap) else float(raw_gap)
    prior = signal["previous_cash_close"]
    conditions = (
        source_gap_count == 0,
        bool(signal["session_eligible"]),
        int(signal["local_minute"]) == 570,
        pd.notna(signal["previous_cash_close"]),
        gap is not None and abs(gap) >= gap_threshold_bps,
        side is not None,
    )
    return SignalReadiness(
        side=side,
        conditions_met=sum(conditions),
        conditions_required=len(conditions),
        blockers=_blockers(
            signal,
            side,
            gap,
            source_gap_count,
            gap_threshold_bps,
        ),
        indicators=(
            "OPEN GAP N/A" if gap is None else f"OPEN GAP {gap:+.2f} BPS",
            f"THRESHOLD {gap_threshold_bps:.2f} BPS",
            "PRIOR CLOSE N/A"
            if pd.isna(prior)
            else f"TARGET PRIOR CLOSE {float(prior):.4f}",
            f"SOURCE WS TRADES {public_trade_count}",
            f"SOURCE GAPS {source_gap_count}",
        ),
        metrics={
            "opening_gap_bps": gap,
            "gap_threshold_bps": gap_threshold_bps,
            "prior_cash_close": None if pd.isna(prior) else float(prior),
            "public_trade_count": public_trade_count,
            "gap_before_bars": source_gap_count,
            "signal_source": "hyperliquid_ws_trades",
        },
    )


def _blockers(
    signal: pd.Series,
    side: str | None,
    gap: float | None,
    source_gap_count: int,
    gap_threshold_bps: float,
) -> tuple[str, ...]:
    if source_gap_count > 0:
        return ("cash_open_trade_gap",)
    if side is not None:
        return ()
    if not bool(signal["session_eligible"]):
        return ("cash_session_closed",)
    if int(signal["local_minute"]) != 570:
        return ("not_cash_open_decision",)
    if pd.isna(signal["previous_cash_close"]):
        return ("prior_close_unavailable",)
    if gap is None:
        return ("gap_unavailable",)
    if abs(gap) < gap_threshold_bps:
        return ("gap_below_threshold",)
    return ("gap_reverted_before_decision",)


def _exit_reason(
    frame: pd.DataFrame, timestamp: pd.Timestamp, exiting: bool
) -> str | None:
    if not exiting:
        return None
    if float(frame.loc[timestamp, "gap_before_bars"]) > 0.0:
        return "source_recovery"
    return "cash_session_close"


def _reason(
    signal: pd.Series,
    side: str | None,
    exit_reason: str | None,
    gap_threshold_bps: float,
) -> str:
    if side is not None:
        return "cash_open_gap_reversal_confirmed"
    if exit_reason is not None:
        return exit_reason
    if int(signal["local_minute"]) != 570:
        return "not_cash_open_decision"
    if not bool(signal["session_eligible"]):
        return "cash_session_closed"
    if pd.isna(signal["previous_cash_close"]):
        return "prior_cash_close_unavailable"
    if abs(float(signal["opening_gap_bps"])) < gap_threshold_bps:
        return "cash_open_gap_below_threshold"
    return "cash_open_gap_reverted_before_decision"


def _intent(evaluation: ProviderEvaluation) -> StrategyIntent:
    if evaluation.side not in {"long", "short"} or evaluation.target_anchor is None:
        raise ValueError("eligible SPCX cash-open evaluation is incomplete")
    return StrategyIntent(
        strategy_id=evaluation.strategy_id,
        symbol=evaluation.symbol,
        side=evaluation.side,
        decision_time_ms=evaluation.decision_time_ms,
        reference_price=evaluation.reference_price,
        reason=evaluation.reason,
        target_anchor=evaluation.target_anchor,
    )


def _timestamp_ms(value: pd.Timestamp) -> int:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise ValueError("SPCX cash-open observed_at must be timezone-aware")
    return int(timestamp.timestamp() * 1_000)

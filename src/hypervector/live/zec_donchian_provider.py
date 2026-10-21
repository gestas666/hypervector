"""Causal long-only ZEC Donchian/ATR probation provider."""

from __future__ import annotations

import math
from typing import Protocol

import pandas as pd

from hypervector.live.bidirectional_intents import StrategyIntent
from hypervector.live.hip3_provider_inputs import (
    completed_hip3_inputs,
    decision_time_ms,
)
from hypervector.live.provider_evaluation import IntentBatch, ProviderEvaluation
from hypervector.live.provider_readiness import SignalReadiness
from hypervector.research.donchian_atr_breakout_signals import (
    DonchianAtrBreakoutConfig,
    build_donchian_atr_breakout_signals,
)

ZEC_DONCHIAN_LONG_STRATEGY = "zec_donchian_20_10_atr20_long_v1"


class DonchianSignalBuilderProtocol(Protocol):
    """Injectable completed-4h signal builder for deterministic tests."""

    def __call__(
        self,
        bars: pd.DataFrame,
        config: DonchianAtrBreakoutConfig,
    ) -> pd.DataFrame: ...


class ZecDonchianLongCollector:
    """Emit long breakouts with ATR stops and ten-bar channel exits."""

    def __init__(
        self,
        *,
        signal_builder: DonchianSignalBuilderProtocol = (
            build_donchian_atr_breakout_signals
        ),
        config: DonchianAtrBreakoutConfig | None = None,
    ) -> None:
        """Bind the preregistered 20/10 channel and ATR20-times-two recipe."""
        self._signal_builder = signal_builder
        self._config = config or DonchianAtrBreakoutConfig()

    def __call__(
        self,
        bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> IntentBatch:
        """Evaluate unseen 15m rows using only completed four-hour signals."""
        if symbol != "ZEC":
            raise ValueError("ZEC Donchian provider supports ZEC only")
        frame, positions, boundary = completed_hip3_inputs(
            bars,
            observed_at,
            after_decision_time_ms,
        )
        signals = self._signal_builder(frame, self._config)
        readiness_signals = signals.copy()
        state_columns = ("prior_entry_high", "prior_exit_low", "atr")
        continuity_segments = frame["gap_before_bars"].gt(0).cumsum()
        readiness_signals.loc[:, state_columns] = (
            readiness_signals.loc[:, state_columns].groupby(continuity_segments).ffill()
        )
        evaluations = tuple(
            _evaluation(
                timestamp,
                frame.loc[timestamp],
                readiness_signals.loc[timestamp],
            )
            for timestamp in positions
        )
        intents = tuple(_intent(row) for row in evaluations if row.eligible)
        return IntentBatch(intents, boundary, evaluations)


def _evaluation(
    timestamp: pd.Timestamp,
    bar: pd.Series,
    signal: pd.Series,
) -> ProviderEvaluation:
    long_entry = bool(signal.get("long_entry", False))
    short_entry = bool(signal.get("short_entry", False))
    long_exit = bool(signal.get("long_exit", False))
    history_ready = _finite(signal.get("prior_entry_high"))
    atr_ready = _finite(signal.get("atr"))
    eligible = long_entry and history_ready and atr_ready
    side = "long" if long_entry else "short" if short_entry else None
    exit_sides = frozenset({"long"}) if long_exit else frozenset()
    reason = _reason(eligible, short_entry, history_ready, atr_ready, long_exit)
    return ProviderEvaluation(
        strategy_id=ZEC_DONCHIAN_LONG_STRATEGY,
        symbol="ZEC",
        decision_time_ms=decision_time_ms(timestamp),
        reference_price=float(bar["close"]),
        decision_action=(
            "enter_long" if eligible else "close_long" if long_exit else "hold"
        ),
        eligible=eligible,
        reason=reason,
        side=side,
        readiness=_readiness(signal, side, history_ready, atr_ready, eligible),
        trigger="completed_4h_donchian_long" if eligible else "none",
        confidence=None,
        exit_sides=exit_sides,
        exit_reason="donchian_10_bar_long_exit" if long_exit else None,
    )


def _readiness(
    signal: pd.Series,
    side: str | None,
    history_ready: bool,
    atr_ready: bool,
    eligible: bool,
) -> SignalReadiness:
    blockers = []
    if not history_ready:
        blockers.append("donchian_history_unready")
    if not atr_ready:
        blockers.append("atr_unready")
    if side == "short":
        blockers.append("zec_long_only")
    elif not eligible:
        blockers.append("awaiting_long_donchian_breakout")
    return SignalReadiness(
        side=side,
        conditions_met=sum((history_ready, atr_ready, eligible)),
        conditions_required=3,
        blockers=tuple(blockers),
        indicators=(
            f"DONCHIAN HISTORY {'READY' if history_ready else 'WAIT'}",
            f"ATR20 {'READY' if atr_ready else 'WAIT'}",
            f"LONG BREAKOUT {'YES' if eligible else 'NO'}",
        ),
        metrics={
            "atr": _finite_or_none(signal.get("atr")),
            "prior_entry_high": _finite_or_none(signal.get("prior_entry_high")),
            "prior_exit_low": _finite_or_none(signal.get("prior_exit_low")),
            "stop_price": _finite_or_none(signal.get("stop_price")),
        },
    )


def _reason(
    eligible: bool,
    short_entry: bool,
    history_ready: bool,
    atr_ready: bool,
    long_exit: bool,
) -> str:
    if eligible:
        return "long_donchian_breakout"
    if long_exit:
        return "long_donchian_channel_exit"
    if short_entry:
        return "zec_long_only"
    if not history_ready or not atr_ready:
        return "indicator_history_unready"
    return "entry_condition_absent"


def _intent(evaluation: ProviderEvaluation) -> StrategyIntent:
    stop_anchor = evaluation.readiness.metrics.get("stop_price")
    return StrategyIntent(
        strategy_id=evaluation.strategy_id,
        symbol=evaluation.symbol,
        side="long",
        decision_time_ms=evaluation.decision_time_ms,
        reference_price=evaluation.reference_price,
        reason="completed_4h_donchian_long",
        stop_anchor=float(stop_anchor)
        if isinstance(stop_anchor, (int, float))
        else None,
    )


def _finite(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _finite_or_none(value: object) -> float | None:
    return float(value) if _finite(value) else None

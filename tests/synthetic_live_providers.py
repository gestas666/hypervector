"""Synthetic, test-only live signal providers registered from the test suite.

These exist only so the generic cohort engine (profile loading, validation,
execution plans, sizing, stops, ledgers, restart, checkpoint and audit) can be
exercised without any real strategy. Each provider emits deterministic intents
from completed-bar bodies: a bar that closes at least ``_BODY_FRACTION`` above
its open is a long intent and one that closes as far below is a short intent.
They are registered from ``tests/conftest.py``; nothing in ``src/`` knows them.
"""

from __future__ import annotations

from collections.abc import Mapping
import math

import pandas as pd

from hypervector.live.bidirectional_intents import StrategyIntent
from hypervector.live.provider_evaluation import IntentBatch, ProviderEvaluation
from hypervector.live.provider_readiness import SignalReadiness
from hypervector.live.provider_registration import (
    ProviderCapability,
    ProviderRegistration,
)
from hypervector.live.provider_registry import register_provider

# (strategy_id, signal timeframe, readiness lookback minutes, stop anchor, target anchor)
SYNTHETIC_PROVIDERS: tuple[tuple[str, str, int, bool, bool], ...] = (
    ("test_alignment_1m", "1m", 1440, False, False),
    ("test_breakout_1m", "1m", 2, False, False),
    ("test_continuation_1m", "1m", 2, False, False),
    ("test_fade_1m", "1m", 2, False, False),
    ("test_long_bias_1m", "1m", 2880, False, False),
    ("test_long_stop_1m", "1m", 61, False, False),
    ("test_long_target_1m", "1m", 61, False, False),
    ("test_mirror_1m", "1m", 6, False, False),
    ("test_loose_1m", "1m", 2, False, False),
    ("test_loose_fixed_1m", "1m", 2, False, False),
    ("test_pullback_1m", "1m", 2, False, False),
    ("test_short_bias_1m", "1m", 2880, False, False),
    ("test_squeeze_1m", "1m", 2, False, False),
    ("test_short_drift_5m", "5m", 31, True, False),
    ("test_short_trend_5m", "5m", 31, True, False),
    ("test_trend_5m", "5m", 31, True, False),
    ("test_anchor_target_15m", "15m", 10080, True, True),
    ("test_band_a_15m", "15m", 16, True, False),
    ("test_band_b_15m", "15m", 16, True, False),
    ("test_channel_15m", "15m", 2880, True, False),
    ("test_channel_fast_15m", "15m", 2880, True, False),
    ("test_channel_long_15m", "15m", 43200, True, False),
    ("test_channel_short_15m", "15m", 2880, True, False),
    ("test_open_long_15m", "15m", 375, True, False),
    ("test_reentry_15m", "15m", 2880, True, False),
    ("test_session_a_15m", "15m", 16, True, False),
    ("test_session_b_15m", "15m", 16, True, False),
    ("test_session_c_15m", "15m", 16, True, False),
    ("test_session_d_15m", "15m", 16, True, False),
    ("test_session_e_15m", "15m", 16, True, False),
    ("test_session_f_15m", "15m", 16, True, False),
    ("test_session_g_15m", "15m", 16, True, False),
)
_BODY_FRACTION = 0.005
_MINUTES = {"1m": 1, "5m": 5, "15m": 15}


class SyntheticBodyCollector:
    """Deterministic completed-bar collector used only by tests."""

    def __init__(
        self,
        *,
        strategy_id: str,
        timeframe: str,
        stop_anchor: bool = False,
        target_anchor: bool = False,
    ) -> None:
        self.strategy_id = strategy_id
        self._duration = pd.Timedelta(minutes=_MINUTES[timeframe])
        self._stop_anchor = stop_anchor
        self._target_anchor = target_anchor

    def __call__(
        self,
        bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> IntentBatch:
        """Return one evaluation per unseen completed bar and intents for big bodies."""
        boundary = 0 if after_decision_time_ms is None else after_decision_time_ms
        observed_ms = int(pd.Timestamp(observed_at).timestamp() * 1_000)
        intents: list[StrategyIntent] = []
        evaluations: list[ProviderEvaluation] = []
        latest = boundary
        for row in bars.itertuples(index=False):
            opened = pd.Timestamp(row.timestamp)
            decision_ms = int((opened + self._duration).timestamp() * 1_000)
            if not boundary < decision_ms <= observed_ms:
                continue
            evaluation, intent = self._evaluate(symbol, decision_ms, row)
            evaluations.append(evaluation)
            if intent is not None:
                intents.append(intent)
            latest = decision_ms
        return IntentBatch(tuple(intents), latest, tuple(evaluations))

    def _evaluate(
        self, symbol: str, decision_ms: int, row: object
    ) -> tuple[ProviderEvaluation, StrategyIntent | None]:
        open_price = float(row.open)  # type: ignore[attr-defined]
        close = float(row.close)  # type: ignore[attr-defined]
        body = close / open_price - 1.0
        side = (
            "long"
            if body >= _BODY_FRACTION
            else "short"
            if body <= -_BODY_FRACTION
            else None
        )
        readiness = SignalReadiness(
            side=side,
            conditions_met=int(side is not None),
            conditions_required=1,
            blockers=() if side is not None else ("body_below_threshold",),
            indicators=(f"BODY {body * 10_000.0:+.1f}bps",),
            metrics={"body_bps": body * 10_000.0 if math.isfinite(body) else None},
        )
        evaluation = ProviderEvaluation(
            strategy_id=self.strategy_id,
            symbol=symbol,
            decision_time_ms=decision_ms,
            reference_price=close,
            decision_action="enter" if side is not None else "hold",
            eligible=side is not None,
            reason="synthetic_body" if side is not None else "body_below_threshold",
            side=side,
            readiness=readiness,
            target_anchor=self._target(close, side),
        )
        if side is None:
            return evaluation, None
        intent = StrategyIntent(
            strategy_id=self.strategy_id,
            symbol=symbol,
            side=side,
            decision_time_ms=decision_ms,
            reference_price=close,
            reason="synthetic_body",
            stop_anchor=self._stop(row, side),
            target_anchor=self._target(close, side),
        )
        return evaluation, intent

    def _stop(self, row: object, side: str) -> float | None:
        if not self._stop_anchor:
            return None
        return float(row.low if side == "long" else row.high)  # type: ignore[attr-defined]

    def _target(self, close: float, side: str | None) -> float | None:
        if not self._target_anchor or side is None:
            return None
        return close * (1.01 if side == "long" else 0.99)


def _factory(
    strategy_id: str, timeframe: str, *, stop_anchor: bool, target_anchor: bool
):
    def build(provider: object, config: object) -> SyntheticBodyCollector:
        del provider, config
        return SyntheticBodyCollector(
            strategy_id=strategy_id,
            timeframe=timeframe,
            stop_anchor=stop_anchor,
            target_anchor=target_anchor,
        )

    return build


def _registration(
    strategy_id: str,
    timeframe: str,
    lookback: int,
    *,
    stop_anchor: bool = False,
    target_anchor: bool = False,
) -> ProviderRegistration:
    return ProviderRegistration(
        strategy_id=strategy_id,
        signal_timeframe=timeframe,
        readiness_lookback_minutes=lookback,
        collector_factory=_factory(
            strategy_id, timeframe, stop_anchor=stop_anchor, target_anchor=target_anchor
        ),
        capability=ProviderCapability(
            stop_anchor=stop_anchor, target_anchor=target_anchor
        ),
    )


SYNTHETIC_REGISTRATIONS: Mapping[str, ProviderRegistration] = {
    strategy_id: _registration(
        strategy_id,
        timeframe,
        lookback,
        stop_anchor=stop_anchor,
        target_anchor=target_anchor,
    )
    for strategy_id, timeframe, lookback, stop_anchor, target_anchor in (
        SYNTHETIC_PROVIDERS
    )
}


def register_synthetic_providers() -> None:
    """Register every synthetic provider; repeated calls are harmless."""
    for registration in SYNTHETIC_REGISTRATIONS.values():
        register_provider(registration)

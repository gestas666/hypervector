"""Causal cohort publication for the frozen hourly price research mechanisms."""

from __future__ import annotations

import math

import pandas as pd

from hypervector.live.bidirectional_intents import StrategyIntent
from hypervector.live.hip3_provider_inputs import (
    completed_hip3_inputs,
    decision_time_ms,
)
from hypervector.live.multi_asset_signal_source import IntentBatch, ProviderEvaluation
from hypervector.live.provider_readiness import ReadinessMetric, SignalReadiness
from hypervector.research.donchian_atr_breakout_signals import (
    DonchianAtrBreakoutConfig,
    build_donchian_atr_breakout_signals,
)
from hypervector.research.hourly_band_reentry import (
    STRATEGY as BAND_REENTRY_STRATEGY,
    build_hourly_band_reentry_signals,
)

DONCHIAN20_STRATEGY = "hourly_donchian_20_10_atr20_bidirectional_v1"
DONCHIAN8_STRATEGY = "hourly_donchian_8_4_atr20_bidirectional_v1"
HOURLY_PRICE_STRATEGIES = frozenset(
    {DONCHIAN20_STRATEGY, DONCHIAN8_STRATEGY, BAND_REENTRY_STRATEGY}
)
HOURLY_PRICE_SYMBOLS = frozenset(
    {
        "BTC",
        "ETH",
        "SOL",
        "HYPE",
        "xyz:SPCX",
        "xyz:SP500",
        "xyz:SNDK",
        "xyz:BRENTOIL",
    }
)
_METRICS = (
    "atr",
    "prior_entry_high",
    "prior_exit_low",
    "band_mean",
    "band_lower",
    "band_upper",
)


def build_hourly_price_signals(bars: pd.DataFrame, strategy_id: str) -> pd.DataFrame:
    """Resolve an exact immutable mechanism shared by research and publication."""
    if strategy_id == BAND_REENTRY_STRATEGY:
        return build_hourly_band_reentry_signals(bars)
    channels = {DONCHIAN20_STRATEGY: (20, 10), DONCHIAN8_STRATEGY: (8, 4)}
    if strategy_id not in channels:
        raise ValueError(f"unsupported hourly price strategy: {strategy_id}")
    entry, exit_channel = channels[strategy_id]
    return build_donchian_atr_breakout_signals(
        bars,
        DonchianAtrBreakoutConfig(
            entry_channel_bars=entry,
            exit_channel_bars=exit_channel,
            signal_hours=1,
        ),
    )


class HourlyPriceCollector:
    """Publish completed hourly entries, stop anchors, exits and honest readiness."""

    def __init__(self, *, strategy_id: str) -> None:
        """Bind one of the predeclared hourly mechanisms without venue clients."""
        if strategy_id not in HOURLY_PRICE_STRATEGIES:
            raise ValueError(f"unsupported hourly price strategy: {strategy_id}")
        self._strategy_id = strategy_id

    def __call__(
        self,
        bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> IntentBatch:
        """Emit only unseen decisions whose source quarter-hour is completed."""
        if symbol not in HOURLY_PRICE_SYMBOLS:
            raise ValueError(f"unsupported hourly price symbol: {symbol}")
        frame, positions, boundary = completed_hip3_inputs(
            bars, observed_at, after_decision_time_ms
        )
        signals = build_hourly_price_signals(frame, self._strategy_id)
        metrics = [column for column in _METRICS if column in signals]
        segments = frame.gap_before_bars.gt(0).cumsum()
        signals.loc[:, metrics] = signals.loc[:, metrics].groupby(segments).ffill()
        evaluations = tuple(
            _evaluation(
                self._strategy_id,
                symbol,
                timestamp,
                frame.loc[timestamp],
                signals.loc[timestamp],
            )
            for timestamp in positions
        )
        return IntentBatch(
            tuple(_intent(row) for row in evaluations if row.eligible),
            boundary,
            evaluations,
        )


def _evaluation(
    strategy: str,
    symbol: str,
    timestamp: pd.Timestamp,
    bar: pd.Series,
    signal: pd.Series,
) -> ProviderEvaluation:
    side = "long" if signal.long_entry else "short" if signal.short_entry else None
    stop = _finite(signal.stop_price)
    ready = _finite(signal.atr) is not None
    eligible = side is not None and ready and stop is not None
    exits = frozenset(side for side in ("long", "short") if signal[f"{side}_exit"])
    reason = (
        "hourly_price_entry"
        if eligible
        else "hourly_price_exit"
        if exits
        else "entry_condition_absent"
    )
    readiness = _readiness(signal, side, ready, eligible)
    return ProviderEvaluation(
        strategy_id=strategy,
        symbol=symbol,
        decision_time_ms=decision_time_ms(timestamp),
        reference_price=float(bar.close),
        eligible=eligible,
        reason=reason,
        side=side,
        decision_action=f"enter_{side}"
        if eligible
        else "close_open_position"
        if exits
        else "hold",
        readiness=readiness,
        trigger="completed_hourly_price" if eligible else "none",
        exit_sides=exits,
        exit_reason="hourly_price_recipe_exit" if exits else None,
        confidence=None,
    )


def _readiness(
    signal: pd.Series,
    side: str | None,
    ready: bool,
    eligible: bool,
) -> SignalReadiness:
    stop = _finite(signal.stop_price)
    metrics: dict[str, ReadinessMetric] = {
        column: _finite(signal.get(column)) for column in _METRICS if column in signal
    }
    metrics.update({"stop_price": stop, "signal_hours": 1, "fresh_entry": eligible})
    blockers = (
        ()
        if eligible
        else ("awaiting_hourly_setup",)
        if ready
        else ("hourly_history_unready",)
    )
    return SignalReadiness(
        side=side,
        conditions_met=int(ready) + int(eligible),
        conditions_required=2,
        blockers=blockers,
        indicators=(
            f"HOURLY HISTORY {'READY' if ready else 'WAIT'}",
            f"FRESH ENTRY {side.upper() if eligible and side else 'NONE'}",
        ),
        metrics=metrics,
    )


def _intent(row: ProviderEvaluation) -> StrategyIntent:
    stop = row.readiness.metrics["stop_price"]
    if row.side not in {"long", "short"} or not isinstance(stop, float):
        raise ValueError(
            "eligible hourly price decision requires a side and finite stop"
        )
    return StrategyIntent(
        strategy_id=row.strategy_id,
        symbol=row.symbol,
        side=row.side,
        decision_time_ms=row.decision_time_ms,
        reference_price=row.reference_price,
        reason="completed_hourly_price",
        stop_anchor=stop,
    )


def _finite(value: object) -> float | None:
    if (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    ):
        return float(value)
    return None

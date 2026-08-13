"""Completed-bar HIP-3 Swing/HA and breakout-pressure live providers."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

import pandas as pd

from hypervector.hip3_pressure_contract import (
    ARCHIVE_PARITY_MAXIMUM_PRESSURE_AGE_MS,
    LEGACY_MAXIMUM_PRESSURE_AGE_MS,
)
from hypervector.live.bidirectional_intents import StrategyIntent
from hypervector.live.hip3_ledger_pressure import (
    Hip3LedgerPressureSource as Hip3LedgerPressureSource,
    Hip3PressureObservation,
    Hip3PressureSourceProtocol,
)
from hypervector.live.hip3_provider_inputs import (
    completed_hip3_inputs,
    decision_time_ms,
)
from hypervector.live.hip3_provider_evaluations import (
    Hip3PressureStatus,
    breakout_evaluation,
    swing_evaluation,
)
from hypervector.live.multi_asset_signal_source import IntentBatch, ProviderEvaluation
from hypervector.research.hip3_breakout_pressure_signals import (
    Hip3BreakoutPressureConfig,
    build_breakout_pressure_signals,
)
from hypervector.research.hip3_swing_signals import build_gap_aware_swing_ha_signals
from hypervector.research.swing_ha_signals import SwingHaSignalConfig

HIP3_SWING_INDEX_STRATEGY = "hip3_swing_ha_sp500_spcx_bidirectional_v2"
HIP3_BREAKOUT_INDEX_STRATEGY = "hip3_breakout_pressure_sp500_spcx_bidirectional_v1"
HIP3_BREAKOUT_INDEX_FRESH15_STRATEGY = (
    "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v2"
)
HIP3_SWING_COMMODITY_STRATEGY = "hip3_swing_ha_sndk_gold_brent_bidirectional_v1"
HIP3_BREAKOUT_COMMODITY_STRATEGY = (
    "hip3_breakout_pressure_sndk_gold_brent_bidirectional_v1"
)
HIP3_BREAKOUT_COMMODITY_FRESH15_STRATEGY = (
    "hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2"
)
HIP3_STRATEGIES = frozenset(
    {
        HIP3_SWING_INDEX_STRATEGY,
        HIP3_BREAKOUT_INDEX_STRATEGY,
        HIP3_BREAKOUT_INDEX_FRESH15_STRATEGY,
        HIP3_SWING_COMMODITY_STRATEGY,
        HIP3_BREAKOUT_COMMODITY_STRATEGY,
        HIP3_BREAKOUT_COMMODITY_FRESH15_STRATEGY,
    }
)


class SwingSignalBuilderProtocol(Protocol):
    """Injectable Swing/HA signal builder for deterministic tests."""

    def __call__(
        self,
        bars: pd.DataFrame,
        config: SwingHaSignalConfig,
    ) -> pd.DataFrame: ...


class BreakoutSignalBuilderProtocol(Protocol):
    """Injectable breakout-pressure signal builder for deterministic tests."""

    def __call__(
        self,
        bars: pd.DataFrame,
        config: Hip3BreakoutPressureConfig,
    ) -> pd.DataFrame: ...


class Hip3SwingHaCollector:
    """Convert the frozen 15m Swing/HA recipe into live attributed intents."""

    def __init__(
        self,
        *,
        strategy_id: str,
        config: SwingHaSignalConfig,
        signal_builder: SwingSignalBuilderProtocol = build_gap_aware_swing_ha_signals,
    ) -> None:
        if strategy_id not in {
            HIP3_SWING_INDEX_STRATEGY,
            HIP3_SWING_COMMODITY_STRATEGY,
        }:
            raise ValueError("unsupported HIP-3 Swing/HA strategy identity")
        self._strategy_id = strategy_id
        self._config = config
        self._signal_builder = signal_builder

    @property
    def config(self) -> SwingHaSignalConfig:
        """Return the immutable journal-selected signal recipe."""
        return self._config

    def __call__(
        self,
        bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> IntentBatch:
        """Evaluate every newly completed 15m decision without look-ahead."""
        frame, positions, boundary = completed_hip3_inputs(
            bars,
            observed_at,
            after_decision_time_ms,
        )
        signals = self._signal_builder(frame, self._config)
        evaluations = tuple(
            swing_evaluation(
                strategy_id=self._strategy_id,
                symbol=symbol,
                timestamp=timestamp,
                bar=frame.loc[timestamp],
                signal=signals.loc[timestamp],
                config=self._config,
            )
            for timestamp in positions
        )
        return IntentBatch(
            tuple(_intent(value) for value in evaluations if value.eligible),
            boundary,
            evaluations,
        )


class Hip3BreakoutPressureCollector:
    """Require 15m breakout structure plus fresh depth-ten venue pressure."""

    def __init__(
        self,
        *,
        strategy_id: str,
        config: Hip3BreakoutPressureConfig,
        pressure_source: Hip3PressureSourceProtocol,
        signal_builder: BreakoutSignalBuilderProtocol = build_breakout_pressure_signals,
    ) -> None:
        if strategy_id not in {
            HIP3_BREAKOUT_INDEX_STRATEGY,
            HIP3_BREAKOUT_INDEX_FRESH15_STRATEGY,
            HIP3_BREAKOUT_COMMODITY_STRATEGY,
            HIP3_BREAKOUT_COMMODITY_FRESH15_STRATEGY,
        }:
            raise ValueError("unsupported HIP-3 breakout strategy identity")
        self._strategy_id = strategy_id
        self._config = config
        self._pressure_source = pressure_source
        self._signal_builder = signal_builder
        self._maximum_pressure_age_ms = _maximum_pressure_age_ms(strategy_id)

    @property
    def config(self) -> Hip3BreakoutPressureConfig:
        """Return the immutable journal-selected breakout recipe."""
        return self._config

    @property
    def pressure_source(self) -> Hip3PressureSourceProtocol:
        """Return the causal L2 evidence source."""
        return self._pressure_source

    def __call__(
        self,
        bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> IntentBatch:
        """Evaluate new breakouts and reject absent, stale, or opposed pressure."""
        frame, positions, boundary = completed_hip3_inputs(
            bars,
            observed_at,
            after_decision_time_ms,
        )
        observed_ms = _timestamp_ms(observed_at)
        decision_ms = decision_time_ms(frame.index[-1])
        pressure, pressure_status = _causal_pressure(
            self._pressure_source.latest_at_or_before(symbol, decision_ms),
            decision_time_ms=decision_ms,
            observed_ms=observed_ms,
            maximum_age_ms=self._maximum_pressure_age_ms,
        )
        signal_input = frame.copy()
        signal_input["decision_imbalance_10"] = 0.0
        if pressure is not None:
            signal_input.loc[signal_input.index[-1], "decision_imbalance_10"] = (
                pressure.imbalance_10
            )
        signals = self._signal_builder(signal_input, self._config)
        evaluations = self._evaluations(
            frame=frame,
            positions=positions,
            signals=signals,
            symbol=symbol,
            pressure=pressure,
            pressure_status=pressure_status,
            decision_ms=decision_ms,
        )
        return IntentBatch(
            tuple(_intent(value) for value in evaluations if value.eligible),
            boundary,
            evaluations,
        )

    def _evaluations(
        self,
        *,
        frame: pd.DataFrame,
        positions: tuple[pd.Timestamp, ...],
        signals: pd.DataFrame,
        symbol: str,
        pressure: Hip3PressureObservation | None,
        pressure_status: Hip3PressureStatus,
        decision_ms: int,
    ) -> tuple[ProviderEvaluation, ...]:
        """Build attributed evaluations for each unseen completed decision."""
        return tuple(
            breakout_evaluation(
                strategy_id=self._strategy_id,
                symbol=symbol,
                timestamp=timestamp,
                bar=frame.loc[timestamp],
                signal=signals.loc[timestamp],
                config=self._config,
                pressure=(pressure if timestamp == frame.index[-1] else None),
                pressure_status=(
                    pressure_status
                    if timestamp == frame.index[-1]
                    else "not_evaluated_for_prior_decision"
                ),
                pressure_cutoff_ms=decision_ms,
                maximum_pressure_age_ms=self._maximum_pressure_age_ms,
            )
            for timestamp in positions
        )


def configured_hip3_collector(
    strategy_id: str,
    *,
    asset_ledgers: Mapping[str, Path],
    cohort_ledger: Path,
) -> Hip3SwingHaCollector | Hip3BreakoutPressureCollector:
    """Resolve one exact strategy identity to its frozen research recipe."""
    from hypervector.live.hip3_provider_recipes import configured_hip3_collector

    return configured_hip3_collector(
        strategy_id,
        asset_ledgers=asset_ledgers,
        cohort_ledger=cohort_ledger,
    )


def _intent(evaluation: ProviderEvaluation) -> StrategyIntent:
    if evaluation.side not in {"long", "short"}:
        raise ValueError("eligible HIP-3 evaluation requires a side")
    return StrategyIntent(
        strategy_id=evaluation.strategy_id,
        symbol=evaluation.symbol,
        side=evaluation.side,
        decision_time_ms=evaluation.decision_time_ms,
        reference_price=evaluation.reference_price,
        reason=f"{evaluation.trigger}:{evaluation.side}",
    )


def _causal_pressure(
    value: Hip3PressureObservation | None,
    *,
    decision_time_ms: int,
    observed_ms: int,
    maximum_age_ms: int,
) -> tuple[Hip3PressureObservation | None, Hip3PressureStatus]:
    if value is None:
        return None, "no_candidate"
    if observed_ms < decision_time_ms:
        return None, "decision_not_observed"
    if value.recv_ts_ms > decision_time_ms:
        return None, "post_decision_candidate"
    if decision_time_ms - value.recv_ts_ms > maximum_age_ms:
        return None, "stale_candidate"
    return value, "available"


def _maximum_pressure_age_ms(strategy_id: str) -> int:
    """Return the frozen freshness contract for one versioned provider."""
    if strategy_id in {
        HIP3_BREAKOUT_INDEX_FRESH15_STRATEGY,
        HIP3_BREAKOUT_COMMODITY_FRESH15_STRATEGY,
    }:
        return ARCHIVE_PARITY_MAXIMUM_PRESSURE_AGE_MS
    return LEGACY_MAXIMUM_PRESSURE_AGE_MS


def _timestamp_ms(timestamp: pd.Timestamp) -> int:
    value = pd.Timestamp(timestamp)
    if value.tzinfo is None:
        raise ValueError("HIP-3 timestamp must be timezone-aware")
    return int(value.timestamp() * 1_000)

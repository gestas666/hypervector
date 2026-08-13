"""Causal candle polling for all configured cohort intent providers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Protocol

import pandas as pd
import requests

from hypervector.live.bidirectional_intents import StrategyIntent, WithheldIntent
from hypervector.live.canonical_regime_telemetry import (
    LEGACY_CANONICAL_REGIME_STRATEGY,
    CanonicalRegimeCollectorProtocol,
    CanonicalRegimeTelemetryCollector,
    canonical_regime_symbols,
)
from hypervector.live.cohort_regime_routing import attach_regime_preferences
from hypervector.live.cohort_profit_lock_history import profit_lock_market_bars
from hypervector.live.multi_asset_default_collectors import build_default_collector
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    StrategyProviderConfig,
)
from hypervector.live.multi_asset_market_bars import (
    CohortMarketBar,
    MultiAssetIntentPollerError,
    TransientCohortMarketDataError,
    aware_utc,
    completed_market_bars,
    latest_completed_price,
    merge_one_minute_bars,
    resample_one_minute_bars,
    resample_one_minute_to_five,
)
from hypervector.live.multi_asset_polling_contract import (
    READINESS_SEED_LOOKBACK_MINUTES,
    SOURCE_TIMEFRAMES,
)
from hypervector.live.multi_asset_signal_source import IntentBatch, ProviderEvaluation
from hypervector.live.transient_transport import transient_read_failure_reason

_INCREMENTAL_LOOKBACK_MINUTES = 5
_MINUTES_PER_DAY = 24 * 60
_PREACTIVATION_READINESS_REASON = "pre_activation_readiness_seed"


class CohortBarFetcherProtocol(Protocol):
    """Public completed-candle transport used by the cohort."""

    def __call__(
        self,
        symbol: str,
        timeframe: str,
        lookback_days: float,
        *,
        end_ms: int | None = None,
    ) -> pd.DataFrame: ...


class ProviderIntentCollectorProtocol(Protocol):
    """Uniform adapter around one provider's completed-bar builder."""

    def __call__(
        self,
        bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> IntentBatch: ...


_default_collector = build_default_collector


@dataclass(frozen=True)
class CohortIntentPoll:
    """Fresh intents and completed-bar reference prices for one cycle."""

    intents: tuple[StrategyIntent, ...]
    reference_prices: Mapping[str, float]
    source_withheld: tuple[WithheldIntent, ...] = field(default_factory=tuple)
    market_bars: Mapping[str, tuple[CohortMarketBar, ...]] = field(default_factory=dict)
    exit_bars: Mapping[str, tuple[CohortMarketBar, ...]] = field(default_factory=dict)
    evaluations: tuple[ProviderEvaluation, ...] = field(default_factory=tuple)
    regime_evaluations: tuple[ProviderEvaluation, ...] = field(default_factory=tuple)

    @property
    def all_intents(self) -> tuple[StrategyIntent, ...]:
        """Return fresh and source-withheld intents for complete journaling."""
        return self.intents + tuple(item.intent for item in self.source_withheld)

    @property
    def all_evaluations(self) -> tuple[ProviderEvaluation, ...]:
        """Return provider setups plus non-executable canonical regime evidence."""
        return self.evaluations + self.regime_evaluations


class ConfiguredMultiAssetIntentPoller:
    """Fetch each required source clock once and advance every provider."""

    def __init__(
        self,
        *,
        config: MultiAssetLiveConfig,
        fetch_bars: CohortBarFetcherProtocol,
        collectors: Mapping[str, ProviderIntentCollectorProtocol],
        canonical_regime_collector: CanonicalRegimeCollectorProtocol | None = None,
    ) -> None:
        expected = {provider.strategy_id for provider in config.providers}
        if set(collectors) != expected:
            raise MultiAssetIntentPollerError(
                "intent collectors must exactly match configured providers"
            )
        unknown = expected.difference(SOURCE_TIMEFRAMES)
        if unknown:
            raise MultiAssetIntentPollerError(
                f"provider source timeframe is not defined: {sorted(unknown)}"
            )
        self._config = config
        self._fetch_bars = fetch_bars
        self._collectors = dict(collectors)
        self._canonical_regime_collector = canonical_regime_collector or (
            CanonicalRegimeTelemetryCollector(
                symbols=canonical_regime_symbols(config.symbols),
                legacy_execution_enabled=False,
                legacy_execution_symbols=frozenset(
                    symbol
                    for provider in config.providers
                    if provider.strategy_id == LEGACY_CANONICAL_REGIME_STRATEGY
                    for symbol in provider.symbols
                ),
            )
        )
        self._boundaries: dict[tuple[str, str], int] | None = None
        self._one_minute_cache: dict[str, pd.DataFrame] = {}
        self._readiness_seed_pending = False

    @classmethod
    def with_default_collectors(
        cls,
        *,
        config: MultiAssetLiveConfig,
        fetch_bars: CohortBarFetcherProtocol,
        backtest_lab_root: Path,
    ) -> ConfiguredMultiAssetIntentPoller:
        """Construct every configured provider with verified dependencies."""
        collectors = {
            provider.strategy_id: build_default_collector(
                provider,
                config,
                backtest_lab_root,
            )
            for provider in config.providers
        }
        return cls(
            config=config,
            fetch_bars=fetch_bars,
            collectors=collectors,
        )

    def activate(self, activation_time_ms: int) -> None:
        """Set a no-retro-entry boundary for every provider and symbol."""
        if self._boundaries is not None:
            raise MultiAssetIntentPollerError("intent poller is already active")
        if (
            isinstance(activation_time_ms, bool)
            or not isinstance(activation_time_ms, int)
            or activation_time_ms < 0
        ):
            raise MultiAssetIntentPollerError(
                "activation_time_ms must be a nonnegative integer"
            )
        self._boundaries = {
            (provider.strategy_id, symbol): activation_time_ms
            for provider in self._config.providers
            for symbol in provider.symbols
        }
        self._canonical_regime_collector.activate(activation_time_ms)
        self._readiness_seed_pending = True

    def poll(self, observed_at: datetime) -> CohortIntentPoll:
        """Return fresh attributed intents and latest completed prices."""
        if self._boundaries is None:
            raise MultiAssetIntentPollerError("intent poller is not active")
        observed = aware_utc(observed_at)
        observed_ms = int(observed.timestamp() * 1_000)
        try:
            bars = self._fetch_cycle(observed_ms)
        except requests.RequestException as exc:
            reason = transient_read_failure_reason(exc)
            if reason is None:
                raise
            raise TransientCohortMarketDataError(
                source="hyperliquid_public_candles",
                reason=reason,
            ) from exc
        intents, source_withheld, evaluations = self._collect_cycle(
            bars,
            observed,
            observed_ms,
        )
        regime_evaluations = self._canonical_regime_collector.collect(bars, observed)
        result = self._build_poll(
            bars,
            observed,
            intents,
            source_withheld,
            evaluations,
            regime_evaluations,
        )
        self._readiness_seed_pending = False
        return result

    def _collect_cycle(
        self,
        bars: Mapping[tuple[str, str], pd.DataFrame],
        observed: pd.Timestamp,
        observed_ms: int,
    ) -> tuple[
        list[StrategyIntent],
        list[WithheldIntent],
        list[ProviderEvaluation],
    ]:
        intents: list[StrategyIntent] = []
        source_withheld: list[WithheldIntent] = []
        evaluations: list[ProviderEvaluation] = []
        for provider in self._config.providers:
            self._collect_provider(
                provider,
                bars,
                observed,
                observed_ms,
                intents,
                source_withheld,
                evaluations,
            )
        return intents, source_withheld, evaluations

    def _collect_provider(
        self,
        provider: StrategyProviderConfig,
        bars: Mapping[tuple[str, str], pd.DataFrame],
        observed: pd.Timestamp,
        observed_ms: int,
        intents: list[StrategyIntent],
        source_withheld: list[WithheldIntent],
        evaluations: list[ProviderEvaluation],
    ) -> None:
        timeframe = SOURCE_TIMEFRAMES[provider.strategy_id]
        collector = self._collectors[provider.strategy_id]
        for symbol in provider.symbols:
            key = (provider.strategy_id, symbol)
            prior = self._require_boundary(key)
            batch = collector(
                bars[(symbol, timeframe)],
                symbol=symbol,
                observed_at=observed,
                after_decision_time_ms=prior,
            )
            _validate_batch(batch, provider.strategy_id, symbol, prior, observed_ms)
            self._boundaries[key] = batch.latest_decision_time_ms
            self._record_evaluations(
                batch,
                collector,
                bars[(symbol, timeframe)],
                provider,
                symbol,
                observed,
                prior,
                evaluations,
            )
            _record_intents(
                batch,
                observed_ms,
                provider.maximum_entry_delay_seconds,
                intents,
                source_withheld,
            )

    def _record_evaluations(
        self,
        batch: IntentBatch,
        collector: ProviderIntentCollectorProtocol,
        bars: pd.DataFrame,
        provider: StrategyProviderConfig,
        symbol: str,
        observed: pd.Timestamp,
        prior: int,
        evaluations: list[ProviderEvaluation],
    ) -> None:
        if batch.evaluations:
            evaluations.extend(batch.evaluations)
            return
        if not self._readiness_seed_pending:
            return
        seed = self._seed_readiness_evaluation(
            collector,
            bars,
            provider.strategy_id,
            symbol,
            observed,
            prior,
        )
        if seed is not None:
            evaluations.append(seed)

    def _require_boundary(self, key: tuple[str, str]) -> int:
        boundaries = self._boundaries
        if boundaries is None:
            raise MultiAssetIntentPollerError("intent poller is not active")
        return boundaries[key]

    def _build_poll(
        self,
        bars: Mapping[tuple[str, str], pd.DataFrame],
        observed: pd.Timestamp,
        intents: list[StrategyIntent],
        source_withheld: list[WithheldIntent],
        evaluations: list[ProviderEvaluation],
        regime_evaluations: tuple[ProviderEvaluation, ...],
    ) -> CohortIntentPoll:
        evaluation_rows = tuple(evaluations)
        all_evaluations = evaluation_rows + regime_evaluations
        weighted_intents = attach_regime_preferences(tuple(intents), all_evaluations)
        ordered = tuple(sorted(weighted_intents, key=self._intent_order))
        prices = {
            symbol: latest_completed_price(bars[(symbol, "1m")], observed, "1m")
            for symbol in self._config.symbols
        }
        market_bars = {
            symbol: completed_market_bars(bars[(symbol, "1m")], observed, symbol)
            for symbol in self._config.symbols
        }
        exit_bars = profit_lock_market_bars(self._config.providers, bars, observed)
        weighted_stale = attach_regime_preferences(
            tuple(item.intent for item in source_withheld),
            all_evaluations,
        )
        withheld = tuple(
            sorted(
                (
                    WithheldIntent(intent, prior.reason)
                    for intent, prior in zip(
                        weighted_stale,
                        source_withheld,
                        strict=True,
                    )
                ),
                key=lambda item: self._intent_order(item.intent),
            )
        )
        return CohortIntentPoll(
            intents=ordered,
            reference_prices=prices,
            source_withheld=withheld,
            market_bars=market_bars,
            exit_bars=exit_bars,
            evaluations=evaluation_rows,
            regime_evaluations=regime_evaluations,
        )

    def _seed_readiness_evaluation(
        self,
        collector: ProviderIntentCollectorProtocol,
        bars: pd.DataFrame,
        strategy_id: str,
        symbol: str,
        observed: pd.Timestamp,
        activation_boundary: int,
    ) -> ProviderEvaluation | None:
        lookback_ms = READINESS_SEED_LOOKBACK_MINUTES[strategy_id] * 60 * 1_000
        seed_boundary = max(0, activation_boundary - lookback_ms)
        batch = collector(
            bars,
            symbol=symbol,
            observed_at=observed,
            after_decision_time_ms=seed_boundary,
        )
        _validate_batch(
            batch,
            strategy_id,
            symbol,
            seed_boundary,
            activation_boundary,
        )
        seed = max(
            batch.evaluations, key=lambda value: value.decision_time_ms, default=None
        )
        return (
            None
            if seed is None
            else replace(
                seed,
                backend_non_action_reason=_PREACTIVATION_READINESS_REASON,
            )
        )

    def _fetch_cycle(self, observed_ms: int) -> dict[tuple[str, str], pd.DataFrame]:
        lookback_days = (
            self._config.lookback_days
            if not self._one_minute_cache
            else _INCREMENTAL_LOOKBACK_MINUTES / _MINUTES_PER_DAY
        )
        fresh = {
            symbol: self._fetch_bars(
                symbol,
                "1m",
                lookback_days,
                end_ms=observed_ms,
            )
            for symbol in self._config.symbols
        }
        retained = {
            symbol: merge_one_minute_bars(
                self._one_minute_cache.get(symbol),
                frame,
                observed_ms,
                self._config.lookback_days,
            )
            for symbol, frame in fresh.items()
        }
        self._one_minute_cache = retained
        result = {(symbol, "1m"): frame for symbol, frame in retained.items()}
        result.update(
            {
                (symbol, "5m"): resample_one_minute_to_five(frame)
                for symbol, frame in retained.items()
            }
        )
        result.update(
            {
                (symbol, "15m"): resample_one_minute_bars(frame, minutes=15)
                for symbol, frame in retained.items()
            }
        )
        return result

    def _intent_order(self, intent: StrategyIntent) -> tuple[int, int, int]:
        symbol_index = self._config.symbols.index(intent.symbol)
        priority = next(
            provider.priority
            for provider in self._config.providers
            if provider.strategy_id == intent.strategy_id
        )
        return intent.decision_time_ms, symbol_index, -priority


def _validate_batch(
    batch: IntentBatch,
    strategy_id: str,
    symbol: str,
    prior: int,
    observed_ms: int,
) -> None:
    boundary = batch.latest_decision_time_ms
    if boundary < prior or boundary > observed_ms:
        raise MultiAssetIntentPollerError(
            f"invalid decision boundary for {strategy_id}/{symbol}: {boundary}"
        )
    for intent in batch.intents:
        if intent.strategy_id != strategy_id or intent.symbol != symbol:
            raise MultiAssetIntentPollerError(
                "provider emitted an intent with incorrect attribution"
            )
        if not prior < intent.decision_time_ms <= boundary:
            raise MultiAssetIntentPollerError(
                "provider intent lies outside its causal decision boundary"
            )
    for evaluation in batch.evaluations:
        if evaluation.strategy_id != strategy_id or evaluation.symbol != symbol:
            raise MultiAssetIntentPollerError(
                "provider emitted an evaluation with incorrect attribution"
            )
        if not prior < evaluation.decision_time_ms <= boundary:
            raise MultiAssetIntentPollerError(
                "provider evaluation lies outside its causal decision boundary"
            )


def _record_intents(
    batch: IntentBatch,
    observed_ms: int,
    maximum_entry_delay_seconds: int,
    intents: list[StrategyIntent],
    source_withheld: list[WithheldIntent],
) -> None:
    for intent in batch.intents:
        age = observed_ms - intent.decision_time_ms
        if age > maximum_entry_delay_seconds * 1_000:
            source_withheld.append(WithheldIntent(intent, "stale_completed_decision"))
        else:
            intents.append(intent)

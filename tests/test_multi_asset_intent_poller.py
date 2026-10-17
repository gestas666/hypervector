"""Causal polling tests for the shared multi-asset intent cohort."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest
import requests

from hypervector.live.bidirectional_intents import StrategyIntent
from hypervector.live.canonical_regime_telemetry import (
    CANONICAL_REGIME_TELEMETRY_STRATEGY,
)
from hypervector.live.multi_asset_intent_poller import (
    ConfiguredMultiAssetIntentPoller,
)
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.multi_asset_market_bars import TransientCohortMarketDataError
from hypervector.live.multi_asset_polling_contract import (
    READINESS_SEED_LOOKBACK_MINUTES,
)
from hypervector.live.multi_asset_signal_source import IntentBatch, ProviderEvaluation
from hypervector.live.provider_readiness import SignalReadiness

_OBSERVED = datetime(2026, 8, 1, 12, tzinfo=UTC)
_OBSERVED_MS = int(_OBSERVED.timestamp() * 1_000)


class _Collector:
    def __init__(self, strategy_id: str, *, emit: bool) -> None:
        self.strategy_id = strategy_id
        self.emit = emit
        self.boundaries: list[int | None] = []
        self.bar_counts: list[int] = []
        self.bar_times: list[tuple[pd.Timestamp, ...]] = []

    def __call__(
        self,
        bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> IntentBatch:
        del observed_at
        self.boundaries.append(after_decision_time_ms)
        self.bar_counts.append(len(bars))
        self.bar_times.append(tuple(pd.DatetimeIndex(bars["timestamp"])))
        boundary = (after_decision_time_ms or 0) + 1
        intents = ()
        if self.emit:
            intents = (
                StrategyIntent(
                    self.strategy_id,
                    symbol,
                    "long" if symbol in {"BTC", "SOL"} else "short",
                    boundary,
                    100.0,
                    "fixture",
                ),
            )
        side = "long" if symbol in {"BTC", "SOL"} else "short"
        evaluation = ProviderEvaluation(
            strategy_id=self.strategy_id,
            symbol=symbol,
            decision_time_ms=boundary,
            reference_price=100.0,
            decision_action="hold",
            eligible=False,
            reason="fixture_hold",
            side=side,
            readiness=SignalReadiness(
                side=side,
                conditions_met=1,
                conditions_required=2,
                blockers=("fixture_blocker",),
                indicators=("FIXTURE 1/2",),
                metrics={"structural_direction": "short"},
            ),
            primary_regime=(
                "TREND_DOWN"
                if self.strategy_id == "range_onset_bidirectional_v1"
                else None
            ),
            state_1m=(
                "TREND_DOWN"
                if self.strategy_id == "range_onset_bidirectional_v1"
                else None
            ),
            state_5m=(
                "TREND_DOWN"
                if self.strategy_id == "range_onset_bidirectional_v1"
                else None
            ),
            context_15m=(
                "TREND_DOWN"
                if self.strategy_id == "range_onset_bidirectional_v1"
                else None
            ),
        )
        return IntentBatch(intents, boundary, (evaluation,))


class _StartupReadinessCollector:
    def __init__(self, strategy_id: str) -> None:
        self.strategy_id = strategy_id
        self.boundaries: list[int | None] = []

    def __call__(
        self,
        bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> IntentBatch:
        del bars, observed_at
        self.boundaries.append(after_decision_time_ms)
        assert after_decision_time_ms is not None
        if after_decision_time_ms == _OBSERVED_MS:
            return IntentBatch((), _OBSERVED_MS)
        decision_time_ms = _OBSERVED_MS - 1
        side = "long" if symbol in {"BTC", "SOL"} else "short"
        readiness = SignalReadiness(
            side=side,
            conditions_met=1,
            conditions_required=2,
            blockers=("startup_fixture",),
            indicators=("STARTUP 1/2",),
        )
        evaluation = ProviderEvaluation(
            strategy_id=self.strategy_id,
            symbol=symbol,
            decision_time_ms=decision_time_ms,
            reference_price=100.0,
            decision_action=f"enter_{side}",
            eligible=True,
            reason="startup_eligible_fixture",
            side=side,
            readiness=readiness,
        )
        retro_intent = StrategyIntent(
            self.strategy_id,
            symbol,
            side,
            decision_time_ms,
            100.0,
            "must_not_route",
        )
        return IntentBatch((retro_intent,), decision_time_ms, (evaluation,))


class _FreshStartupWithMissedExitCollector:
    def __init__(
        self,
        strategy_id: str,
        activation_ms: int,
        *,
        fresh_exit: bool = False,
        seed_exit: bool = True,
    ) -> None:
        self.strategy_id = strategy_id
        self.activation_ms = activation_ms
        self.fresh_exit = fresh_exit
        self.seed_exit = seed_exit

    def __call__(
        self,
        bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> IntentBatch:
        del bars, observed_at
        assert after_decision_time_ms is not None
        side = "long" if symbol in {"BTC", "SOL"} else "short"
        if after_decision_time_ms == self.activation_ms:
            decision_ms = self.activation_ms + 1
            evaluation = _poller_evaluation(
                self.strategy_id,
                symbol,
                side,
                decision_ms,
                exit_side=side if self.fresh_exit else None,
            )
            if self.fresh_exit:
                return IntentBatch((), decision_ms, (evaluation,))
            intent = StrategyIntent(
                self.strategy_id,
                symbol,
                side,
                decision_ms,
                100.0,
                "fresh_post_activation",
            )
            return IntentBatch((intent,), decision_ms, (evaluation,))
        decision_ms = self.activation_ms - 1
        evaluation = _poller_evaluation(
            self.strategy_id,
            symbol,
            side,
            decision_ms,
            exit_side=side if self.seed_exit else None,
        )
        return IntentBatch((), decision_ms, (evaluation,))


def _poller_evaluation(
    strategy_id: str,
    symbol: str,
    side: str,
    decision_ms: int,
    *,
    exit_side: str | None,
) -> ProviderEvaluation:
    exit_sides = frozenset({exit_side}) if exit_side is not None else frozenset()
    return ProviderEvaluation(
        strategy_id=strategy_id,
        symbol=symbol,
        decision_time_ms=decision_ms,
        reference_price=100.0,
        decision_action=f"close_{exit_side}" if exit_side else f"enter_{side}",
        eligible=exit_side is None,
        reason="missed_recipe_exit" if exit_side else "fresh_post_activation",
        side=side,
        readiness=SignalReadiness(side, 1, 1, (), ("FIXTURE READY",)),
        exit_sides=exit_sides,
        exit_reason="missed_recipe_exit" if exit_side else None,
    )


class _CanonicalCollector:
    def __init__(self) -> None:
        self.activations: list[int] = []
        self.collections = 0

    def activate(self, activation_time_ms: int) -> None:
        self.activations.append(activation_time_ms)

    def collect(
        self,
        bars: object,
        observed_at: pd.Timestamp,
    ) -> tuple[ProviderEvaluation, ...]:
        del bars, observed_at
        self.collections += 1
        return (
            ProviderEvaluation(
                strategy_id=CANONICAL_REGIME_TELEMETRY_STRATEGY,
                symbol="BTC",
                decision_time_ms=_OBSERVED_MS - 999,
                reference_price=100.0,
                decision_action="regime_observation",
                eligible=False,
                reason="canonical_regime_observation",
                side=None,
                readiness=SignalReadiness(
                    side=None,
                    conditions_met=1,
                    conditions_required=1,
                    blockers=(),
                    indicators=("5m TREND_DOWN",),
                    metrics={},
                ),
                primary_regime="TREND_DOWN",
                state_1m="TREND_DOWN",
                state_5m="TREND_DOWN",
                context_15m="RANGE",
                confidence=0.8,
                backend_non_action_reason="telemetry_only_no_execution_authority",
            ),
        )


def _assert_startup_boundaries(collector: _Collector, *, symbols: int) -> None:
    activation_ms = _OBSERVED_MS - 1_000
    lookback_ms = READINESS_SEED_LOOKBACK_MINUTES[collector.strategy_id] * 60 * 1_000
    initial = [
        boundary
        for _ in range(symbols)
        for boundary in (activation_ms, max(0, activation_ms - lookback_ms))
    ]
    assert collector.boundaries[: symbols * 2] == initial
    assert collector.boundaries[symbols * 2 :] == [activation_ms + 1] * symbols


def _bars(symbol: str, timeframe: str) -> pd.DataFrame:
    del symbol
    minutes = 5 if timeframe == "5m" else 1
    return pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                ["2026-08-01T11:50:00Z", "2026-08-01T11:55:00Z"]
                if minutes == 5
                else ["2026-08-01T11:58:00Z", "2026-08-01T11:59:00Z"],
                utc=True,
            ),
            "open": [99.0, 100.0],
            "high": [101.0, 102.0],
            "low": [98.0, 99.0],
            "close": [100.0, 101.0],
            "volume": [10.0, 11.0],
        }
    )


def _one_minute_bars(symbol: str) -> pd.DataFrame:
    del symbol
    closes = [float(value) for value in range(100, 110)]
    return pd.DataFrame(
        {
            "timestamp": pd.date_range(
                "2026-08-01T11:50:00Z",
                periods=10,
                freq="1min",
            ),
            "open": [value - 0.5 for value in closes],
            "high": [value + 1.0 for value in closes],
            "low": [value - 1.0 for value in closes],
            "close": closes,
            "volume": [1.0] * 10,
        }
    )


def test_poller_uses_one_minute_feed_and_incremental_refresh() -> None:
    """Live polling derives 5m locally and never repeats a full warmup cycle."""
    config = load_multi_asset_live_config(
        "tests/fixtures/profiles/multi_asset_bidirectional_canary.toml",
        mode="observe",
    )
    calls: list[tuple[str, str, float, int | None]] = []

    def fetch(
        symbol: str,
        timeframe: str,
        lookback_days: float,
        *,
        end_ms: int | None = None,
    ) -> pd.DataFrame:
        calls.append((symbol, timeframe, lookback_days, end_ms))
        return _one_minute_bars(symbol)

    collectors = {
        provider.strategy_id: _Collector(provider.strategy_id, emit=False)
        for provider in config.providers
    }
    poller = ConfiguredMultiAssetIntentPoller(
        config=config,
        fetch_bars=fetch,
        collectors=collectors,
    )
    poller.activate(_OBSERVED_MS - 1_000)

    first = poller.poll(_OBSERVED)
    poller.poll(datetime(2026, 8, 1, 12, 0, 15, tzinfo=UTC))

    assert len(calls) == 8
    assert {timeframe for _, timeframe, _, _ in calls} == {"1m"}
    assert {days for _, _, days, _ in calls[:4]} == {config.lookback_days}
    assert all(0.0 < days < 1.0 for _, _, days, _ in calls[4:])
    hulk = collectors["hulk_expansion_bidirectional_tuned_v2"]
    range_onset = collectors["range_onset_bidirectional_v1"]
    source_follow = collectors["hypervelocity_source_follow_bidirectional_5m_v1"]
    hype_breakout = collectors["hype_breakout_onset_bidirectional_v1"]
    assert hulk.bar_counts == [2] * 12
    assert range_onset.bar_counts == [10] * 12
    assert source_follow.bar_counts == [10] * 3
    assert hype_breakout.bar_counts == [10] * 3
    assert hulk.bar_times[0] == (
        pd.Timestamp("2026-08-01T11:50:00Z"),
        pd.Timestamp("2026-08-01T11:55:00Z"),
    )
    assert first.reference_prices["BTC"] == 109.0
    assert len(first.evaluations) == 10
    assert {
        (evaluation.strategy_id, evaluation.symbol) for evaluation in first.evaluations
    } == {
        (provider.strategy_id, symbol)
        for provider in config.providers
        for symbol in provider.symbols
    }


def test_startup_seeds_readiness_without_routing_retroactive_intents() -> None:
    """Latest completed setups are visible immediately but never executable."""
    config = load_multi_asset_live_config(
        "tests/fixtures/profiles/multi_asset_bidirectional_canary.toml",
        mode="observe",
    )
    collectors = {
        provider.strategy_id: _StartupReadinessCollector(provider.strategy_id)
        for provider in config.providers
    }
    poller = ConfiguredMultiAssetIntentPoller(
        config=config,
        fetch_bars=lambda symbol, timeframe, days, *, end_ms=None: _one_minute_bars(
            symbol
        ),
        collectors=collectors,
    )
    poller.activate(_OBSERVED_MS)

    result = poller.poll(_OBSERVED)
    second = poller.poll(datetime(2026, 8, 1, 12, 0, 15, tzinfo=UTC))

    assert result.intents == ()
    assert result.source_withheld == ()
    assert len(result.evaluations) == 10
    assert all(
        evaluation.decision_time_ms < _OBSERVED_MS for evaluation in result.evaluations
    )
    assert {
        evaluation.backend_non_action_reason for evaluation in result.evaluations
    } == {"pre_activation_readiness_seed"}
    assert {
        evaluation.as_payload()["backend_non_action_reason"]
        for evaluation in result.evaluations
    } == {"pre_activation_readiness_seed"}
    assert all(evaluation.eligible for evaluation in result.evaluations)
    assert second.evaluations == ()
    provider_sizes = {
        provider.strategy_id: len(provider.symbols) for provider in config.providers
    }
    assert all(
        len(collector.boundaries) == provider_sizes[strategy_id] * 3
        for strategy_id, collector in collectors.items()
    )


def test_first_fresh_row_does_not_bypass_missed_exit_recovery_seed() -> None:
    """Crossing a bar during startup must retain the pre-activation exit scan."""
    activation_ms = _OBSERVED_MS - 1_000
    config = load_multi_asset_live_config(
        "tests/fixtures/profiles/multi_asset_bidirectional_canary.toml",
        mode="observe",
    )
    collectors = {
        provider.strategy_id: _FreshStartupWithMissedExitCollector(
            provider.strategy_id,
            activation_ms,
        )
        for provider in config.providers
    }
    poller = ConfiguredMultiAssetIntentPoller(
        config=config,
        fetch_bars=lambda symbol, timeframe, days, *, end_ms=None: _one_minute_bars(
            symbol
        ),
        collectors=collectors,
    )
    poller.activate(activation_ms)

    result = poller.poll(_OBSERVED)

    assert len(result.intents) == len(result.evaluations)
    assert all(
        row.backend_non_action_reason == "pre_activation_readiness_seed"
        for row in result.evaluations
    )
    assert all(row.exit_sides for row in result.evaluations)
    assert all(intent.decision_time_ms > activation_ms for intent in result.intents)


def test_first_fresh_recipe_exit_is_not_hidden_by_readiness_seed() -> None:
    """A delayed first poll must retain a fresh post-activation recipe exit."""
    activation_ms = _OBSERVED_MS - 1_000
    config = load_multi_asset_live_config(
        "tests/fixtures/profiles/multi_asset_bidirectional_canary.toml",
        mode="observe",
    )
    collectors = {
        provider.strategy_id: _FreshStartupWithMissedExitCollector(
            provider.strategy_id,
            activation_ms,
            fresh_exit=True,
            seed_exit=False,
        )
        for provider in config.providers
    }
    poller = ConfiguredMultiAssetIntentPoller(
        config=config,
        fetch_bars=lambda symbol, timeframe, days, *, end_ms=None: _one_minute_bars(
            symbol
        ),
        collectors=collectors,
    )
    poller.activate(activation_ms)

    result = poller.poll(_OBSERVED)

    assert len(result.evaluations) == 10
    assert all(row.decision_time_ms > activation_ms for row in result.evaluations)
    assert all(row.exit_sides for row in result.evaluations)
    assert all(row.backend_non_action_reason is None for row in result.evaluations)


def test_poller_fetches_each_source_clock_and_advances_hold_boundaries() -> None:
    """Every provider advances causally even when it emits no entry intent."""
    config = load_multi_asset_live_config(
        "tests/fixtures/profiles/multi_asset_bidirectional_canary.toml",
        mode="observe",
    )
    calls: list[tuple[str, str, float, int | None]] = []

    def fetch(
        symbol: str,
        timeframe: str,
        lookback_days: float,
        *,
        end_ms: int | None = None,
    ) -> pd.DataFrame:
        calls.append((symbol, timeframe, lookback_days, end_ms))
        return _bars(symbol, timeframe)

    hulk = _Collector("hulk_expansion_bidirectional_tuned_v2", emit=True)
    range_onset = _Collector("range_onset_bidirectional_v1", emit=False)
    source_follow = _Collector(
        "hypervelocity_source_follow_bidirectional_5m_v1",
        emit=False,
    )
    hype_breakout = _Collector(
        "hype_breakout_onset_bidirectional_v1",
        emit=False,
    )
    poller = ConfiguredMultiAssetIntentPoller(
        config=config,
        fetch_bars=fetch,
        collectors={
            hulk.strategy_id: hulk,
            range_onset.strategy_id: range_onset,
            source_follow.strategy_id: source_follow,
            hype_breakout.strategy_id: hype_breakout,
        },
    )
    poller.activate(_OBSERVED_MS - 1_000)

    first = poller.poll(_OBSERVED)
    second = poller.poll(datetime(2026, 8, 1, 12, 0, 15, tzinfo=UTC))

    assert len(first.intents) == 4
    assert len(second.intents) == 4
    assert set(first.reference_prices) == {"BTC", "ETH", "SOL", "HYPE"}
    assert set(first.reference_prices.values()) == {101.0}
    scores = {intent.symbol: intent.regime_alignment_score for intent in first.intents}
    assert scores == {"BTC": -1.0, "ETH": 1.0, "SOL": -1.0, "HYPE": 1.0}
    assert all(intent.regime_decision_time_ms is not None for intent in first.intents)
    assert set(first.market_bars) == {"BTC", "ETH", "SOL", "HYPE"}
    btc_bars = first.market_bars["BTC"]
    assert [bar.timestamp_ms for bar in btc_bars] == [
        1_785_585_480_000,
        1_785_585_540_000,
    ]
    assert [
        (bar.open, bar.high, bar.low, bar.close, bar.volume) for bar in btc_bars
    ] == [
        (99.0, 101.0, 98.0, 100.0, 10.0),
        (100.0, 102.0, 99.0, 101.0, 11.0),
    ]
    _assert_startup_boundaries(hulk, symbols=4)
    _assert_startup_boundaries(range_onset, symbols=4)
    _assert_startup_boundaries(source_follow, symbols=1)
    _assert_startup_boundaries(hype_breakout, symbols=1)
    assert {(symbol, timeframe) for symbol, timeframe, _, _ in calls} == {
        (symbol, "1m") for symbol in config.symbols
    }
    assert all(days == config.lookback_days for _, _, days, _ in calls[:4])
    assert all(0.0 < days < 1.0 for _, _, days, _ in calls[4:])


def test_range_retired_profile_keeps_canonical_regime_outside_route_roster() -> None:
    """v39 routes remain exact while independent regime evidence weights intents."""
    config = load_multi_asset_live_config(
        "tests/fixtures/profiles/multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39.toml",
        mode="observe",
    )
    collectors = {
        provider.strategy_id: _Collector(
            provider.strategy_id,
            emit=provider.strategy_id == "hulk_expansion_bidirectional_tuned_v2",
        )
        for provider in config.providers
    }
    canonical = _CanonicalCollector()
    poller = ConfiguredMultiAssetIntentPoller(
        config=config,
        fetch_bars=lambda symbol, timeframe, days, *, end_ms=None: _one_minute_bars(
            symbol
        ),
        collectors=collectors,
        canonical_regime_collector=canonical,
    )
    poller.activate(_OBSERVED_MS - 1_000)

    result = poller.poll(_OBSERVED)

    configured = {provider.strategy_id for provider in config.providers}
    assert CANONICAL_REGIME_TELEMETRY_STRATEGY not in configured
    assert canonical.activations == [_OBSERVED_MS - 1_000]
    assert canonical.collections == 1
    assert len(result.evaluations) == sum(
        len(provider.symbols) for provider in config.providers
    )
    assert tuple(value.strategy_id for value in result.regime_evaluations) == (
        CANONICAL_REGIME_TELEMETRY_STRATEGY,
    )
    assert result.all_evaluations == result.evaluations + result.regime_evaluations
    btc = next(intent for intent in result.intents if intent.symbol == "BTC")
    assert btc.regime_alignment_stance == "directionally_opposed"


def test_stale_completed_entries_are_visible_but_not_routable() -> None:
    """A backend outage cannot turn old completed signals into live entries."""
    config = load_multi_asset_live_config(
        "tests/fixtures/profiles/multi_asset_bidirectional_canary.toml",
        mode="observe",
    )
    collectors = {
        provider.strategy_id: _Collector(provider.strategy_id, emit=True)
        for provider in config.providers
    }
    poller = ConfiguredMultiAssetIntentPoller(
        config=config,
        fetch_bars=lambda symbol, timeframe, days, *, end_ms=None: _bars(
            symbol, timeframe
        ),
        collectors=collectors,
    )
    poller.activate(1_000)

    result = poller.poll(_OBSERVED)

    assert result.intents == ()
    assert len(result.source_withheld) == 10
    assert {item.reason for item in result.source_withheld} == {
        "stale_completed_decision"
    }
    assert len(result.all_intents) == 10


def test_default_collectors_require_the_real_backtest_lab_root() -> None:
    """Runtime construction fails before polling when Hulk dependencies are absent."""
    config = load_multi_asset_live_config(
        "tests/fixtures/profiles/multi_asset_bidirectional_canary.toml",
        mode="observe",
    )

    try:
        ConfiguredMultiAssetIntentPoller.with_default_collectors(
            config=config,
            fetch_bars=lambda *_args, **_kwargs: pd.DataFrame(),
            backtest_lab_root=Path("does-not-exist"),
        )
    except FileNotFoundError as exc:
        assert "backtest-lab" in str(exc)
    else:
        raise AssertionError("missing Hulk dependency root was accepted")


@pytest.mark.integration
def test_default_collectors_support_the_staged_sol_aligned_provider() -> None:
    """The next-flat profile must have a concrete causal runtime collector."""
    config = load_multi_asset_live_config(
        "tests/fixtures/profiles/multi_asset_bidirectional_range_retired_hype75_candidate.toml",
        mode="observe",
    )

    poller = ConfiguredMultiAssetIntentPoller.with_default_collectors(
        config=config,
        fetch_bars=lambda *_args, **_kwargs: pd.DataFrame(),
        backtest_lab_root=Path("../backtest-lab/backtest_lab").resolve(),
    )

    assert poller is not None


def _assert_transient_fetch_failure_preserves_boundaries(
    error: requests.RequestException,
    reason: str,
) -> None:
    """Assert a retry-exhausted public read can recover on the next cycle."""
    config = load_multi_asset_live_config(
        "tests/fixtures/profiles/multi_asset_bidirectional_canary.toml",
        mode="observe",
    )
    collectors = {
        provider.strategy_id: _Collector(provider.strategy_id, emit=False)
        for provider in config.providers
    }
    failing = True

    def fetch(
        symbol: str,
        timeframe: str,
        lookback_days: float,
        *,
        end_ms: int | None = None,
    ) -> pd.DataFrame:
        del timeframe, lookback_days, end_ms
        if failing:
            raise error
        return _one_minute_bars(symbol)

    poller = ConfiguredMultiAssetIntentPoller(
        config=config,
        fetch_bars=fetch,
        collectors=collectors,
    )
    boundary = _OBSERVED_MS - 1_000
    poller.activate(boundary)

    with pytest.raises(
        TransientCohortMarketDataError,
        match=reason,
    ):
        poller.poll(_OBSERVED)

    assert all(not collector.boundaries for collector in collectors.values())
    failing = False
    result = poller.poll(_OBSERVED)
    assert len(result.evaluations) == 10
    assert all(collector.boundaries[0] == boundary for collector in collectors.values())


def test_exhausted_candle_429_is_classified_without_advancing_boundaries() -> None:
    """A throttled public read may retry next cycle without losing causal intents."""
    response = requests.Response()
    response.status_code = 429
    error = requests.HTTPError("rate limited", response=response)
    _assert_transient_fetch_failure_preserves_boundaries(
        error,
        "http_429_retry_exhausted",
    )


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (
            requests.ConnectionError("venue unavailable"),
            "transport_connection_retry_exhausted",
        ),
        (requests.Timeout("venue timed out"), "transport_timeout_retry_exhausted"),
    ],
)
def test_exhausted_candle_transport_is_classified_without_advancing_boundaries(
    error: requests.RequestException,
    reason: str,
) -> None:
    """A failed public transport may recover without losing causal intents."""
    _assert_transient_fetch_failure_preserves_boundaries(error, reason)


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_exhausted_candle_server_error_preserves_boundaries(status: int) -> None:
    """A temporary server failure withholds this cycle without losing intents."""
    response = requests.Response()
    response.status_code = status
    error = requests.HTTPError("temporary server failure", response=response)
    _assert_transient_fetch_failure_preserves_boundaries(
        error, "http_server_retry_exhausted"
    )


@pytest.mark.parametrize("status", [400, 401, 403, 404, 501])
def test_permanent_candle_http_error_remains_fatal(status: int) -> None:
    """Invalid requests and unsupported APIs cannot become temporary-data gaps."""
    config = load_multi_asset_live_config(
        "tests/fixtures/profiles/multi_asset_bidirectional_canary.toml",
        mode="observe",
    )
    collectors = {
        provider.strategy_id: _Collector(provider.strategy_id, emit=False)
        for provider in config.providers
    }
    response = requests.Response()
    response.status_code = status

    def fetch(
        symbol: str,
        timeframe: str,
        lookback_days: float,
        *,
        end_ms: int | None = None,
    ) -> pd.DataFrame:
        del symbol, timeframe, lookback_days, end_ms
        raise requests.HTTPError("server failure", response=response)

    poller = ConfiguredMultiAssetIntentPoller(
        config=config,
        fetch_bars=fetch,
        collectors=collectors,
    )
    poller.activate(_OBSERVED_MS - 1_000)

    with pytest.raises(requests.HTTPError, match="server failure"):
        poller.poll(_OBSERVED)

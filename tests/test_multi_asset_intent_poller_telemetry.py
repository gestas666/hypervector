"""Startup telemetry views for the multi-asset intent poller."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from hypervector.live.multi_asset_intent_poller import (
    ConfiguredMultiAssetIntentPoller,
)
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.multi_asset_signal_source import IntentBatch, ProviderEvaluation
from hypervector.live.provider_readiness import SignalReadiness

_OBSERVED = datetime(2026, 8, 1, 12, tzinfo=UTC)
_ACTIVATION_MS = int(_OBSERVED.timestamp() * 1_000)


class _MissedExitThenCurrentSetupCollector:
    """Return an old recovery exit followed by a current setup row."""

    def __init__(self, strategy_id: str) -> None:
        self._strategy_id = strategy_id

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
        if after_decision_time_ms == _ACTIVATION_MS:
            return IntentBatch((), _ACTIVATION_MS)
        recovery = _evaluation(
            self._strategy_id,
            symbol,
            _ACTIVATION_MS - 60_000,
            exit_side="long",
        )
        current = _evaluation(
            self._strategy_id,
            symbol,
            _ACTIVATION_MS - 1,
            exit_side=None,
        )
        return IntentBatch((), current.decision_time_ms, (recovery, current))


def test_startup_telemetry_shows_current_setup_without_losing_recovery_exit() -> None:
    """Screen telemetry and execution recovery must use separate startup views."""
    config = load_multi_asset_live_config(
        "configs/multi_asset_bidirectional_canary.toml",
        mode="observe",
    )
    poller = ConfiguredMultiAssetIntentPoller(
        config=config,
        fetch_bars=lambda symbol, timeframe, days, *, end_ms=None: _bars(),
        collectors={
            provider.strategy_id: _MissedExitThenCurrentSetupCollector(
                provider.strategy_id
            )
            for provider in config.providers
        },
    )
    poller.activate(_ACTIVATION_MS)

    result = poller.poll(_OBSERVED)

    assert result.evaluations
    assert all(row.exit_sides for row in result.evaluations)
    assert all(
        row.decision_time_ms == _ACTIVATION_MS - 60_000 for row in result.evaluations
    )
    assert len(result.telemetry_evaluations) == len(result.evaluations)
    assert all(not row.exit_sides for row in result.telemetry_evaluations)
    assert all(
        row.decision_time_ms == _ACTIVATION_MS - 1
        for row in result.telemetry_evaluations
    )


def _evaluation(
    strategy_id: str,
    symbol: str,
    decision_time_ms: int,
    *,
    exit_side: str | None,
) -> ProviderEvaluation:
    exit_sides = frozenset({exit_side}) if exit_side is not None else frozenset()
    return ProviderEvaluation(
        strategy_id=strategy_id,
        symbol=symbol,
        decision_time_ms=decision_time_ms,
        reference_price=100.0,
        decision_action="close_long" if exit_side else "hold",
        eligible=False,
        reason="missed_exit" if exit_side else "current_setup",
        side=None,
        readiness=SignalReadiness(None, 1, 2, ("waiting",), ("CURRENT 1/2",)),
        exit_sides=exit_sides,
        exit_reason="missed_exit" if exit_side else None,
    )


def _bars() -> pd.DataFrame:
    timestamps = pd.date_range("2026-08-01T11:50:00Z", periods=10, freq="1min")
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [100.0] * 10,
            "high": [101.0] * 10,
            "low": [99.0] * 10,
            "close": [100.0] * 10,
            "volume": [1.0] * 10,
        }
    )

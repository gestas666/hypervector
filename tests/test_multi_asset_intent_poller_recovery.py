"""Recovery coverage for the causal multi-asset candle poller."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from hypervector.live.multi_asset_intent_poller import (
    ConfiguredMultiAssetIntentPoller,
)
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.multi_asset_signal_source import IntentBatch, ProviderEvaluation

_START = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
_RECOVERY = datetime(2026, 8, 1, 12, 12, tzinfo=UTC)


class _ContiguousCollector:
    """Reject a source frame containing an outage-created cadence hole."""

    def __init__(self, strategy_id: str, minutes: int) -> None:
        self._strategy_id = strategy_id
        self._minutes = minutes

    def __call__(
        self,
        bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> IntentBatch:
        del symbol, observed_at
        cadence = pd.DatetimeIndex(bars["timestamp"]).to_series().diff().dropna()
        expected = pd.Timedelta(minutes=self._minutes)
        if not cadence.eq(expected).all():
            raise ValueError(f"{self._strategy_id} fixture bars are not contiguous")
        assert after_decision_time_ms is not None
        return IntentBatch((), after_decision_time_ms + 1, ())


class _CanonicalCollector:
    """Keep this regression focused on the provider source frames."""

    def activate(self, activation_time_ms: int) -> None:
        """Accept the shared activation boundary."""
        assert activation_time_ms >= 0

    def collect(
        self,
        bars: object,
        observed_at: pd.Timestamp,
    ) -> tuple[ProviderEvaluation, ...]:
        """Return no independent regime rows for this fixture."""
        del bars, observed_at
        return ()


def test_recovery_fetch_bridges_an_outage_longer_than_incremental_window() -> None:
    """A stale cache must backfill its full hole before providers resume."""
    config = load_multi_asset_live_config(
        "tests/fixtures/profiles/cohort_base.toml",
        mode="observe",
    )
    master = _minute_bars()
    calls: list[float] = []

    def fetch(
        symbol: str,
        timeframe: str,
        lookback_days: float,
        *,
        end_ms: int | None = None,
    ) -> pd.DataFrame:
        del symbol, timeframe
        assert end_ms is not None
        calls.append(lookback_days)
        start_ms = end_ms - int(lookback_days * 86_400_000)
        timestamps = pd.DatetimeIndex(master["timestamp"])
        return master.loc[
            (timestamps >= pd.Timestamp(start_ms, unit="ms", tz="UTC"))
            & (timestamps <= pd.Timestamp(end_ms, unit="ms", tz="UTC"))
        ].copy()

    collectors = {
        provider.strategy_id: _ContiguousCollector(
            provider.strategy_id,
            5 if provider.timeframe == "30m" else 1,
        )
        for provider in config.providers
    }
    poller = ConfiguredMultiAssetIntentPoller(
        config=config,
        fetch_bars=fetch,
        collectors=collectors,
        canonical_regime_collector=_CanonicalCollector(),
    )
    poller.activate(int(_START.timestamp() * 1_000) - 1)

    poller.poll(_START)
    poller.poll(_RECOVERY)

    second_cycle = calls[len(config.symbols) :]
    assert min(second_cycle) >= 13.0 / (24.0 * 60.0)


def _minute_bars() -> pd.DataFrame:
    """Return one deterministic minute source spanning both poll cycles."""
    timestamps = pd.date_range("2026-08-01T11:40:00Z", periods=34, freq="1min")
    closes = pd.Series(range(100, 134), dtype=float)
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": closes - 0.25,
            "high": closes + 0.5,
            "low": closes - 0.5,
            "close": closes,
            "volume": 1.0,
        }
    )

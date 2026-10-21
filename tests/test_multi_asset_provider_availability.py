"""Provider-local availability recovery for the multi-asset poller."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from hypervector.live.hip3_provider_availability import (
    Hip3ObserverUnavailableError,
)
from hypervector.live.multi_asset_intent_poller import (
    ConfiguredMultiAssetIntentPoller,
)
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.multi_asset_polling_contract import (
    READINESS_SEED_LOOKBACK_MINUTES,
)
from hypervector.live.provider_evaluation import IntentBatch, ProviderEvaluation
from hypervector.live.provider_readiness import SignalReadiness

_CONFIG = Path(
    "tests/fixtures/profiles/six_asset_profit_lock.toml"
)
_OBSERVED = datetime(2026, 8, 15, 12, tzinfo=UTC)
_OBSERVED_MS = int(_OBSERVED.timestamp() * 1_000)
_HIP3_PROVIDER = "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3"


class _CanonicalCollector:
    """No-op canonical regime collector for this provider isolation test."""

    def activate(self, activation_time_ms: int) -> None:
        """Accept the shared activation boundary."""
        del activation_time_ms

    def collect(
        self,
        bars: object,
        observed_at: pd.Timestamp,
    ) -> tuple[ProviderEvaluation, ...]:
        """Return no independent regime rows."""
        del bars, observed_at
        return ()


class _Collector:
    """Emit one attributed hold evaluation and remember causal boundaries."""

    def __init__(self, strategy_id: str) -> None:
        self.strategy_id = strategy_id
        self.boundaries: dict[str, list[int | None]] = {}

    def __call__(
        self,
        bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> IntentBatch:
        """Return a non-entry evaluation one millisecond after the cursor."""
        del bars, observed_at
        self.boundaries.setdefault(symbol, []).append(after_decision_time_ms)
        boundary = (after_decision_time_ms or 0) + 1
        evaluation = ProviderEvaluation(
            strategy_id=self.strategy_id,
            symbol=symbol,
            decision_time_ms=boundary,
            reference_price=129.0,
            decision_action="hold",
            eligible=False,
            reason="fixture_hold",
            side=None,
            readiness=SignalReadiness(
                side=None,
                conditions_met=0,
                conditions_required=1,
                blockers=("fixture_hold",),
                indicators=("FIXTURE HOLD",),
            ),
        )
        return IntentBatch((), boundary, (evaluation,))


class _RecoveringHip3Collector(_Collector):
    """Fail only SP500 once, then recover on the next portfolio cycle."""

    def __init__(self) -> None:
        super().__init__(_HIP3_PROVIDER)
        self.unavailable = True

    def __call__(
        self,
        bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> IntentBatch:
        """Raise the typed availability error only for the failed route."""
        self.boundaries.setdefault(symbol, []).append(after_decision_time_ms)
        if symbol == "xyz:SP500" and self.unavailable:
            raise Hip3ObserverUnavailableError("observer_status_stale")
        self.boundaries[symbol].pop()
        return super().__call__(
            bars,
            symbol=symbol,
            observed_at=observed_at,
            after_decision_time_ms=after_decision_time_ms,
        )


class _ReadinessSeedUnavailableCollector(_Collector):
    """Become unavailable only during the second startup-readiness call."""

    def __init__(self) -> None:
        super().__init__(_HIP3_PROVIDER)
        self.calls: dict[str, int] = {}

    def __call__(
        self,
        bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> IntentBatch:
        """Return no new row, then expose a technical source outage."""
        del bars, observed_at
        self.calls[symbol] = self.calls.get(symbol, 0) + 1
        if self.calls[symbol] == 1:
            return IntentBatch((), after_decision_time_ms or 0, ())
        raise Hip3ObserverUnavailableError("cash_open_trade_bars_incomplete")


def _one_minute_bars(symbol: str) -> pd.DataFrame:
    """Return complete causal OHLCV rows for every configured symbol."""
    del symbol
    close = [100.0 + index for index in range(30)]
    return pd.DataFrame(
        {
            "timestamp": pd.date_range(
                "2026-08-15T11:30:00Z",
                periods=30,
                freq="1min",
            ),
            "open": close,
            "high": [value + 1.0 for value in close],
            "low": [value - 1.0 for value in close],
            "close": close,
            "volume": [1.0] * 30,
        }
    )


def test_one_stale_observer_does_not_stop_portfolio_polling() -> None:
    """A technical route outage is explicit and preserves its decision cursor."""
    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    hip3 = _RecoveringHip3Collector()
    collectors = {
        provider.strategy_id: (
            hip3
            if provider.strategy_id == _HIP3_PROVIDER
            else _Collector(provider.strategy_id)
        )
        for provider in config.providers
    }
    poller = ConfiguredMultiAssetIntentPoller(
        config=config,
        fetch_bars=lambda symbol, timeframe, days, *, end_ms=None: _one_minute_bars(
            symbol
        ),
        collectors=collectors,
        canonical_regime_collector=_CanonicalCollector(),
    )
    activation = _OBSERVED_MS - 1_000
    poller.activate(activation)

    first = poller.poll(_OBSERVED)
    hip3.unavailable = False
    second = poller.poll(datetime(2026, 8, 15, 12, 0, 15, tzinfo=UTC))

    unavailable = next(row for row in first.evaluations if row.symbol == "xyz:SP500")
    assert unavailable.decision_action == "technical_unavailable"
    assert unavailable.backend_non_action_reason == "observer_status_stale"
    assert unavailable.readiness.blockers == ("observer_status_stale",)
    assert len(first.evaluations) == 7
    assert hip3.boundaries["xyz:SP500"] == [activation, activation]
    seed_boundary = activation - (
        READINESS_SEED_LOOKBACK_MINUTES[_HIP3_PROVIDER] * 60 * 1_000
    )
    assert hip3.boundaries["xyz:SPCX"] == [
        activation,
        seed_boundary,
        activation + 1,
    ]
    assert any(row.symbol == "xyz:SP500" for row in second.evaluations)


def test_readiness_seed_unavailability_does_not_stop_portfolio_polling() -> None:
    """A source outage during the startup seed remains provider-local."""
    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    hip3 = _ReadinessSeedUnavailableCollector()
    collectors = {
        provider.strategy_id: (
            hip3
            if provider.strategy_id == _HIP3_PROVIDER
            else _Collector(provider.strategy_id)
        )
        for provider in config.providers
    }
    poller = ConfiguredMultiAssetIntentPoller(
        config=config,
        fetch_bars=lambda symbol, timeframe, days, *, end_ms=None: _one_minute_bars(
            symbol
        ),
        collectors=collectors,
        canonical_regime_collector=_CanonicalCollector(),
    )
    poller.activate(_OBSERVED_MS - 1_000)

    result = poller.poll(_OBSERVED)

    unavailable = next(row for row in result.evaluations if row.symbol == "xyz:SP500")
    assert unavailable.decision_action == "technical_unavailable"
    assert unavailable.reason == "cash_open_trade_bars_incomplete"
    assert unavailable.backend_non_action_reason == "cash_open_trade_bars_incomplete"
    assert unavailable.readiness.blockers == ("cash_open_trade_bars_incomplete",)
    assert len(result.evaluations) == 7

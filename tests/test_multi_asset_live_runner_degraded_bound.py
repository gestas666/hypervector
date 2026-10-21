"""The account-blindness bound is wall-clock time, not a count of polls.

A degraded poll lands about two minutes after the previous one once transport
retries are exhausted (median 123.5 s on the live ledger), so the former bound
of 240 polls meant about 8.2 hours of blindness instead of the documented hour.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import requests

from multi_asset_live_runner_fixtures import execution_contract as _contract
from test_multi_asset_live_runner import _SYMBOLS, _Engine, _Poller, _Telemetry
from test_multi_asset_live_runner import _router

from hypervector.live.hyperliquid_protocol import HyperliquidReconciliationSnapshot
from hypervector.live.multi_asset_intent_poller import CohortIntentPoll
from hypervector.live.multi_asset_live_runner import MultiAssetLiveRunner
from hypervector.live.multi_asset_live_runner_support import (
    CohortDegradedBlindnessError,
    MultiAssetLiveRunnerError,
)
from hypervector.live.multi_asset_market_bars import TransientCohortMarketDataError

# The measured wall time of one retry-exhausted read.
_FAILED_POLL_SECONDS = 108.0


class _Scenario:
    """Per-poll outcomes on a clock that moves only when a poll or a sleep spends it.

    The runner sleeps once at the end of every poll it continues from, so the
    sleep is the boundary between one scripted poll and the next.
    """

    def __init__(self, modes: tuple[str, ...]) -> None:
        self.modes = modes
        self.index = 0
        self.now = 1_000.0

    @property
    def mode(self) -> str:
        return self.modes[self.index] if self.index < len(self.modes) else "ok"

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds
        self.index += 1


class _AccountBlindEngine(_Engine):
    """Fail account reconciliation while the scripted poll says so."""

    def __init__(self, symbol: str, scenario: _Scenario) -> None:
        super().__init__(symbol)
        self._scenario = scenario

    def reconcile_telemetry(
        self, *, funding_start_time_ms: int, funding_end_time_ms: int
    ) -> HyperliquidReconciliationSnapshot:
        if self._scenario.mode == "account":
            self._scenario.now += _FAILED_POLL_SECONDS
            raise requests.ConnectionError("venue unreachable")
        return super().reconcile_telemetry(
            funding_start_time_ms=funding_start_time_ms,
            funding_end_time_ms=funding_end_time_ms,
        )


class _MarketBlindPoller(_Poller):
    """Fail public market data while the scripted poll says so."""

    def __init__(self, scenario: _Scenario) -> None:
        super().__init__((), (), ())
        self._scenario = scenario

    def poll(self, observed_at: datetime) -> CohortIntentPoll:
        if self._scenario.mode == "market":
            self._scenario.now += _FAILED_POLL_SECONDS
            raise TransientCohortMarketDataError(
                source="BTC_candles", reason="transport_timeout_retry_exhausted"
            )
        return super().poll(observed_at)


def _runner(
    tmp_path: Path,
    modes: tuple[str, ...],
    **bound: float,
) -> tuple[MultiAssetLiveRunner, dict[str, _Engine], _Telemetry, _Scenario]:
    scenario = _Scenario(modes)
    telemetry = _Telemetry(None)
    engines: dict[str, _Engine] = {
        symbol: _AccountBlindEngine(symbol, scenario) for symbol in _SYMBOLS
    }
    pairs = frozenset(("test_trend_provider", symbol) for symbol in _SYMBOLS)
    runner = MultiAssetLiveRunner(
        symbols=_SYMBOLS,
        engines=engines,
        router=_router(),
        intent_poller=_MarketBlindPoller(scenario),
        telemetry=telemetry,
        stop_file=tmp_path / "STOP",
        now_fn=lambda: datetime(2026, 8, 1, 12, tzinfo=UTC),
        sleep_fn=scenario.sleep,
        poll_seconds=15.0,
        signal_stop_requested=lambda: False,
        maximum_hold_seconds_by_symbol={symbol: 28_800 for symbol in _SYMBOLS},
        execution_contracts={"test_trend_provider": _contract()},
        maximum_entry_delay_ms_by_provider_symbol={pair: 60_000 for pair in pairs},
        executable_provider_symbols=pairs,
        monotonic_fn=scenario.monotonic,
        **bound,
    )
    return runner, engines, telemetry, scenario


def test_default_bound_ends_account_blindness_after_one_hour(tmp_path: Path) -> None:
    """The documented intent: one hour of blindness, whatever the poll cadence."""
    runner, _, telemetry, scenario = _runner(tmp_path, ("account",) * 100)

    with pytest.raises(CohortDegradedBlindnessError, match="3672s across 34"):
        runner.run(max_polls=500)

    # 33 failed polls is 3,564 s; the 34th crosses 3,600 s.
    assert len(telemetry.degraded_polls) == 34
    assert scenario.now - 1_000.0 == 34 * _FAILED_POLL_SECONDS


def test_bound_trips_exactly_at_the_configured_seconds(tmp_path: Path) -> None:
    """Reaching the bound trips it; one tick short does not."""
    exact = 5 * _FAILED_POLL_SECONDS
    runner, _, telemetry, _ = _runner(
        tmp_path, ("account",) * 20, maximum_degraded_seconds=exact
    )
    with pytest.raises(CohortDegradedBlindnessError):
        runner.run(max_polls=50)
    assert len(telemetry.degraded_polls) == 5

    runner, _, telemetry, _ = _runner(
        tmp_path, ("account",) * 20, maximum_degraded_seconds=exact + 0.001
    )
    with pytest.raises(CohortDegradedBlindnessError):
        runner.run(max_polls=50)
    assert len(telemetry.degraded_polls) == 6


def test_the_bound_is_time_not_poll_count(tmp_path: Path) -> None:
    """Fast-failing polls take many more polls to reach the same wall-clock bound."""
    runner, engines, telemetry, scenario = _runner(
        tmp_path, ("account",) * 400, maximum_degraded_seconds=3_600.0
    )

    def fast_failure(**_kwargs: object) -> HyperliquidReconciliationSnapshot:
        scenario.now += 1.0
        raise requests.Timeout("read timed out")

    engines["BTC"].reconcile_telemetry = fast_failure  # type: ignore[method-assign]

    with pytest.raises(CohortDegradedBlindnessError):
        runner.run(max_polls=1_000)

    # Each poll costs 1 s of reads plus the rest of its 15 s cadence, so the
    # 241st failure lands at 3,601 s: a count of 240 would have tripped at 3,586 s.
    assert len(telemetry.degraded_polls) == 241
    assert telemetry.degraded_polls[0] == (
        "hyperliquid_account_reconciliation",
        "transport_timeout_retry_exhausted",
    )


def test_a_successful_poll_clears_the_account_streak(tmp_path: Path) -> None:
    """Intermittent failures never accumulate toward the bound."""
    bound = 1.5 * _FAILED_POLL_SECONDS
    alternating = ("account", "ok") * 10
    runner, _, telemetry, _ = _runner(
        tmp_path, alternating, maximum_degraded_seconds=bound
    )

    assert runner.run(max_polls=20) == 20
    assert len(telemetry.degraded_polls) == 10

    runner, _, _, _ = _runner(
        tmp_path, ("account", "account"), maximum_degraded_seconds=bound
    )
    with pytest.raises(CohortDegradedBlindnessError):
        runner.run(max_polls=20)


def test_market_data_blindness_never_trips_the_account_bound(
    tmp_path: Path,
) -> None:
    """A candle outage keeps the account reconciled and its deadlines running.

    Ending the process would not repair a public-data outage; it would only
    spend a restart and stop the unconditional deadlines that still run.
    """
    runner, engines, telemetry, scenario = _runner(
        tmp_path, ("market",) * 120, maximum_degraded_seconds=3_600.0
    )

    assert runner.run(max_polls=120) == 120

    assert scenario.now - 1_000.0 > 3 * 3_600.0
    assert len(telemetry.degraded_polls) == 120
    assert set(telemetry.degraded_polls) == {
        ("BTC_candles", "transport_timeout_retry_exhausted")
    }
    # Every degraded market poll reconciled twice: once before acquisition and
    # once for the unconditional deadlines.
    assert len(engines["BTC"].reconciliations) == 240


def test_a_market_data_poll_proves_the_account_was_visible(tmp_path: Path) -> None:
    """Reconciliation succeeded before the market read failed, so blindness resets."""
    modes = ("account",) * 30 + ("market",) + ("account",) * 30
    runner, _, telemetry, _ = _runner(tmp_path, modes, maximum_degraded_seconds=3_600.0)

    assert runner.run(max_polls=61) == 61
    assert len(telemetry.degraded_polls) == 61


@pytest.mark.parametrize("value", [0.0, -1.0, float("nan"), float("inf")])
def test_bound_must_be_positive_and_finite(tmp_path: Path, value: float) -> None:
    with pytest.raises(MultiAssetLiveRunnerError, match="maximum_degraded_seconds"):
        _runner(tmp_path, (), maximum_degraded_seconds=value)

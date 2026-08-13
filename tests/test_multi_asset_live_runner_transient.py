"""Transient public-data recovery tests for the live cohort runner."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from hyperliquid.utils.error import ClientError  # type: ignore[import-untyped]
import pytest
from requests import ReadTimeout

from hypervector.live.hyperliquid_protocol import SolReconciliationSnapshot
from hypervector.live.multi_asset_intent_poller import CohortIntentPoll
from hypervector.live.multi_asset_live_runner import MultiAssetLiveRunner
from hypervector.live.multi_asset_market_bars import TransientCohortMarketDataError
from test_multi_asset_live_runner import (
    _SYMBOLS,
    _Engine,
    _Poller,
    _Telemetry,
    _contract,
    _router,
)


class _TransientPoller(_Poller):
    def __init__(self) -> None:
        super().__init__(())
        self.attempts = 0

    def poll(self, observed_at: datetime) -> CohortIntentPoll:
        self.attempts += 1
        if self.attempts == 1:
            raise TransientCohortMarketDataError(
                source="hyperliquid_public_candles",
                reason="http_429_retry_exhausted",
            )
        return super().poll(observed_at)


class _TransientReconcileEngine(_Engine):
    def __init__(self, symbol: str, failure: Exception) -> None:
        super().__init__(symbol)
        self._failure = failure
        self.reconcile_attempts = 0

    def reconcile_telemetry(
        self,
        *,
        funding_start_time_ms: int,
        funding_end_time_ms: int,
    ) -> SolReconciliationSnapshot:
        self.reconcile_attempts += 1
        if self.reconcile_attempts == 1:
            raise self._failure
        return super().reconcile_telemetry(
            funding_start_time_ms=funding_start_time_ms,
            funding_end_time_ms=funding_end_time_ms,
        )


def test_exhausted_public_candle_429_skips_cycle_without_stopping_runner(
    tmp_path: Path,
) -> None:
    """A classified public-read throttle is journaled and retried next cycle."""
    engines = {symbol: _Engine(symbol) for symbol in _SYMBOLS}
    telemetry = _Telemetry()
    poller = _TransientPoller()
    runner = MultiAssetLiveRunner(
        symbols=_SYMBOLS,
        engines=engines,
        router=_router(),
        intent_poller=poller,
        telemetry=telemetry,
        stop_file=tmp_path / "STOP",
        now_fn=lambda: datetime(2026, 8, 1, 12, tzinfo=UTC),
        sleep_fn=lambda _: None,
        poll_seconds=15.0,
        signal_stop_requested=lambda: False,
        maximum_hold_seconds_by_symbol={symbol: 28_800 for symbol in _SYMBOLS},
        execution_contracts={"hulk": _contract()},
        executable_provider_symbols=frozenset(("hulk", symbol) for symbol in _SYMBOLS),
    )

    assert runner.run(max_polls=2) == 2
    assert poller.attempts == 2
    assert telemetry.degraded_polls == [
        ("hyperliquid_public_candles", "http_429_retry_exhausted")
    ]
    assert telemetry.heartbeats == 1
    assert all(not engine.entries and not engine.exits for engine in engines.values())


def test_exhausted_account_timeout_skips_cycle_without_stopping_runner(
    tmp_path: Path,
) -> None:
    """Retry-exhausted account transport failure cannot terminate supervision."""
    engines = {symbol: _Engine(symbol) for symbol in _SYMBOLS}
    transient = _TransientReconcileEngine("BTC", ReadTimeout("deadline"))
    engines["BTC"] = transient
    telemetry = _Telemetry()
    runner = _runner(tmp_path, engines, telemetry)

    assert runner.run(max_polls=2) == 2
    assert transient.reconcile_attempts == 2
    assert telemetry.degraded_polls == [
        ("hyperliquid_account_reconciliation", "transport_timeout_retry_exhausted")
    ]
    assert telemetry.heartbeats == 1


def test_exhausted_account_429_skips_cycle_without_stopping_runner(
    tmp_path: Path,
) -> None:
    """Retry-exhausted HTTP 429 remains an explicit recoverable live cycle."""
    engines = {symbol: _Engine(symbol) for symbol in _SYMBOLS}
    transient = _TransientReconcileEngine(
        "BTC",
        ClientError(429, None, "limited", {}),
    )
    engines["BTC"] = transient
    telemetry = _Telemetry()
    runner = _runner(tmp_path, engines, telemetry)

    assert runner.run(max_polls=2) == 2
    assert transient.reconcile_attempts == 2
    assert telemetry.degraded_polls == [
        ("hyperliquid_account_reconciliation", "http_429_retry_exhausted")
    ]


def test_nonretryable_account_client_error_still_fails_closed(tmp_path: Path) -> None:
    """A non-transient venue rejection cannot be mislabeled as degradation."""
    engines = {symbol: _Engine(symbol) for symbol in _SYMBOLS}
    engines["BTC"] = _TransientReconcileEngine(
        "BTC",
        ClientError(422, None, "rejected", {}),
    )
    telemetry = _Telemetry()

    with pytest.raises(ClientError) as caught:
        _runner(tmp_path, engines, telemetry).run(max_polls=2)

    assert caught.value.status_code == 422
    assert telemetry.degraded_polls == []


def _runner(
    tmp_path: Path,
    engines: dict[str, _Engine],
    telemetry: _Telemetry,
) -> MultiAssetLiveRunner:
    return MultiAssetLiveRunner(
        symbols=_SYMBOLS,
        engines=engines,
        router=_router(),
        intent_poller=_Poller(()),
        telemetry=telemetry,
        stop_file=tmp_path / "STOP",
        now_fn=lambda: datetime(2026, 8, 1, 12, tzinfo=UTC),
        sleep_fn=lambda _: None,
        poll_seconds=15.0,
        signal_stop_requested=lambda: False,
        maximum_hold_seconds_by_symbol={symbol: 28_800 for symbol in _SYMBOLS},
        execution_contracts={"hulk": _contract()},
        executable_provider_symbols=frozenset(("hulk", symbol) for symbol in _SYMBOLS),
    )

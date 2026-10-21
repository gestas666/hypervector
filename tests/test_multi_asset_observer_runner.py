"""Execution-incapable multi-asset observer runner tests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from requests import ReadTimeout

from hypervector.live.bidirectional_intents import StrategyIntent, WithheldIntent
from hypervector.live.multi_asset_intent_poller import (
    CohortIntentPoll,
    CohortMarketBar,
)
from hypervector.live.multi_asset_observer_runner import (
    MultiAssetObserverRunner,
    MultiAssetObserverRunnerError,
)
from hypervector.live.provider_evaluation import ProviderEvaluation
from hypervector.live.provider_readiness import SignalReadiness
from hypervector.live.hyperliquid_protocol import SolBookLevel, SolBookSnapshot

_OBSERVED = datetime(2026, 8, 2, 6, tzinfo=UTC)
_OBSERVED_MS = int(_OBSERVED.timestamp() * 1_000)
_SYMBOLS = ("BTC", "ETH", "SOL", "HYPE")
_PROVIDERS = (
    "hulk_expansion_bidirectional_tuned_v2",
    "range_onset_bidirectional_v1",
)
_EXPECTED = frozenset(
    (provider, symbol) for provider in _PROVIDERS for symbol in _SYMBOLS
)


class _Poller:
    def __init__(self, poll: CohortIntentPoll) -> None:
        self.result = poll
        self.activation_time_ms: int | None = None
        self.observed_at: list[datetime] = []

    def activate(self, activation_time_ms: int) -> None:
        self.activation_time_ms = activation_time_ms

    def poll(self, observed_at: datetime) -> CohortIntentPoll:
        self.observed_at.append(observed_at)
        return self.result


class _Telemetry:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.degraded_polls: list[tuple[str, str]] = []
        self.routing: tuple[tuple[StrategyIntent, ...], object, object] | None = None
        self.regime_evaluations: tuple[ProviderEvaluation, ...] = ()

    def emit_configuration(self) -> None:
        self.events.append("configuration")

    def emit_market_bars(self, _bars: object) -> None:
        self.events.append("market_bars")

    def emit_market_books(self, _books: object) -> None:
        self.events.append("market_books")

    def emit_canonical_regimes(
        self, evaluations: tuple[ProviderEvaluation, ...]
    ) -> None:
        self.events.append("canonical_regimes")
        self.regime_evaluations = evaluations

    def emit_routing(
        self,
        intents: tuple[StrategyIntent, ...],
        report: object,
        evaluations: object = (),
    ) -> None:
        self.events.append("routing")
        self.routing = (intents, report, evaluations)

    def emit_heartbeat(self) -> None:
        self.events.append("heartbeat")

    def emit_stopped(self, *, reason: str) -> None:
        self.events.append(f"stopped:{reason}")

    def emit_poll_degraded(self, *, source: str, reason: str) -> None:
        self.degraded_polls.append((source, reason))


class _TransientBookSource:
    def __init__(self) -> None:
        self.attempts = 0

    def __call__(self) -> dict[str, SolBookSnapshot]:
        self.attempts += 1
        if self.attempts == 1:
            raise ReadTimeout("public L2 deadline")
        return _books()


def _intent(symbol: str, side: str, *, strategy: str = _PROVIDERS[1]) -> StrategyIntent:
    return StrategyIntent(strategy, symbol, side, _OBSERVED_MS, 100.0, "fixture")


def _evaluation(provider: str, symbol: str) -> ProviderEvaluation:
    return ProviderEvaluation(
        strategy_id=provider,
        symbol=symbol,
        decision_time_ms=_OBSERVED_MS,
        reference_price=100.0,
        decision_action="hold",
        eligible=False,
        reason="fixture_hold",
        side="long",
        readiness=SignalReadiness(
            side="long",
            conditions_met=2,
            conditions_required=3,
            blockers=("fixture_blocker",),
            indicators=("FIXTURE 2/3",),
        ),
    )


def _market_bars() -> dict[str, tuple[CohortMarketBar, ...]]:
    return {
        symbol: (
            CohortMarketBar(
                symbol, _OBSERVED_MS - 60_000, 99.0, 101.0, 98.0, 100.0, 1.0
            ),
        )
        for symbol in _SYMBOLS
    }


def _books() -> dict[str, SolBookSnapshot]:
    return {
        symbol: SolBookSnapshot(
            _OBSERVED_MS,
            (SolBookLevel(99.9, 2.0, 1),),
            (SolBookLevel(100.1, 2.0, 1),),
            100.0,
            20.0,
            2.0,
            2.0,
            0.0,
        )
        for symbol in _SYMBOLS
    }


def _poll(
    *,
    evaluations: tuple[ProviderEvaluation, ...] | None = None,
    display_evaluations: tuple[ProviderEvaluation, ...] | None = None,
    regime_evaluations: tuple[ProviderEvaluation, ...] = (),
) -> CohortIntentPoll:
    fresh = _intent("BTC", "long")
    stale = _intent("SOL", "short", strategy=_PROVIDERS[0])
    return CohortIntentPoll(
        intents=(fresh,),
        reference_prices={symbol: 100.0 for symbol in _SYMBOLS},
        source_withheld=(WithheldIntent(stale, "stale_completed_decision"),),
        market_bars=_market_bars(),
        evaluations=evaluations
        if evaluations is not None
        else tuple(_evaluation(*pair) for pair in sorted(_EXPECTED)),
        display_evaluations=display_evaluations,
        regime_evaluations=regime_evaluations,
    )


def _runner(
    tmp_path: Path,
    poll: CohortIntentPoll,
    *,
    emit_configuration_on_start: bool = True,
    sleep_fn: Callable[[float], None] | None = None,
    signal_stop_requested: Callable[[], bool] | None = None,
) -> tuple[MultiAssetObserverRunner, _Poller, _Telemetry]:
    poller = _Poller(poll)
    telemetry = _Telemetry()
    runner = MultiAssetObserverRunner(
        symbols=_SYMBOLS,
        expected_provider_symbols=_EXPECTED,
        intent_poller=poller,
        book_source=_books,
        telemetry=telemetry,
        stop_file=tmp_path / "STOP",
        now_fn=lambda: _OBSERVED,
        sleep_fn=sleep_fn or (lambda _seconds: None),
        poll_seconds=15.0,
        signal_stop_requested=signal_stop_requested or (lambda: False),
        emit_configuration_on_start=emit_configuration_on_start,
    )
    return runner, poller, telemetry


def test_resumed_observer_does_not_duplicate_configuration_identity(
    tmp_path: Path,
) -> None:
    """A continued run appends cycles under its existing frozen identity."""
    runner, _poller, telemetry = _runner(
        tmp_path,
        _poll(),
        emit_configuration_on_start=False,
    )

    assert runner.run(max_polls=1) == 1
    assert telemetry.events == [
        "market_books",
        "market_bars",
        "routing",
        "heartbeat",
        "stopped:bounded_run_complete",
    ]


def test_observer_retries_transient_public_l2_failure(tmp_path: Path) -> None:
    """A retry-exhausted public read is journaled without ending observation."""
    poller = _Poller(_poll())
    telemetry = _Telemetry()
    books = _TransientBookSource()
    runner = MultiAssetObserverRunner(
        symbols=_SYMBOLS,
        expected_provider_symbols=_EXPECTED,
        intent_poller=poller,
        book_source=books,
        telemetry=telemetry,
        stop_file=tmp_path / "STOP",
        now_fn=lambda: _OBSERVED,
        sleep_fn=lambda _seconds: None,
        poll_seconds=15.0,
        signal_stop_requested=lambda: False,
    )

    assert runner.run(max_polls=2) == 2
    assert books.attempts == 2
    assert telemetry.degraded_polls == [
        ("hyperliquid_public_l2", "transport_timeout_retry_exhausted")
    ]
    assert telemetry.events[-2:] == ["heartbeat", "stopped:bounded_run_complete"]


def test_observer_publishes_full_readiness_and_withholds_every_intent(
    tmp_path: Path,
) -> None:
    """The observer uses production decisions but grants no routing authority."""
    runner, poller, telemetry = _runner(tmp_path, _poll())

    assert runner.run(max_polls=1) == 1

    assert poller.activation_time_ms == _OBSERVED_MS
    assert telemetry.events == [
        "configuration",
        "market_books",
        "market_bars",
        "routing",
        "heartbeat",
        "stopped:bounded_run_complete",
    ]
    assert telemetry.routing is not None
    intents, report, evaluations = telemetry.routing
    assert len(intents) == 2
    assert report.actions == ()
    assert {item.reason for item in report.withheld} == {
        "stale_completed_decision",
        "observe_mode_no_execution",
    }
    assert len(evaluations) == 8


def test_observer_publishes_display_rows_instead_of_recovery_rows(
    tmp_path: Path,
) -> None:
    """Startup recovery evidence must not replace fresher Screen 2 setup rows."""
    recovery = tuple(_evaluation(*pair) for pair in sorted(_EXPECTED))
    display = tuple(
        replace(
            row,
            decision_time_ms=row.decision_time_ms + 1,
            reason="current_setup",
        )
        for row in recovery
    )
    runner, _poller, telemetry = _runner(
        tmp_path,
        _poll(evaluations=recovery, display_evaluations=display),
    )

    assert runner.run(max_polls=1) == 1
    assert telemetry.routing is not None
    assert telemetry.routing[2] == display


def test_observer_publishes_independent_canonical_regime_evidence(
    tmp_path: Path,
) -> None:
    """Observe mode must retain canonical regimes for routes without native states."""
    canonical = (_evaluation("canonical_regime_telemetry_v1", "BTC"),)
    runner, _poller, telemetry = _runner(
        tmp_path,
        _poll(regime_evaluations=canonical),
    )

    assert runner.run(max_polls=1) == 1
    assert telemetry.regime_evaluations == canonical
    assert telemetry.events == [
        "configuration",
        "market_books",
        "market_bars",
        "canonical_regimes",
        "routing",
        "heartbeat",
        "stopped:bounded_run_complete",
    ]


def test_observer_samples_intent_clock_after_book_capture(tmp_path: Path) -> None:
    """Observer decisions must causally see the same-cycle recorded book."""
    activation = datetime(2026, 8, 2, 5, 59, 58, tzinfo=UTC)
    before_book = datetime(2026, 8, 2, 6, 0, 0, tzinfo=UTC)
    after_book = datetime(2026, 8, 2, 6, 0, 3, tzinfo=UTC)
    clock = iter((activation, before_book, after_book))
    poller = _Poller(_poll())
    telemetry = _Telemetry()

    def books() -> dict[str, SolBookSnapshot]:
        assert next(clock) == before_book
        return {
            symbol: SolBookSnapshot(
                _OBSERVED_MS,
                (SolBookLevel(99.9, 2.0, 1),),
                (SolBookLevel(100.1, 2.0, 1),),
                100.0,
                20.0,
                2.0,
                2.0,
                0.0,
            )
            for symbol in _SYMBOLS
        }

    runner = MultiAssetObserverRunner(
        symbols=_SYMBOLS,
        expected_provider_symbols=_EXPECTED,
        intent_poller=poller,
        book_source=books,
        telemetry=telemetry,
        stop_file=tmp_path / "STOP",
        now_fn=lambda: next(clock),
        sleep_fn=lambda _seconds: None,
        poll_seconds=15.0,
        signal_stop_requested=lambda: False,
    )

    runner.run(max_polls=1)

    assert poller.observed_at == [after_book]


def test_observer_fails_fast_when_initial_provider_coverage_is_incomplete(
    tmp_path: Path,
) -> None:
    """Missing one provider/coin setup is a technical parity failure."""
    incomplete = tuple(_evaluation(*pair) for pair in sorted(_EXPECTED)[:-1])
    runner, _poller, telemetry = _runner(tmp_path, _poll(evaluations=incomplete))

    with pytest.raises(MultiAssetObserverRunnerError, match="readiness coverage"):
        runner.run(max_polls=1)

    assert telemetry.events == ["configuration", "market_books"]


def test_observer_fails_fast_when_initial_candle_coverage_is_incomplete(
    tmp_path: Path,
) -> None:
    """The chart and strategy cannot silently omit an enabled symbol."""
    poll = _poll()
    incomplete = CohortIntentPoll(
        poll.intents,
        poll.reference_prices,
        poll.source_withheld,
        {key: value for key, value in poll.market_bars.items() if key != "HYPE"},
        poll.evaluations,
    )
    runner, _poller, telemetry = _runner(tmp_path, incomplete)

    with pytest.raises(MultiAssetObserverRunnerError, match="market coverage"):
        runner.run(max_polls=1)

    assert telemetry.events == ["configuration", "market_books"]

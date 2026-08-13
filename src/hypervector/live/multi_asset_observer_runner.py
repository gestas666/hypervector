"""Continuous no-submit runner for production multi-asset signal collectors."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
import math
from pathlib import Path
import time
from typing import Protocol

from hyperliquid.utils.error import ClientError, ServerError  # type: ignore[import-untyped]
from requests import RequestException

from hypervector.live.bidirectional_intents import (
    IntentRoutingReport,
    StrategyIntent,
    WithheldIntent,
)
from hypervector.live.multi_asset_intent_poller import (
    CohortIntentPoll,
    CohortMarketBar,
)
from hypervector.live.multi_asset_market_bars import TransientCohortMarketDataError
from hypervector.live.multi_asset_signal_source import ProviderEvaluation
from hypervector.live.cohort_operator_commands import CohortProfileSettings
from hypervector.live.hyperliquid_protocol import SolBookSnapshot
from hypervector.live.multi_asset_operator_runtime import (
    ObserverProfileCommandProcessor,
    OperatorCommandSourceProtocol,
)
from hypervector.live.transient_transport import transient_read_failure_reason

ProviderSymbol = tuple[str, str]


class ObserverIntentPollerProtocol(Protocol):
    """Causal production collector surface consumed by the observer."""

    def activate(self, activation_time_ms: int) -> None:
        """Set the causal boundary after which decisions may be emitted."""
        ...

    def poll(self, observed_at: datetime) -> CohortIntentPoll:
        """Collect one production-equivalent market and decision snapshot."""
        ...


class ObserverTelemetryProtocol(Protocol):
    """Disarmed backend ledger projection consumed by the TUI."""

    def emit_configuration(self) -> None:
        """Persist the effective disarmed configuration identity."""
        ...

    def emit_market_bars(
        self,
        bars: Mapping[str, tuple[CohortMarketBar, ...]],
    ) -> None:
        """Persist causal completed-bar windows for every enabled symbol."""
        ...

    def emit_routing(
        self,
        intents: tuple[StrategyIntent, ...],
        report: IntentRoutingReport,
        evaluations: tuple[ProviderEvaluation, ...] = (),
    ) -> None:
        """Persist evaluated setups and explicitly withheld intents."""
        ...

    def emit_market_books(
        self,
        books: Mapping[str, SolBookSnapshot],
    ) -> None:
        """Persist current public venue depth for every enabled symbol."""
        ...

    def emit_canonical_regimes(
        self,
        evaluations: tuple[ProviderEvaluation, ...],
    ) -> None:
        """Persist independent canonical regimes without routing authority."""
        ...

    def emit_heartbeat(self) -> None:
        """Persist observer liveness without implying execution health."""
        ...

    def emit_poll_degraded(self, *, source: str, reason: str) -> None:
        """Persist one recoverable public-data failure."""
        ...


class MultiAssetObserverRunnerError(RuntimeError):
    """The disarmed observer cannot preserve its parity contract."""


class MultiAssetObserverRunner:
    """Publish current production decisions while withholding every order intent."""

    def __init__(
        self,
        *,
        symbols: tuple[str, ...],
        expected_provider_symbols: frozenset[ProviderSymbol],
        intent_poller: ObserverIntentPollerProtocol,
        book_source: Callable[[], Mapping[str, SolBookSnapshot]],
        telemetry: ObserverTelemetryProtocol,
        stop_file: Path,
        now_fn: Callable[[], datetime],
        sleep_fn: Callable[[float], None],
        poll_seconds: float,
        signal_stop_requested: Callable[[], bool],
        operator_commands: OperatorCommandSourceProtocol | None = None,
        profile_stage: Callable[[CohortProfileSettings], str] | None = None,
        monotonic_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        _validate_configuration(symbols, expected_provider_symbols, poll_seconds)
        self._symbols = symbols
        self._expected = expected_provider_symbols
        self._intent_poller = intent_poller
        self._book_source = book_source
        self._telemetry = telemetry
        self._stop_file = stop_file
        self._now_fn = now_fn
        self._sleep_fn = sleep_fn
        self._poll_seconds = poll_seconds
        self._signal_stop_requested = signal_stop_requested
        self._monotonic_fn = monotonic_fn
        if (operator_commands is None) != (profile_stage is None):
            raise ValueError("observer profile staging requires source and handler")
        self._profile_commands = (
            ObserverProfileCommandProcessor(
                source=operator_commands,
                telemetry=telemetry,
                stage=profile_stage,
            )
            if operator_commands is not None and profile_stage is not None
            else None
        )

    def run(self, *, max_polls: int | None = None) -> int:
        """Poll until operator stop or a bounded diagnostic completion."""
        _validate_max_polls(max_polls)
        if self._shutdown_requested():
            raise MultiAssetObserverRunnerError(
                "observer stop requested before startup"
            )
        activation = _aware(self._now_fn())
        self._intent_poller.activate(int(activation.timestamp() * 1_000))
        self._telemetry.emit_configuration()
        polls = 0
        while not self._shutdown_requested():
            cycle_started = self._monotonic_fn()
            try:
                self._poll_once(require_full_coverage=polls == 0)
            except TransientCohortMarketDataError as exc:
                self._telemetry.emit_poll_degraded(
                    source=exc.source,
                    reason=exc.reason,
                )
            polls += 1
            if max_polls is not None and polls >= max_polls:
                return polls
            if not self._shutdown_requested():
                elapsed = self._monotonic_fn() - cycle_started
                self._sleep_fn(max(0.0, self._poll_seconds - elapsed))
        return polls

    def _poll_once(self, *, require_full_coverage: bool) -> None:
        try:
            books = self._book_source()
        except (RequestException, ClientError, ServerError) as exc:
            reason = transient_read_failure_reason(exc)
            if reason is None:
                raise
            raise TransientCohortMarketDataError(
                source="hyperliquid_public_l2",
                reason=reason,
            ) from exc
        if set(books) != set(self._symbols):
            raise MultiAssetObserverRunnerError("public L2 coverage is incomplete")
        self._telemetry.emit_market_books(books)
        observed = _aware(self._now_fn())
        poll = self._intent_poller.poll(observed)
        _validate_poll(
            poll,
            self._symbols,
            self._expected,
            require_full_coverage=require_full_coverage,
        )
        report = _observe_only_report(poll)
        self._telemetry.emit_market_bars(poll.market_bars)
        if poll.regime_evaluations:
            self._telemetry.emit_canonical_regimes(poll.regime_evaluations)
        if self._profile_commands is not None:
            self._profile_commands.process()
        self._telemetry.emit_routing(poll.all_intents, report, poll.evaluations)
        self._telemetry.emit_heartbeat()

    def _shutdown_requested(self) -> bool:
        return self._stop_file.exists() or self._signal_stop_requested()


def _observe_only_report(poll: CohortIntentPoll) -> IntentRoutingReport:
    withheld = poll.source_withheld + tuple(
        WithheldIntent(intent, "observe_mode_no_execution") for intent in poll.intents
    )
    return IntentRoutingReport((), withheld)


def _validate_poll(
    poll: CohortIntentPoll,
    symbols: tuple[str, ...],
    expected: frozenset[ProviderSymbol],
    *,
    require_full_coverage: bool,
) -> None:
    symbol_set = set(symbols)
    if set(poll.reference_prices) != symbol_set:
        raise MultiAssetObserverRunnerError(
            "initial reference-price coverage is incomplete"
        )
    if set(poll.market_bars) != symbol_set or any(
        not poll.market_bars[symbol] for symbol in symbols
    ):
        raise MultiAssetObserverRunnerError("initial market coverage is incomplete")
    pairs = [(value.strategy_id, value.symbol) for value in poll.evaluations]
    if len(pairs) != len(set(pairs)):
        raise MultiAssetObserverRunnerError(
            "provider readiness coverage has duplicates"
        )
    actual = set(pairs)
    if not actual.issubset(expected):
        raise MultiAssetObserverRunnerError(
            "provider readiness contains an unknown pair"
        )
    if require_full_coverage and actual != expected:
        missing = sorted(expected.difference(actual))
        raise MultiAssetObserverRunnerError(
            f"initial provider readiness coverage is incomplete: {missing}"
        )


def _validate_configuration(
    symbols: tuple[str, ...],
    expected: frozenset[ProviderSymbol],
    poll_seconds: float,
) -> None:
    if not symbols or len(set(symbols)) != len(symbols):
        raise MultiAssetObserverRunnerError(
            "observer symbols must be unique and non-empty"
        )
    if not expected or {symbol for _, symbol in expected} != set(symbols):
        raise MultiAssetObserverRunnerError(
            "expected provider coverage must span every symbol"
        )
    if not math.isfinite(poll_seconds) or poll_seconds <= 0.0:
        raise MultiAssetObserverRunnerError("poll_seconds must be positive and finite")


def _validate_max_polls(value: int | None) -> None:
    if value is not None and (
        isinstance(value, bool) or not isinstance(value, int) or value <= 0
    ):
        raise MultiAssetObserverRunnerError("max_polls must be a positive integer")


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise MultiAssetObserverRunnerError("observer clock must be timezone-aware")
    return value

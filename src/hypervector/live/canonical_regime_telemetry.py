"""Non-executable canonical regime evidence for cohorts without Range execution."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import replace
from typing import Protocol

import pandas as pd

from hypervector.live.multi_asset_signal_source import (
    ProviderEvaluation,
    RangeDecisionBuilderProtocol,
    range_decision_evaluation,
)
from hypervector.live.sol_range_onset_controller import SolLiveDecision
from hypervector.live.sol_range_onset_decision_source import (
    build_completed_live_decisions,
)

CANONICAL_REGIME_TELEMETRY_STRATEGY = "canonical_regime_telemetry_v1"
LEGACY_CANONICAL_REGIME_STRATEGY = "range_onset_bidirectional_v1"
CANONICAL_REGIME_STRATEGIES = (
    CANONICAL_REGIME_TELEMETRY_STRATEGY,
    LEGACY_CANONICAL_REGIME_STRATEGY,
)
_SUPPORTED_SYMBOLS = frozenset(("BTC", "ETH", "SOL", "HYPE"))
_NON_ACTION_REASON = "telemetry_only_no_execution_authority"


class CanonicalRegimeCollectorProtocol(Protocol):
    """Causal telemetry-only regime collector consumed by the cohort poller."""

    def activate(self, activation_time_ms: int) -> None: ...

    def collect(
        self,
        bars: Mapping[tuple[str, str], pd.DataFrame],
        observed_at: pd.Timestamp,
    ) -> tuple[ProviderEvaluation, ...]: ...


class CanonicalRegimeTelemetryCollector:
    """Advance canonical completed-bar evidence without constructing intents."""

    def __init__(
        self,
        *,
        symbols: tuple[str, ...],
        legacy_execution_enabled: bool,
        legacy_execution_symbols: frozenset[str] = frozenset(),
        decision_builder: RangeDecisionBuilderProtocol = build_completed_live_decisions,
    ) -> None:
        if not symbols or len(set(symbols)) != len(symbols):
            raise ValueError("canonical regime symbols must be non-empty and unique")
        if any(not symbol.strip() for symbol in symbols):
            raise ValueError("canonical regime symbols must be non-empty")
        if not isinstance(legacy_execution_enabled, bool):
            raise ValueError("legacy_execution_enabled must be boolean")
        if not legacy_execution_symbols.issubset(symbols):
            raise ValueError("legacy execution symbols must belong to canonical scope")
        self._symbols = (
            ()
            if legacy_execution_enabled
            else tuple(
                symbol for symbol in symbols if symbol not in legacy_execution_symbols
            )
        )
        self._decision_builder = decision_builder
        self._boundaries: dict[str, int] | None = None

    def activate(self, activation_time_ms: int) -> None:
        """Establish a strict no-retro-observation boundary for every symbol."""
        if self._boundaries is not None:
            raise ValueError("canonical regime collector is already active")
        if (
            isinstance(activation_time_ms, bool)
            or not isinstance(activation_time_ms, int)
            or activation_time_ms < 0
        ):
            raise ValueError("activation_time_ms must be a nonnegative integer")
        self._boundaries = {symbol: activation_time_ms for symbol in self._symbols}

    def collect(
        self,
        bars: Mapping[tuple[str, str], pd.DataFrame],
        observed_at: pd.Timestamp,
    ) -> tuple[ProviderEvaluation, ...]:
        """Return unseen telemetry-only evaluations in chronological order."""
        if self._boundaries is None:
            raise ValueError("canonical regime collector is not active")
        observed_ms = _observed_ms(observed_at)
        output: list[ProviderEvaluation] = []
        for symbol in self._symbols:
            source = bars.get((symbol, "1m"))
            if source is None:
                raise ValueError(f"canonical regime bars missing for {symbol}/1m")
            prior = self._boundaries[symbol]
            decisions = self._decision_builder(
                source,
                observed_at=observed_at,
                after_decision_time_ms=prior,
            )
            _validate_decisions(decisions, prior, observed_ms, symbol)
            output.extend(_telemetry_evaluation(value, symbol) for value in decisions)
            if decisions:
                self._boundaries[symbol] = decisions[-1].decision_time_ms
        return tuple(sorted(output, key=lambda value: value.decision_time_ms))


def canonical_regime_symbols(symbols: Iterable[str]) -> tuple[str, ...]:
    """Return symbols compatible with the continuous exact-cadence detector."""
    return tuple(symbol for symbol in symbols if symbol in _SUPPORTED_SYMBOLS)


def latest_canonical_evaluation(
    evaluations: Iterable[ProviderEvaluation],
    symbol: str,
) -> ProviderEvaluation | None:
    """Return newest canonical evidence, preferring the independent identity."""
    candidates = [
        value
        for value in evaluations
        if value.symbol == symbol and value.strategy_id in CANONICAL_REGIME_STRATEGIES
    ]
    return max(
        candidates,
        key=lambda value: (
            value.decision_time_ms,
            value.strategy_id == CANONICAL_REGIME_TELEMETRY_STRATEGY,
        ),
        default=None,
    )


def latest_canonical_evaluation_at_or_before(
    evaluations: Iterable[ProviderEvaluation],
    symbol: str,
    decision_time_ms: int,
) -> ProviderEvaluation | None:
    """Return newest canonical evidence causally available to one decision."""
    if (
        isinstance(decision_time_ms, bool)
        or not isinstance(decision_time_ms, int)
        or decision_time_ms < 0
    ):
        raise ValueError("decision_time_ms must be a nonnegative integer")
    return latest_canonical_evaluation(
        (value for value in evaluations if value.decision_time_ms <= decision_time_ms),
        symbol,
    )


def _telemetry_evaluation(
    decision: SolLiveDecision,
    symbol: str,
) -> ProviderEvaluation:
    source = range_decision_evaluation(decision, symbol)
    return replace(
        source,
        strategy_id=CANONICAL_REGIME_TELEMETRY_STRATEGY,
        decision_action="regime_observation",
        eligible=False,
        reason="canonical_regime_observation",
        side=None,
        exit_sides=frozenset(),
        exit_reason=None,
        backend_non_action_reason=_NON_ACTION_REASON,
    )


def _validate_decisions(
    decisions: tuple[SolLiveDecision, ...],
    prior: int,
    observed_ms: int,
    symbol: str,
) -> None:
    times = tuple(value.decision_time_ms for value in decisions)
    if times != tuple(sorted(set(times))):
        raise ValueError(f"canonical regime decisions are unordered for {symbol}")
    if any(not prior < value <= observed_ms for value in times):
        raise ValueError(
            f"canonical regime decision lies outside boundary for {symbol}"
        )


def _observed_ms(observed_at: pd.Timestamp) -> int:
    if observed_at.tz is None:
        raise ValueError("canonical regime observed_at must be timezone-aware")
    return int(observed_at.timestamp() * 1_000)

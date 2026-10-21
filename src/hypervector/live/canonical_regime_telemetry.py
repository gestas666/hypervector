"""Non-executable canonical regime evidence for every continuous cohort symbol."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Protocol

import pandas as pd

from hypervector.live.canonical_regime_decisions import (
    CanonicalRegimeDecision,
    build_completed_regime_decisions,
)
from hypervector.live.perp_venue_identity import parse_perp_venue_identity
from hypervector.live.provider_evaluation import ProviderEvaluation

if TYPE_CHECKING:
    from hypervector.live.multi_asset_live_config import MultiAssetLiveConfig

CANONICAL_REGIME_TELEMETRY_STRATEGY = "canonical_regime_telemetry_v1"
_NON_ACTION_REASON = "telemetry_only_no_execution_authority"


class CanonicalRegimeDecisionBuilderProtocol(Protocol):
    """Injectable completed-bar canonical regime builder."""

    def __call__(
        self,
        raw_bars: pd.DataFrame,
        *,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> tuple[CanonicalRegimeDecision, ...]: ...


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
        decision_builder: CanonicalRegimeDecisionBuilderProtocol = (
            build_completed_regime_decisions
        ),
    ) -> None:
        if len(set(symbols)) != len(symbols):
            raise ValueError("canonical regime symbols must be unique")
        if any(not symbol.strip() for symbol in symbols):
            raise ValueError("canonical regime symbols must be non-empty")
        self._symbols = tuple(symbols)
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
            output.extend(canonical_regime_evaluation(value, symbol) for value in decisions)
            if decisions:
                self._boundaries[symbol] = decisions[-1].decision_time_ms
        return tuple(sorted(output, key=lambda value: value.decision_time_ms))


def canonical_regime_symbols(symbols: Iterable[str]) -> tuple[str, ...]:
    """Return the continuously traded core perps the exact-cadence detector serves.

    Builder-deployed (HIP-3) markets can pause between sessions, so they get no
    canonical regime telemetry.
    """
    return tuple(
        symbol for symbol in symbols if not parse_perp_venue_identity(symbol).perp_dex
    )


def configured_canonical_regime_symbols(
    config: MultiAssetLiveConfig,
) -> tuple[str, ...]:
    """Return the configured symbols that receive descriptive canonical telemetry.

    Neither intents nor regime entry gates are added.
    """
    return canonical_regime_symbols(config.symbols)


def canonical_regime_evaluation(
    decision: CanonicalRegimeDecision,
    symbol: str,
) -> ProviderEvaluation:
    """Project one canonical decision into non-executable provider telemetry."""
    return ProviderEvaluation(
        strategy_id=CANONICAL_REGIME_TELEMETRY_STRATEGY,
        symbol=symbol,
        decision_time_ms=decision.decision_time_ms,
        reference_price=decision.reference_price,
        decision_action="regime_observation",
        eligible=False,
        reason="canonical_regime_observation",
        side=None,
        readiness=decision.readiness,
        primary_regime=decision.primary_regime,
        state_1m=decision.state_1m,
        state_5m=decision.state_5m,
        context_15m=decision.context_15m,
        confidence=decision.confidence,
        backend_non_action_reason=_NON_ACTION_REASON,
    )


def latest_canonical_evaluation(
    evaluations: Iterable[ProviderEvaluation],
    symbol: str,
) -> ProviderEvaluation | None:
    """Return the newest canonical evidence for one symbol."""
    candidates = [
        value
        for value in evaluations
        if value.symbol == symbol
        and value.strategy_id == CANONICAL_REGIME_TELEMETRY_STRATEGY
    ]
    return max(candidates, key=lambda value: value.decision_time_ms, default=None)


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


def _validate_decisions(
    decisions: tuple[CanonicalRegimeDecision, ...],
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

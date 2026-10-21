"""Telemetry-only canonical regime collection independent of execution routes."""

from __future__ import annotations

import pandas as pd

from hypervector.live.canonical_regime_decisions import CanonicalRegimeDecision
from hypervector.live.canonical_regime_telemetry import (
    CANONICAL_REGIME_TELEMETRY_STRATEGY,
    CanonicalRegimeTelemetryCollector,
    canonical_regime_symbols,
)
from hypervector.live.provider_readiness import SignalReadiness


def test_collector_emits_causal_regime_evidence_without_execution_authority() -> None:
    """Canonical evidence is a non-executable detector, never a route."""
    collector = CanonicalRegimeTelemetryCollector(
        symbols=("BTC",),
        decision_builder=_decisions,
    )
    collector.activate(1_000)

    observed = collector.collect(
        {("BTC", "1m"): pd.DataFrame()},
        pd.Timestamp("2026-08-11T04:01:05Z"),
    )

    assert len(observed) == 1
    evaluation = observed[0]
    assert evaluation.strategy_id == CANONICAL_REGIME_TELEMETRY_STRATEGY
    assert evaluation.decision_time_ms == 2_000
    assert evaluation.decision_action == "regime_observation"
    assert evaluation.eligible is False
    assert evaluation.side is None
    assert (
        evaluation.backend_non_action_reason == "telemetry_only_no_execution_authority"
    )
    assert (evaluation.state_1m, evaluation.state_5m, evaluation.context_15m) == (
        "TREND_UP",
        "TREND_UP",
        "RANGE",
    )


def test_collector_boundary_prevents_duplicate_or_retroactive_observations() -> None:
    """Activation and persisted in-memory boundaries expose each close once."""
    collector = CanonicalRegimeTelemetryCollector(
        symbols=("BTC",),
        decision_builder=_decisions,
    )
    collector.activate(1_500)
    bars = {("BTC", "1m"): pd.DataFrame()}
    observed = pd.Timestamp("2026-08-11T04:01:05Z")

    first = collector.collect(bars, observed)
    second = collector.collect(bars, observed)

    assert tuple(value.decision_time_ms for value in first) == (2_000,)
    assert second == ()


def test_canonical_scope_excludes_session_bounded_hip3_assets() -> None:
    """The exact-cadence detector serves every core perp but no HIP-3 market."""
    assert canonical_regime_symbols(
        ("BTC", "xyz:AAA", "ETH", "xyz:CCC", "SOL", "HYPE", "LTC")
    ) == ("BTC", "ETH", "SOL", "HYPE", "LTC")


def test_collector_with_no_continuous_symbols_emits_nothing() -> None:
    """A HIP-3-only cohort still builds a poller with an empty canonical scope."""
    collector = CanonicalRegimeTelemetryCollector(symbols=(), decision_builder=_decisions)
    collector.activate(1_000)

    assert collector.collect({}, pd.Timestamp("2026-08-11T04:01:05Z")) == ()


def _decisions(
    raw_bars: pd.DataFrame,
    *,
    observed_at: pd.Timestamp,
    after_decision_time_ms: int | None,
) -> tuple[CanonicalRegimeDecision, ...]:
    del raw_bars, observed_at
    rows = (_decision(1_000), _decision(2_000))
    boundary = after_decision_time_ms if after_decision_time_ms is not None else -1
    return tuple(row for row in rows if row.decision_time_ms > boundary)


def _decision(decision_time_ms: int) -> CanonicalRegimeDecision:
    readiness = SignalReadiness(
        side="long",
        conditions_met=1,
        conditions_required=1,
        blockers=(),
        indicators=("5m TREND_UP",),
        metrics={"structural_direction": "long"},
    )
    return CanonicalRegimeDecision(
        decision_time_ms=decision_time_ms,
        reference_price=100.0,
        primary_regime="TREND_UP",
        state_1m="TREND_UP",
        state_5m="TREND_UP",
        context_15m="RANGE",
        confidence=0.7,
        structural_direction="long",
        readiness=readiness,
    )

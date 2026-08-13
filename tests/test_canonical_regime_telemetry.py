"""Telemetry-only canonical regime collection independent of execution routes."""

from __future__ import annotations

import pandas as pd

from hypervector.live.canonical_regime_telemetry import (
    CANONICAL_REGIME_TELEMETRY_STRATEGY,
    CanonicalRegimeTelemetryCollector,
    canonical_regime_symbols,
)
from hypervector.live.provider_readiness import SignalReadiness
from hypervector.live.sol_range_onset_controller import SolLiveDecision


def test_collector_emits_causal_regime_evidence_without_execution_authority() -> None:
    """A retired Range route must leave a non-executable canonical detector."""
    collector = CanonicalRegimeTelemetryCollector(
        symbols=("BTC",),
        legacy_execution_enabled=False,
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
        legacy_execution_enabled=False,
        decision_builder=_decisions,
    )
    collector.activate(1_500)
    bars = {("BTC", "1m"): pd.DataFrame()}
    observed = pd.Timestamp("2026-08-11T04:01:05Z")

    first = collector.collect(bars, observed)
    second = collector.collect(bars, observed)

    assert tuple(value.decision_time_ms for value in first) == (2_000,)
    assert second == ()


def test_collector_is_disabled_when_legacy_range_execution_is_configured() -> None:
    """Existing v35 Range telemetry must not be duplicated under a second ID."""
    collector = CanonicalRegimeTelemetryCollector(
        symbols=("BTC",),
        legacy_execution_enabled=True,
        decision_builder=_decisions,
    )
    collector.activate(1_000)

    assert (
        collector.collect(
            {("BTC", "1m"): pd.DataFrame()},
            pd.Timestamp("2026-08-11T04:01:05Z"),
        )
        == ()
    )


def test_collector_excludes_only_symbols_with_legacy_range_execution() -> None:
    """A partial Range roster must not suppress canonical states on other assets."""
    collector = CanonicalRegimeTelemetryCollector(
        symbols=("BTC", "ETH", "SOL", "HYPE"),
        legacy_execution_enabled=False,
        legacy_execution_symbols=frozenset(("ETH", "SOL")),
        decision_builder=_decisions,
    )
    collector.activate(1_000)
    bars = {(symbol, "1m"): pd.DataFrame() for symbol in ("BTC", "ETH", "SOL", "HYPE")}

    observed = collector.collect(bars, pd.Timestamp("2026-08-11T04:01:05Z"))

    assert tuple(value.symbol for value in observed) == ("BTC", "HYPE")


def test_canonical_scope_excludes_session_bounded_hip3_assets() -> None:
    """The exact-cadence crypto detector cannot ingest overnight HIP-3 gaps."""
    assert canonical_regime_symbols(
        ("BTC", "xyz:SP500", "ETH", "xyz:SNDK", "SOL", "HYPE")
    ) == ("BTC", "ETH", "SOL", "HYPE")


def _decisions(
    raw_bars: pd.DataFrame,
    *,
    observed_at: pd.Timestamp,
    after_decision_time_ms: int | None,
) -> tuple[SolLiveDecision, ...]:
    del raw_bars, observed_at
    rows = (_decision(1_000), _decision(2_000))
    boundary = after_decision_time_ms if after_decision_time_ms is not None else -1
    return tuple(row for row in rows if row.decision_time_ms > boundary)


def _decision(decision_time_ms: int) -> SolLiveDecision:
    readiness = SignalReadiness(
        side="long",
        conditions_met=2,
        conditions_required=3,
        blockers=("awaiting_hourly_sma_cross",),
        indicators=("5m TREND_UP",),
        metrics={"structural_direction": "long"},
    )
    return SolLiveDecision(
        decision_time_ms=decision_time_ms,
        reference_price=100.0,
        long_entry=True,
        short_entry=False,
        long_exit=False,
        short_exit=False,
        primary_regime="TREND_UP",
        state_1m="TREND_UP",
        state_5m="TREND_UP",
        context_15m="RANGE",
        confidence=0.7,
        structural_direction="long",
        regime_admitted=True,
        readiness=readiness,
    )

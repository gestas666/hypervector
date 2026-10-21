"""Causal contract tests for the ETH breakout transfer observer."""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd
import pytest

from hypervector.live.bidirectional_intents import StrategyIntent
from hypervector.live.eth_breakout_transfer_provider import (
    ETH_BREAKOUT_TRANSFER_STRATEGY,
    EthBreakoutTransferCollector,
)
from hypervector.live.provider_evaluation import IntentBatch, ProviderEvaluation
from hypervector.live.provider_readiness import SignalReadiness

_DECISION_MS = int(pd.Timestamp("2026-08-05T23:00:00Z").timestamp() * 1_000)
_CANONICAL_STRATEGY = "hype_breakout_onset_bidirectional_v1"


def _source(
    *,
    side: str = "long",
    prior_bbwp_min: float | None = 20.0,
    body_bps: float | None = -4.0,
    eligible: bool = True,
) -> ProviderEvaluation:
    metrics: dict[str, object] = {
        "entry_feature_status": "measured",
        "prior_bbwp_min_15m": prior_bbwp_min,
        "directional_bar_body_bps": body_bps,
    }
    return ProviderEvaluation(
        strategy_id=_CANONICAL_STRATEGY,
        symbol="ETH",
        decision_time_ms=_DECISION_MS,
        reference_price=1_900.0,
        decision_action=f"enter_{side}" if eligible else "hold",
        eligible=eligible,
        reason="breakout_onset_directional" if eligible else "5m_not_breakout",
        side=side,
        readiness=SignalReadiness(
            side=side,
            conditions_met=3 if eligible else 1,
            conditions_required=3,
            blockers=() if eligible else ("5m_not_breakout",),
            indicators=("CANONICAL TEST SOURCE",),
            metrics=metrics,
        ),
        trigger="5m_breakout_onset" if eligible else "none",
        primary_regime="BREAKOUT",
        state_1m="TREND_UP" if side == "long" else "TREND_DOWN",
        state_5m="BREAKOUT",
        context_15m="RANGE",
        confidence=0.72,
    )


def _canonical(
    evaluations: tuple[ProviderEvaluation, ...],
    *,
    fresh: bool = True,
) -> Callable[..., IntentBatch]:
    intents = (
        tuple(
            StrategyIntent(
                strategy_id=_CANONICAL_STRATEGY,
                symbol=row.symbol,
                side=row.side or "long",
                decision_time_ms=row.decision_time_ms,
                reference_price=row.reference_price,
                reason="canonical_test",
            )
            for row in evaluations
            if row.eligible
        )
        if fresh
        else ()
    )

    def collect(
        bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> IntentBatch:
        del bars, symbol, observed_at, after_decision_time_ms
        return IntentBatch(intents, _DECISION_MS, evaluations)

    return collect


def _collect(
    source: ProviderEvaluation,
    *,
    fresh: bool = True,
) -> IntentBatch:
    collector = EthBreakoutTransferCollector(
        canonical_collector=_canonical((source,), fresh=fresh)
    )
    return collector(
        pd.DataFrame(),
        symbol="ETH",
        observed_at=pd.Timestamp("2026-08-05T23:00:30Z"),
        after_decision_time_ms=_DECISION_MS - 60_000,
    )


@pytest.mark.parametrize("side", ["long", "short"])
def test_candidate_preserves_both_canonical_sides(side: str) -> None:
    """A qualifying fresh onset retains its original long or short side."""
    batch = _collect(_source(side=side))

    assert [(row.strategy_id, row.symbol, row.side) for row in batch.intents] == [
        (ETH_BREAKOUT_TRANSFER_STRATEGY, "ETH", side)
    ]
    evaluation = batch.evaluations[0]
    assert evaluation.eligible is True
    assert evaluation.reason == "eth_breakout_transfer_ready"
    assert evaluation.readiness.conditions_met == 3
    assert evaluation.readiness.conditions_required == 3
    assert evaluation.readiness.metrics["maximum_prior_bbwp_min_15m"] == 40.0
    assert evaluation.readiness.metrics["maximum_directional_body_bps"] == 0.0


@pytest.mark.parametrize(
    ("prior_bbwp_min", "body_bps", "blocker"),
    [
        (40.1, -1.0, "prior_compression_absent"),
        (20.0, 0.1, "directional_pullback_absent"),
    ],
)
def test_candidate_requires_compression_and_pullback(
    prior_bbwp_min: float,
    body_bps: float,
    blocker: str,
) -> None:
    """The frozen ETH entry conditions are conjunctive rather than advisory."""
    batch = _collect(_source(prior_bbwp_min=prior_bbwp_min, body_bps=body_bps))

    assert batch.intents == ()
    assert batch.evaluations[0].eligible is False
    assert blocker in batch.evaluations[0].readiness.blockers


def test_candidate_does_not_replay_a_startup_seed() -> None:
    """A qualifying historical evaluation cannot become a fresh candidate intent."""
    batch = _collect(_source(), fresh=False)

    assert batch.intents == ()
    assert batch.evaluations[0].eligible is False
    assert batch.evaluations[0].reason == "canonical_intent_not_fresh"


def test_candidate_rejects_unmeasured_entry_features() -> None:
    """Missing causal feature telemetry fails closed instead of using defaults."""
    batch = _collect(_source(prior_bbwp_min=None))

    assert batch.intents == ()
    assert batch.evaluations[0].reason == "entry_features_unavailable"


def test_candidate_supports_eth_only() -> None:
    """Cross-asset expansion requires a separately tested strategy identity."""
    collector = EthBreakoutTransferCollector(
        canonical_collector=_canonical((_source(),))
    )

    with pytest.raises(ValueError, match="supports ETH only"):
        collector(
            pd.DataFrame(),
            symbol="SOL",
            observed_at=pd.Timestamp("2026-08-05T23:00:30Z"),
            after_decision_time_ms=_DECISION_MS - 60_000,
        )


def test_executable_candidate_labels_its_entry_policy_authority() -> None:
    """A staged execution route cannot continue to describe its filters as inert."""
    collector = EthBreakoutTransferCollector(
        canonical_collector=_canonical((_source(),)),
        execution_enabled=True,
    )

    batch = collector(
        pd.DataFrame(),
        symbol="ETH",
        observed_at=pd.Timestamp("2026-08-05T23:00:30Z"),
        after_decision_time_ms=_DECISION_MS - 60_000,
    )

    readiness = batch.evaluations[0].readiness
    assert readiness.metrics["candidate_authority"] == "automatic_execution"
    assert readiness.metrics["entry_policy_authority"] == "automatic_execution"
    assert readiness.indicators[-1].endswith("[AUTOMATIC EXECUTION]")

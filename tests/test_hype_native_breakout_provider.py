"""Contract tests for the isolated HYPE-native breakout provider identity."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.live.bidirectional_intents import (
    BidirectionalIntentRouter,
    PositionState,
    StrategyCapability,
    StrategyIntent,
)
from hypervector.live.hype_breakout_cohort_provider import (
    HYPE_BREAKOUT_COHORT_STRATEGY,
)
from hypervector.live.hype_native_breakout_provider import (
    HYPE_NATIVE_BREAKOUT_LONG_STRATEGY,
    HYPE_NATIVE_BREAKOUT_STRATEGY,
    HypeNativeBreakoutOnsetCollector,
)
from hypervector.live.provider_evaluation import IntentBatch, ProviderEvaluation
from hypervector.live.provider_readiness import SignalReadiness

_DECISION_MS = 1_786_944_600_000


class _CanonicalCollector:
    """Return a frozen canonical batch and retain invocation evidence."""

    def __init__(self, batch: IntentBatch) -> None:
        self.batch = batch
        self.calls: list[str] = []

    def __call__(
        self,
        bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> IntentBatch:
        del bars, observed_at, after_decision_time_ms
        self.calls.append(symbol)
        return self.batch


def _readiness(side: str) -> SignalReadiness:
    return SignalReadiness(
        side=side,
        conditions_met=3,
        conditions_required=3,
        blockers=(),
        indicators=("5M BREAKOUT", "ONSET YES"),
        metrics={"breakout_onset": True},
    )


def _evaluation(
    side: str, *, strategy_id: str = HYPE_BREAKOUT_COHORT_STRATEGY
) -> ProviderEvaluation:
    return ProviderEvaluation(
        strategy_id=strategy_id,
        symbol="HYPE",
        decision_time_ms=_DECISION_MS,
        reference_price=40.0,
        decision_action=f"enter_{side}",
        eligible=True,
        reason="breakout_onset_directional",
        side=side,
        readiness=_readiness(side),
        trigger="5m_breakout_onset",
    )


def _intent(side: str) -> StrategyIntent:
    return StrategyIntent(
        strategy_id=HYPE_BREAKOUT_COHORT_STRATEGY,
        symbol="HYPE",
        side=side,
        decision_time_ms=_DECISION_MS,
        reference_price=40.0,
        reason=f"hype_5m_breakout_onset:{side}",
    )


def _collector(
    batch: IntentBatch,
) -> tuple[HypeNativeBreakoutOnsetCollector, _CanonicalCollector]:
    canonical = _CanonicalCollector(batch)
    return HypeNativeBreakoutOnsetCollector(canonical_collector=canonical), canonical


def test_native_identity_relabels_both_sides_without_changing_signal_evidence() -> None:
    """The new ID preserves every canonical field except strategy identity."""
    batch = IntentBatch(
        intents=(_intent("long"), _intent("short")),
        latest_decision_time_ms=_DECISION_MS,
        evaluations=(_evaluation("long"), _evaluation("short")),
    )
    collector, canonical = _collector(batch)

    result = collector(
        pd.DataFrame(),
        symbol="HYPE",
        observed_at=pd.Timestamp("2026-08-17T12:00:00Z"),
        after_decision_time_ms=0,
    )

    assert canonical.calls == ["HYPE"]
    assert HYPE_NATIVE_BREAKOUT_STRATEGY != HYPE_BREAKOUT_COHORT_STRATEGY
    assert {row.side for row in result.intents} == {"long", "short"}
    assert {row.strategy_id for row in result.intents} == {
        HYPE_NATIVE_BREAKOUT_STRATEGY
    }
    assert {row.strategy_id for row in result.evaluations} == {
        HYPE_NATIVE_BREAKOUT_STRATEGY
    }
    assert result.latest_decision_time_ms == batch.latest_decision_time_ms
    assert result.intents[0].reason == batch.intents[0].reason
    assert result.evaluations[0].readiness == batch.evaluations[0].readiness


def test_native_provider_rejects_every_non_hype_symbol_before_collection() -> None:
    """The restored route cannot repeat the unsupported cross-asset transfer."""
    collector, canonical = _collector(IntentBatch((), 0, ()))

    for symbol in ("BTC", "ETH", "SOL"):
        with pytest.raises(ValueError, match="HYPE-only"):
            collector(
                pd.DataFrame(),
                symbol=symbol,
                observed_at=pd.Timestamp("2026-08-17T12:00:00Z"),
                after_decision_time_ms=0,
            )

    assert canonical.calls == []


def test_native_provider_fails_closed_on_noncanonical_input_identity() -> None:
    """An aliased upstream provider cannot silently enter the new evidence cohort."""
    collector, _ = _collector(
        IntentBatch((), _DECISION_MS, (_evaluation("long", strategy_id="wrong"),))
    )

    with pytest.raises(ValueError, match="canonical HYPE breakout identity"):
        collector(
            pd.DataFrame(),
            symbol="HYPE",
            observed_at=pd.Timestamp("2026-08-17T12:00:00Z"),
            after_decision_time_ms=0,
        )


def test_opposite_native_onset_retains_close_before_reverse_semantics() -> None:
    """A fresh opposite onset closes the open HYPE side without reversing."""
    router = BidirectionalIntentRouter(
        (
            StrategyCapability(
                HYPE_NATIVE_BREAKOUT_STRATEGY,
                "HYPE",
                frozenset({"long", "short"}),
                40,
            ),
        ),
        maximum_positions=1,
    )
    opposite = _intent("short")
    routed = router.route(
        (
            StrategyIntent(
                strategy_id=HYPE_NATIVE_BREAKOUT_STRATEGY,
                symbol=opposite.symbol,
                side=opposite.side,
                decision_time_ms=opposite.decision_time_ms,
                reference_price=opposite.reference_price,
                reason=opposite.reason,
            ),
        ),
        positions={"HYPE": PositionState("HYPE", "long")},
    )

    assert [(row.action, row.side) for row in routed.actions] == [("close", "short")]
    assert routed.withheld == ()


def test_long_authority_turns_short_onset_into_exit_only_evidence() -> None:
    """The long challenger closes a long on short onset without opening short."""
    batch = IntentBatch(
        intents=(_intent("short"),),
        latest_decision_time_ms=_DECISION_MS,
        evaluations=(_evaluation("short"),),
    )
    canonical = _CanonicalCollector(batch)
    collector = HypeNativeBreakoutOnsetCollector(
        canonical_collector=canonical,
        strategy_id=HYPE_NATIVE_BREAKOUT_LONG_STRATEGY,
        entry_sides=frozenset({"long"}),
    )

    result = collector(
        pd.DataFrame(),
        symbol="HYPE",
        observed_at=pd.Timestamp("2026-08-17T12:00:00Z"),
        after_decision_time_ms=0,
    )

    assert result.intents == ()
    evaluation = result.evaluations[0]
    assert evaluation.strategy_id == HYPE_NATIVE_BREAKOUT_LONG_STRATEGY
    assert evaluation.eligible is False
    assert evaluation.decision_action == "close_long"
    assert evaluation.exit_sides == frozenset({"long"})
    assert evaluation.exit_reason == "opposite_native_onset"


def test_long_authority_preserves_canonical_long_entry() -> None:
    """Allowed native long onsets retain exact entry evidence under the new ID."""
    batch = IntentBatch(
        intents=(_intent("long"),),
        latest_decision_time_ms=_DECISION_MS,
        evaluations=(_evaluation("long"),),
    )
    collector = HypeNativeBreakoutOnsetCollector(
        canonical_collector=_CanonicalCollector(batch),
        strategy_id=HYPE_NATIVE_BREAKOUT_LONG_STRATEGY,
        entry_sides=frozenset({"long"}),
    )

    result = collector(
        pd.DataFrame(),
        symbol="HYPE",
        observed_at=pd.Timestamp("2026-08-17T12:00:00Z"),
        after_decision_time_ms=0,
    )

    assert [row.side for row in result.intents] == ["long"]
    assert result.evaluations[0].eligible is True

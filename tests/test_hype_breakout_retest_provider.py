"""Integration tests for the HYPE breakout-retest v2 provider."""

from __future__ import annotations

from collections.abc import Iterator

import pandas as pd

from hypervector.live.hype_breakout_retest_provider import (
    HYPE_BREAKOUT_RETEST_STRATEGY,
    HypeBreakoutRetestCollector,
)
from hypervector.live.provider_evaluation import IntentBatch, ProviderEvaluation
from hypervector.live.provider_readiness import SignalReadiness

_START = pd.Timestamp("2026-08-06T00:00:00Z")
_MINUTE_MS = 60_000


class _CanonicalCollector:
    def __init__(self, batches: tuple[IntentBatch, ...]) -> None:
        self._batches: Iterator[IntentBatch] = iter(batches)

    def __call__(
        self,
        bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> IntentBatch:
        del bars, symbol, observed_at, after_decision_time_ms
        return next(self._batches)


def _decision_ms(position: int) -> int:
    candle = _START + pd.Timedelta(minutes=position)
    return int((candle + pd.Timedelta(minutes=1)).timestamp() * 1_000)


def _evaluation(
    position: int,
    *,
    onset: bool,
    breakout_side: str,
    structural_side: str,
) -> ProviderEvaluation:
    readiness = SignalReadiness(
        side=structural_side,
        conditions_met=3 if onset else 1,
        conditions_required=3,
        blockers=() if onset else ("awaiting_new_5m_breakout_onset",),
        indicators=(
            "5M BREAKOUT",
            f"STRUCT {structural_side.upper()}",
        ),
        metrics={
            "breakout_onset": onset,
            "breakout_side": breakout_side,
            "breakout_side_relation": (
                "aligned" if breakout_side == structural_side else "opposed"
            ),
            "structural_direction": structural_side,
        },
    )
    return ProviderEvaluation(
        strategy_id="hype_breakout_onset_bidirectional_v1",
        symbol="HYPE",
        decision_time_ms=_decision_ms(position),
        reference_price=100.0,
        decision_action=f"enter_{structural_side}" if onset else "hold",
        eligible=onset,
        reason="breakout_onset_directional" if onset else "awaiting_new_onset",
        side=structural_side,
        readiness=readiness,
        trigger="5m_breakout_onset" if onset else "none",
        primary_regime="BREAKOUT",
        state_1m="TREND_DOWN",
        state_5m="BREAKOUT",
        context_15m="TREND_DOWN",
        confidence=0.70,
    )


def _batch(evaluation: ProviderEvaluation) -> IntentBatch:
    return IntentBatch((), evaluation.decision_time_ms, (evaluation,))


def _bars(
    *, confirmation: bool = True, fade_confirmation: bool = False
) -> pd.DataFrame:
    rows = 22
    timestamps = pd.date_range(_START, periods=rows, freq="1min")
    frame = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [100.3] * rows,
            "high": [100.4] * rows,
            "low": [100.1] * rows,
            "close": [100.2] * rows,
            "volume": [10.0] * rows,
        }
    )
    frame.loc[20, ["open", "high", "low", "close"]] = [100.3, 100.4, 99.8, 100.0]
    next_bar = [100.05, 100.12, 99.85, 99.90]
    if fade_confirmation:
        next_bar = [100.00, 100.25, 99.85, 100.20]
    if not confirmation:
        next_bar = [100.10, 100.30, 100.00, 100.25]
    frame.loc[21, ["open", "high", "low", "close"]] = next_bar
    return frame


def test_opposed_breakout_arms_structural_fade_without_immediate_entry() -> None:
    """An opposed onset arms the v1 structural fade without entering immediately."""
    onset = _evaluation(
        20,
        onset=True,
        breakout_side="short",
        structural_side="long",
    )
    collector = HypeBreakoutRetestCollector(
        canonical_collector=_CanonicalCollector((_batch(onset),))
    )

    batch = collector(
        _bars().iloc[:21],
        symbol="HYPE",
        observed_at=_START + pd.Timedelta(minutes=21),
        after_decision_time_ms=_decision_ms(19),
    )

    assert batch.intents == ()
    evaluation = batch.evaluations[0]
    assert evaluation.strategy_id == HYPE_BREAKOUT_RETEST_STRATEGY
    assert evaluation.side == "long"
    assert evaluation.eligible is False
    assert evaluation.reason == "awaiting_failed_breakout_reclaim"
    assert evaluation.readiness.metrics["entry_mode"] == "fade"
    assert evaluation.readiness.metrics["entry_policy_state"] == "armed"
    assert evaluation.readiness.metrics["breakout_side_authority"] == (
        "continuation_or_fade_reference"
    )
    assert evaluation.readiness.metrics["structural_direction_authority"] == (
        "execution_for_fade"
    )
    assert evaluation.readiness.metrics["retest_boundary_price"] == 100.1


def test_confirmed_failed_breakout_emits_one_v2_long_fade_intent() -> None:
    """A completed bullish reclaim confirms the opposed structural long fade."""
    onset = _evaluation(
        20,
        onset=True,
        breakout_side="short",
        structural_side="long",
    )
    confirmation = _evaluation(
        21,
        onset=False,
        breakout_side="short",
        structural_side="long",
    )
    collector = HypeBreakoutRetestCollector(
        canonical_collector=_CanonicalCollector((_batch(onset), _batch(confirmation)))
    )
    collector(
        _bars(fade_confirmation=True).iloc[:21],
        symbol="HYPE",
        observed_at=_START + pd.Timedelta(minutes=21),
        after_decision_time_ms=_decision_ms(19),
    )

    batch = collector(
        _bars(fade_confirmation=True),
        symbol="HYPE",
        observed_at=_START + pd.Timedelta(minutes=22),
        after_decision_time_ms=_decision_ms(20),
    )

    assert [(intent.strategy_id, intent.side) for intent in batch.intents] == [
        (HYPE_BREAKOUT_RETEST_STRATEGY, "long")
    ]
    assert batch.intents[0].decision_time_ms == _decision_ms(21)
    evaluation = batch.evaluations[0]
    assert evaluation.eligible is True
    assert evaluation.reason == "failed_breakout_reclaim_confirmed"
    assert evaluation.readiness.metrics["entry_mode"] == "fade"
    assert evaluation.readiness.metrics["entry_policy_state"] == "confirmed"
    assert evaluation.readiness.metrics["retest_age_bars"] == 1


def test_nonconfirming_reversal_remains_pending_without_intent() -> None:
    """A failed first retest cannot leak the canonical immediate intent."""
    onset = _evaluation(
        20,
        onset=True,
        breakout_side="short",
        structural_side="short",
    )
    reversal = _evaluation(
        21,
        onset=False,
        breakout_side="short",
        structural_side="short",
    )
    collector = HypeBreakoutRetestCollector(
        canonical_collector=_CanonicalCollector((_batch(onset), _batch(reversal)))
    )
    collector(
        _bars(confirmation=False).iloc[:21],
        symbol="HYPE",
        observed_at=_START + pd.Timedelta(minutes=21),
        after_decision_time_ms=_decision_ms(19),
    )

    batch = collector(
        _bars(confirmation=False),
        symbol="HYPE",
        observed_at=_START + pd.Timedelta(minutes=22),
        after_decision_time_ms=_decision_ms(20),
    )

    assert batch.intents == ()
    assert batch.evaluations[0].reason == "awaiting_breakout_retest"
    assert batch.evaluations[0].readiness.metrics["entry_policy_state"] == "pending"

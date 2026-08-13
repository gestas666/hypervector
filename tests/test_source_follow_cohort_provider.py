"""Causal cohort adapter tests for measured bidirectional source-follow."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from hypervector.live.source_follow_cohort_provider import (
    SourceFollowCohortCollector,
)
from hypervector.regime.source_follow_runtime import (
    FiveMinuteBar,
    SourceFollowRuntime,
    SourceRegimeLabel,
)
from hypervector.regime.source_follow_session import SourceFollowSessionSignal


class _SequenceClassifier:
    def __init__(self, labels: tuple[tuple[str, str | None, float], ...]) -> None:
        self._labels = iter(labels)

    def classify(self, bar: FiveMinuteBar) -> SourceRegimeLabel:
        primary, secondary, confidence = next(self._labels)
        return SourceRegimeLabel(
            label_time_utc=bar.timestamp_utc,
            primary=primary,
            secondary=secondary,
            confidence=confidence,
        )


def _bars() -> pd.DataFrame:
    timestamps = pd.date_range("2026-08-02T12:00:00Z", periods=15, freq="1min")
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [100.0] * 15,
            "high": [100.2] * 15,
            "low": [100.0] * 15,
            "close": [100.1] * 15,
            "volume": [10.0] * 15,
        }
    )


def _collector() -> SourceFollowCohortCollector:
    runtime = SourceFollowRuntime(
        _SequenceClassifier(
            (
                ("TREND_DOWN", None, 0.80),
                ("TREND_DOWN", None, 0.82),
                ("TREND_UP", None, 0.85),
            )
        ),
        minimum_confidence=0.70,
        minimum_range_bps=12.0,
        maximum_range_bps=100.0,
        direction_mode="trend_bidirectional",
    )
    return SourceFollowCohortCollector(
        SourceFollowSessionSignal(runtime),
        minimum_confidence=0.70,
        minimum_range_bps=12.0,
        maximum_range_bps=100.0,
    )


def test_source_follow_cohort_emits_only_fresh_bidirectional_onset() -> None:
    """A fresh completed 5m trend onset becomes one attributed cohort intent."""
    after = int(datetime(2026, 8, 2, 12, 10, tzinfo=UTC).timestamp() * 1_000)

    batch = _collector()(
        _bars(),
        symbol="BTC",
        observed_at=pd.Timestamp("2026-08-02T12:16:00Z"),
        after_decision_time_ms=after,
    )

    assert [(intent.side, intent.decision_time_ms) for intent in batch.intents] == [
        ("long", int(datetime(2026, 8, 2, 12, 15, tzinfo=UTC).timestamp() * 1_000))
    ]
    evaluation = batch.evaluations[0]
    assert evaluation.strategy_id == ("hypervelocity_source_follow_bidirectional_5m_v1")
    assert evaluation.primary_regime == "TREND_UP"
    assert evaluation.eligible is True
    assert evaluation.readiness.conditions_met == 3
    assert evaluation.readiness.conditions_required == 3
    assert evaluation.readiness.blockers == ()


def test_source_follow_startup_seed_is_visible_but_not_retroactive() -> None:
    """The latest historical setup can seed telemetry without becoming an intent."""
    collector = _collector()
    activation = int(datetime(2026, 8, 2, 12, 16, tzinfo=UTC).timestamp() * 1_000)
    first = collector(
        _bars(),
        symbol="BTC",
        observed_at=pd.Timestamp("2026-08-02T12:16:00Z"),
        after_decision_time_ms=activation,
    )
    seed = collector(
        _bars(),
        symbol="BTC",
        observed_at=pd.Timestamp("2026-08-02T12:16:00Z"),
        after_decision_time_ms=activation - 6 * 60 * 1_000,
    )

    assert first.intents == ()
    assert first.evaluations == ()
    assert seed.intents == ()
    assert len(seed.evaluations) == 1
    assert seed.evaluations[0].decision_time_ms < activation

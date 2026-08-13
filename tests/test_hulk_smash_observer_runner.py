from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from hypervector.live.hulk_smash_live_decisions import HulkSmashLiveDecision
from hypervector.live.hulk_smash_observer_runner import HulkSmashObserverRunner


class FakeObserver:
    def __init__(self) -> None:
        self.started = False
        self.history: tuple[HulkSmashLiveDecision, ...] = ()
        self.decisions: list[HulkSmashLiveDecision] = []
        self.polls = 0

    def start(self) -> None:
        self.started = True

    def record_history(self, decisions: tuple[HulkSmashLiveDecision, ...]) -> None:
        self.history = decisions

    def process(self, decision: HulkSmashLiveDecision) -> None:
        self.decisions.append(decision)

    def poll_market(self) -> None:
        self.polls += 1


def test_observer_runner_primes_history_without_executing_it(tmp_path: Path) -> None:
    observer = FakeObserver()
    now_values = iter(
        [
            datetime(2026, 8, 1, 1, 30, tzinfo=UTC),
            datetime(2026, 8, 1, 2, 0, tzinfo=UTC),
        ]
    )
    runner = HulkSmashObserverRunner(
        observer=observer,
        stop_file=tmp_path / "STOP",
        fetch_bars=lambda *args: pd.DataFrame({"timestamp": []}),
        build_decisions=_fake_builder,
        now_fn=lambda: next(now_values),
        sleep_fn=lambda _: None,
        poll_seconds=1.0,
        lookback_days=14,
    )

    polls = runner.run(max_polls=2)

    assert polls == 2
    assert observer.started is True
    assert len(observer.history) == 2
    assert [decision.decision_time_ms for decision in observer.decisions] == [3]
    assert observer.polls == 2


def test_observer_runner_reuses_full_frozen_lookback_for_refreshes(
    tmp_path: Path,
) -> None:
    fetch_days: list[int] = []
    now_values = iter(
        [
            datetime(2026, 8, 1, 1, 30, tzinfo=UTC),
            datetime(2026, 8, 1, 2, 0, tzinfo=UTC),
        ]
    )

    def fetch(_symbol: str, _timeframe: str, days: int) -> pd.DataFrame:
        fetch_days.append(days)
        return pd.DataFrame({"timestamp": []})

    runner = HulkSmashObserverRunner(
        observer=FakeObserver(),
        stop_file=tmp_path / "STOP",
        fetch_bars=fetch,
        build_decisions=_fake_builder,
        now_fn=lambda: next(now_values),
        sleep_fn=lambda _: None,
        poll_seconds=1.0,
        lookback_days=14,
    )

    runner.run(max_polls=2)

    assert fetch_days == [14, 14]


def _fake_builder(
    bars: pd.DataFrame,
    *,
    observed_at: pd.Timestamp,
    after_decision_time_ms: int | None,
) -> tuple[HulkSmashLiveDecision, ...]:
    del bars, observed_at
    decisions = (_decision(1), _decision(2), _decision(3))
    if after_decision_time_ms is None:
        return decisions[:2]
    return tuple(
        item for item in decisions if item.decision_time_ms > after_decision_time_ms
    )


def _decision(time_ms: int) -> HulkSmashLiveDecision:
    return HulkSmashLiveDecision(
        decision_time_ms=time_ms,
        bar_open_at=pd.Timestamp("2026-08-01T00:00:00Z"),
        reference_price=100.0,
        open_price=100.0,
        high_price=101.0,
        low_price=99.0,
        volume=1.0,
        candidate="none",
        score=0,
        minimum_score=7,
        trigger="none",
        evidence=(),
        stop_anchor=None,
        entry_eligible=False,
        reason="no_trigger",
    )

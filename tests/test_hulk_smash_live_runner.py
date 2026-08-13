from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from hypervector.live.hulk_smash_live_decisions import HulkSmashLiveDecision
from hypervector.live.hulk_smash_live_models import (
    HulkSmashLiveSnapshot,
    HulkSmashLiveState,
)
from hypervector.live.hulk_smash_live_runner import (
    HulkSmashLiveRunner,
    HulkSmashLiveRunnerError,
)


class FakeEngine:
    def __init__(self, state: HulkSmashLiveState = HulkSmashLiveState.FLAT) -> None:
        self._snapshot = HulkSmashLiveSnapshot(state=state)
        self.calls: list[tuple[str, object]] = []

    @property
    def snapshot(self) -> HulkSmashLiveSnapshot:
        return self._snapshot

    def start(self) -> HulkSmashLiveSnapshot:
        self.calls.append(("start", None))
        return self._snapshot

    def record_history(self, decisions: tuple[HulkSmashLiveDecision, ...]) -> None:
        self.calls.append(("history", decisions))

    def record_strategy_decision(self, decision: HulkSmashLiveDecision) -> None:
        self.calls.append(("decision", decision))

    def enter(self, decision: HulkSmashLiveDecision) -> HulkSmashLiveSnapshot:
        self.calls.append(("enter", decision))
        self._snapshot = HulkSmashLiveSnapshot(state=HulkSmashLiveState.OPEN)
        return self._snapshot

    def poll_market(self) -> HulkSmashLiveSnapshot:
        self.calls.append(("poll", None))
        return self._snapshot

    def stop(self, reason: str) -> HulkSmashLiveSnapshot:
        self.calls.append(("stop", reason))
        self._snapshot = HulkSmashLiveSnapshot(state=HulkSmashLiveState.STOPPED)
        return self._snapshot


class FailingPollEngine(FakeEngine):
    def __init__(self, failure: BaseException) -> None:
        super().__init__()
        self._failure = failure

    def poll_market(self) -> HulkSmashLiveSnapshot:
        self.calls.append(("poll", None))
        raise self._failure


def test_live_runner_warms_without_entry_then_routes_only_fresh_signal(
    tmp_path: Path,
) -> None:
    history = (_decision(0, eligible=True),)
    fresh = _decision(1, eligible=True)
    engine = FakeEngine()
    builder = _Builder(history, (fresh,))
    runner = _runner(tmp_path, engine, builder)

    assert runner.run(max_polls=1) == 1

    names = [name for name, _ in engine.calls]
    assert names == ["start", "history", "poll", "decision", "enter", "stop"]
    assert engine.calls[1][1] == history
    assert engine.calls[-1] == ("stop", "bounded_run_complete")


def test_live_runner_records_but_does_not_route_signal_while_position_open(
    tmp_path: Path,
) -> None:
    engine = FakeEngine(HulkSmashLiveState.OPEN)
    runner = _runner(
        tmp_path,
        engine,
        _Builder((_decision(0),), (_decision(1, eligible=True),)),
    )

    runner.run(max_polls=1)

    assert any(name == "decision" for name, _ in engine.calls)
    assert not any(name == "enter" for name, _ in engine.calls)


def test_live_runner_refuses_existing_stop_file_before_engine_start(
    tmp_path: Path,
) -> None:
    engine = FakeEngine()
    stop_file = tmp_path / "STOP"
    stop_file.write_text("stop", encoding="utf-8")
    runner = _runner(
        tmp_path,
        engine,
        _Builder((_decision(0),), ()),
        stop_file=stop_file,
    )

    with pytest.raises(HulkSmashLiveRunnerError, match="stop file already exists"):
        runner.run()

    assert not engine.calls


def test_live_runner_rejects_non_increasing_fresh_decisions(tmp_path: Path) -> None:
    engine = FakeEngine()
    duplicate = _decision(0, eligible=True)
    runner = _runner(
        tmp_path,
        engine,
        _Builder((_decision(0),), (duplicate,)),
    )

    with pytest.raises(HulkSmashLiveRunnerError, match="strictly increasing"):
        runner.run(max_polls=1)

    assert not any(name == "decision" for name, _ in engine.calls)


def test_live_runner_stops_routing_when_engine_is_faulted(tmp_path: Path) -> None:
    engine = FakeEngine(HulkSmashLiveState.FAULTED)
    runner = _runner(
        tmp_path,
        engine,
        _Builder((_decision(0),), (_decision(1, eligible=True),)),
    )

    with pytest.raises(HulkSmashLiveRunnerError, match="FAULTED"):
        runner.run(max_polls=1)

    assert not any(name in {"decision", "enter"} for name, _ in engine.calls)


def test_live_runner_reuses_full_frozen_lookback_for_refreshes(
    tmp_path: Path,
) -> None:
    fetch_days: list[int] = []

    def fetch(_symbol: str, _timeframe: str, days: int) -> pd.DataFrame:
        fetch_days.append(days)
        return pd.DataFrame()

    engine = FakeEngine()
    runner = HulkSmashLiveRunner(
        engine=engine,
        stop_file=tmp_path / "STOP",
        fetch_bars=fetch,
        build_decisions=_Builder((_decision(0),), ()),
        now_fn=lambda: datetime(2026, 8, 1, 12, tzinfo=UTC),
        sleep_fn=lambda _: None,
        poll_seconds=5.0,
        lookback_days=14,
        maximum_entry_delay_seconds=7_200,
        signal_stop_requested=lambda: False,
    )

    runner.run(max_polls=1)

    assert fetch_days == [14, 14]


def test_live_runner_does_not_refetch_before_next_30m_decision(
    tmp_path: Path,
) -> None:
    fetch_days: list[int] = []

    def fetch(_symbol: str, _timeframe: str, days: int) -> pd.DataFrame:
        fetch_days.append(days)
        return pd.DataFrame()

    history = (_decision(3),)
    runner = HulkSmashLiveRunner(
        engine=FakeEngine(),
        stop_file=tmp_path / "STOP",
        fetch_bars=fetch,
        build_decisions=_Builder(history, ()),
        now_fn=lambda: datetime(2026, 8, 1, 12, 0, 1, tzinfo=UTC),
        sleep_fn=lambda _: None,
        poll_seconds=5.0,
        lookback_days=14,
        maximum_entry_delay_seconds=7_200,
        signal_stop_requested=lambda: False,
    )

    runner.run(max_polls=1)

    assert history[0].decision_time_ms == 1_785_585_600_000
    assert fetch_days == [14]


def test_live_runner_records_stop_after_operable_runtime_failure(
    tmp_path: Path,
) -> None:
    engine = FailingPollEngine(RuntimeError("injected poll failure"))
    runner = _runner(tmp_path, engine, _Builder((_decision(0),), ()))

    with pytest.raises(RuntimeError, match="injected poll failure"):
        runner.run(max_polls=1)

    assert engine.calls[-1] == ("stop", "runtime_failure")


def test_live_runner_records_stop_after_operator_interrupt(tmp_path: Path) -> None:
    engine = FailingPollEngine(KeyboardInterrupt())
    runner = _runner(tmp_path, engine, _Builder((_decision(0),), ()))

    with pytest.raises(KeyboardInterrupt):
        runner.run(max_polls=1)

    assert engine.calls[-1] == ("stop", "operator_interrupt")


def test_live_runner_journals_but_does_not_execute_stale_signal(
    tmp_path: Path,
) -> None:
    engine = FakeEngine()
    runner = HulkSmashLiveRunner(
        engine=engine,
        stop_file=tmp_path / "STOP",
        fetch_bars=lambda _symbol, _timeframe, _days: pd.DataFrame(),
        build_decisions=_Builder(
            (_decision(0),),
            (_decision(1, eligible=True),),
        ),
        now_fn=lambda: datetime(2026, 8, 1, 12, tzinfo=UTC),
        sleep_fn=lambda _: None,
        poll_seconds=5.0,
        lookback_days=14,
        maximum_entry_delay_seconds=60,
        signal_stop_requested=lambda: False,
    )

    runner.run(max_polls=1)

    recorded = next(payload for name, payload in engine.calls if name == "decision")
    assert isinstance(recorded, HulkSmashLiveDecision)
    assert recorded.entry_eligible is False
    assert recorded.reason == "stale_decision"
    assert not any(name == "enter" for name, _ in engine.calls)


def test_live_runner_refuses_future_completed_bar_decision(tmp_path: Path) -> None:
    engine = FakeEngine()
    runner = HulkSmashLiveRunner(
        engine=engine,
        stop_file=tmp_path / "STOP",
        fetch_bars=lambda _symbol, _timeframe, _days: pd.DataFrame(),
        build_decisions=_Builder(
            (_decision(0),),
            (_decision(5, eligible=True),),
        ),
        now_fn=lambda: datetime(2026, 8, 1, 12, tzinfo=UTC),
        sleep_fn=lambda _: None,
        poll_seconds=5.0,
        lookback_days=14,
        maximum_entry_delay_seconds=60,
        signal_stop_requested=lambda: False,
    )

    with pytest.raises(HulkSmashLiveRunnerError, match="future"):
        runner.run(max_polls=1)

    assert not any(name in {"decision", "enter"} for name, _ in engine.calls)


def test_live_runner_defers_signal_stop_until_entry_is_protected(
    tmp_path: Path,
) -> None:
    stop_requested = [False]

    class StopDuringEntryEngine(FakeEngine):
        def enter(self, decision: HulkSmashLiveDecision) -> HulkSmashLiveSnapshot:
            snapshot = super().enter(decision)
            stop_requested[0] = True
            return snapshot

    engine = StopDuringEntryEngine()
    runner = HulkSmashLiveRunner(
        engine=engine,
        stop_file=tmp_path / "STOP",
        fetch_bars=lambda _symbol, _timeframe, _days: pd.DataFrame(),
        build_decisions=_Builder(
            (_decision(0),),
            (_decision(3, eligible=True),),
        ),
        now_fn=lambda: datetime(2026, 8, 1, 12, tzinfo=UTC),
        sleep_fn=lambda _: pytest.fail("signal stop must not sleep"),
        poll_seconds=5.0,
        lookback_days=14,
        maximum_entry_delay_seconds=60,
        signal_stop_requested=lambda: stop_requested[0],
    )

    assert runner.run() == 1
    assert engine.calls[-1] == ("stop", "operator_signal")


def test_live_runner_refuses_signal_received_during_public_warmup(
    tmp_path: Path,
) -> None:
    stop_requested = [False]
    engine = FakeEngine()

    def fetch(_symbol: str, _timeframe: str, _days: int) -> pd.DataFrame:
        stop_requested[0] = True
        return pd.DataFrame()

    runner = HulkSmashLiveRunner(
        engine=engine,
        stop_file=tmp_path / "STOP",
        fetch_bars=fetch,
        build_decisions=_Builder((_decision(0),), ()),
        now_fn=lambda: datetime(2026, 8, 1, 12, tzinfo=UTC),
        sleep_fn=lambda _: None,
        poll_seconds=5.0,
        lookback_days=14,
        maximum_entry_delay_seconds=60,
        signal_stop_requested=lambda: stop_requested[0],
    )

    with pytest.raises(HulkSmashLiveRunnerError, match="during warmup"):
        runner.run()

    assert engine.calls == []


class _Builder:
    def __init__(
        self,
        history: tuple[HulkSmashLiveDecision, ...],
        fresh: tuple[HulkSmashLiveDecision, ...],
    ) -> None:
        self._history = history
        self._fresh = fresh

    def __call__(
        self,
        bars: pd.DataFrame,
        *,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> tuple[HulkSmashLiveDecision, ...]:
        del bars, observed_at
        return self._history if after_decision_time_ms is None else self._fresh


def _runner(
    tmp_path: Path,
    engine: FakeEngine,
    builder: _Builder,
    *,
    stop_file: Path | None = None,
) -> HulkSmashLiveRunner:
    return HulkSmashLiveRunner(
        engine=engine,
        stop_file=stop_file or tmp_path / "STOP",
        fetch_bars=lambda symbol, timeframe, days: pd.DataFrame(),
        build_decisions=builder,
        now_fn=lambda: datetime(2026, 8, 1, 12, tzinfo=UTC),
        sleep_fn=lambda _: None,
        poll_seconds=5.0,
        lookback_days=14,
        maximum_entry_delay_seconds=7_200,
        signal_stop_requested=lambda: False,
    )


def _decision(index: int, *, eligible: bool = False) -> HulkSmashLiveDecision:
    opened = pd.Timestamp("2026-08-01T10:00:00Z") + pd.Timedelta(minutes=30 * index)
    return HulkSmashLiveDecision(
        decision_time_ms=int((opened + pd.Timedelta(minutes=30)).timestamp() * 1_000),
        bar_open_at=opened,
        reference_price=100.0,
        open_price=100.2,
        high_price=100.5,
        low_price=99.8,
        volume=10.0,
        candidate="hulk_rebuilt_expansion_v1",
        score=8,
        minimum_score=7,
        trigger="squeeze_release",
        evidence=("squeeze_release", "adx_usable"),
        stop_anchor=100.5,
        entry_eligible=eligible,
        reason="eligible" if eligible else "score_below_7",
    )

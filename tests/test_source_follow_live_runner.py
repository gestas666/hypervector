"""Causal completed-bar tests for the BTC source-follow live runner."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

from hypervector.live.source_follow_live_engine import (
    SourceFollowLiveSnapshot,
    SourceFollowLiveState,
)
from hypervector.live.source_follow_live_runner import SourceFollowLiveRunner
from hypervector.regime.source_follow_runtime import (
    FiveMinuteBar,
    SourceFollowDecision,
)


class _Engine:
    def __init__(self) -> None:
        self.started = False
        self.decisions: list[SourceFollowDecision | None] = []
        self.history: tuple[SourceFollowDecision, ...] = ()

    def start(self) -> SourceFollowLiveSnapshot:
        self.started = True
        return SourceFollowLiveSnapshot(SourceFollowLiveState.FLAT)

    def process(
        self, decision: SourceFollowDecision | None
    ) -> SourceFollowLiveSnapshot:
        self.decisions.append(decision)
        return SourceFollowLiveSnapshot(SourceFollowLiveState.FLAT)

    def record_history(self, decisions: tuple[SourceFollowDecision, ...]) -> None:
        self.history = decisions


class _Runtime:
    def __init__(self) -> None:
        self.bars: list[FiveMinuteBar] = []

    def update(self, bar: FiveMinuteBar) -> SourceFollowDecision:
        self.bars.append(bar)
        return SourceFollowDecision(
            label_time_utc=bar.timestamp_utc,
            available_at_utc=bar.timestamp_utc + timedelta(minutes=5),
            primary="TREND_DOWN",
            secondary=None,
            confidence=0.82,
            primary_onset=True,
            source_event=True,
            signal_range_bps=18.0,
            entry_eligible=True,
            entry_direction="short",
            maximum_hold_seconds=86_400.0,
            exclusion_reason=None,
            bar_open=bar.open,
            bar_high=bar.high,
            bar_low=bar.low,
            bar_close=bar.close,
            bar_volume=bar.volume,
        )


class _Fetcher:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, symbol: str, timeframe: str, lookback_days: int) -> pd.DataFrame:
        self.calls += 1
        periods = 1 if self.calls == 1 else 2
        stamps = pd.date_range("2026-07-31T12:00:00Z", periods=periods, freq="5min")
        return pd.DataFrame(
            {
                "timestamp": stamps,
                "open": [100.0] * periods,
                "high": [100.2] * periods,
                "low": [99.8] * periods,
                "close": [100.0] * periods,
                "volume": [10.0] * periods,
            }
        )


def _runner(
    tmp_path: Path, observed: datetime
) -> tuple[SourceFollowLiveRunner, _Engine]:
    engine = _Engine()
    runner = SourceFollowLiveRunner(
        engine=engine,
        runtime=_Runtime(),
        fetch_bars=_Fetcher(),
        stop_file=tmp_path / "STOP",
        now_fn=lambda: observed,
        sleep_fn=lambda _: None,
        poll_seconds=5.0,
        lookback_days=30,
        entry_pulse_seconds=60.0,
    )
    return runner, engine


def test_runner_ignores_warmup_and_emits_only_new_completed_bar(tmp_path: Path) -> None:
    """Historical warmup labels cannot become live entry decisions."""
    runner, engine = _runner(tmp_path, datetime(2026, 7, 31, 12, 10, tzinfo=UTC))

    assert runner.run(max_polls=1) == 1

    assert engine.started
    assert len(engine.history) == 1
    assert engine.history[0].label_time_utc == datetime(2026, 7, 31, 12, 0, tzinfo=UTC)
    assert engine.decisions[0] is None
    decision = engine.decisions[1]
    assert decision is not None
    assert decision.label_time_utc == datetime(2026, 7, 31, 12, 5, tzinfo=UTC)
    assert decision.entry_eligible


def test_runner_caps_display_history_without_processing_it(tmp_path: Path) -> None:
    """Only 90 warm bars are published and none enter the execution path."""
    observed = datetime(2026, 7, 31, 12, 10, tzinfo=UTC)

    def fetch(symbol: str, timeframe: str, lookback_days: int) -> pd.DataFrame:
        periods = 95 if lookback_days > 2 else 96
        stamps = pd.date_range("2026-07-31T04:10:00Z", periods=periods, freq="5min")
        return pd.DataFrame(
            {
                "timestamp": stamps,
                "open": [100.0] * periods,
                "high": [100.2] * periods,
                "low": [99.8] * periods,
                "close": [100.0] * periods,
                "volume": [10.0] * periods,
            }
        )

    engine = _Engine()
    runner = SourceFollowLiveRunner(
        engine=engine,
        runtime=_Runtime(),
        fetch_bars=fetch,
        stop_file=tmp_path / "STOP",
        now_fn=lambda: observed,
        sleep_fn=lambda _: None,
        poll_seconds=5.0,
        lookback_days=30,
        entry_pulse_seconds=60.0,
    )

    runner.run(max_polls=1)

    assert len(engine.history) == 90
    assert len(engine.decisions) == 2
    assert engine.decisions[0] is None
    assert engine.decisions[1] is not None


def test_runner_records_but_disarms_a_missed_entry_pulse(tmp_path: Path) -> None:
    """A delayed poll cannot chase an onset after its one-minute pulse."""
    runner, engine = _runner(tmp_path, datetime(2026, 7, 31, 12, 12, tzinfo=UTC))

    runner.run(max_polls=1)

    decision = engine.decisions[1]
    assert decision is not None
    assert not decision.entry_eligible
    assert decision.entry_direction is None
    assert decision.exclusion_reason == "entry_pulse_expired"


def test_runner_rechecks_freshness_after_reconciliation_and_fetch(
    tmp_path: Path,
) -> None:
    """Network work cannot consume the pulse while retaining stale authority."""
    times = iter(
        (
            datetime(2026, 7, 31, 12, 10, 10, tzinfo=UTC),
            datetime(2026, 7, 31, 12, 10, 10, tzinfo=UTC),
            datetime(2026, 7, 31, 12, 11, 5, tzinfo=UTC),
        )
    )
    engine = _Engine()
    runner = SourceFollowLiveRunner(
        engine=engine,
        runtime=_Runtime(),
        fetch_bars=_Fetcher(),
        stop_file=tmp_path / "STOP",
        now_fn=lambda: next(times),
        sleep_fn=lambda _: None,
        poll_seconds=5.0,
        lookback_days=30,
        entry_pulse_seconds=60.0,
    )

    runner.run(max_polls=1)

    decision = engine.decisions[1]
    assert decision is not None
    assert decision.entry_eligible is False
    assert decision.entry_direction is None
    assert decision.exclusion_reason == "entry_pulse_expired"


def test_runner_rechecks_operator_stop_before_submitting_a_decision(
    tmp_path: Path,
) -> None:
    """A stop requested during market-data work wins over a fresh signal."""
    stop_file = tmp_path / "STOP"
    delegate = _Fetcher()

    def fetch(symbol: str, timeframe: str, lookback_days: int) -> pd.DataFrame:
        frame = delegate(symbol, timeframe, lookback_days)
        if delegate.calls == 2:
            stop_file.touch()
        return frame

    engine = _Engine()
    observed = datetime(2026, 7, 31, 12, 10, 10, tzinfo=UTC)
    runner = SourceFollowLiveRunner(
        engine=engine,
        runtime=_Runtime(),
        fetch_bars=fetch,
        stop_file=stop_file,
        now_fn=lambda: observed,
        sleep_fn=lambda _: None,
        poll_seconds=5.0,
        lookback_days=30,
        entry_pulse_seconds=60.0,
    )

    runner.run(max_polls=1)

    assert engine.decisions == [None]

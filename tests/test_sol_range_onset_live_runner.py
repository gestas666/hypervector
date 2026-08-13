"""Continuous-loop tests for the explicitly armed SOL live runner."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from hypervector.live.hyperliquid_protocol import (
    SolAccountSnapshot,
    SolPositionSnapshot,
    SolReconciliationSnapshot,
)
from hypervector.live.sol_range_onset_controller import SolLiveDecision
from hypervector.live.sol_range_onset_runner import (
    SolLiveRunnerError,
    SolRangeOnsetLiveRunner,
)
from hypervector.live.sol_range_onset_state import SolLiveSnapshot, SolLiveState


def _decision(timestamp_ms: int) -> SolLiveDecision:
    return SolLiveDecision(
        timestamp_ms,
        73.1,
        False,
        False,
        False,
        False,
        "RANGE",
        "RANGE",
        "RANGE",
        "TREND_DOWN",
        0.6,
        "neutral",
        True,
    )


def _flat_venue() -> SolReconciliationSnapshot:
    position = SolPositionSnapshot(0.0, None, None, 0.0, 0.0, 0.0, None, None)
    account = SolAccountSnapshot(150.0, 150.0, 0.0, 0.0, position)
    return SolReconciliationSnapshot(account, (), ())


class _Engine:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.snapshot = SolLiveSnapshot(state=SolLiveState.FLAT)

    def start(self) -> SolLiveSnapshot:
        self.events.append("start")
        return self.snapshot

    def stop(self, reason: str) -> SolLiveSnapshot:
        self.events.append(f"stop:{reason}")
        return SolLiveSnapshot(state=SolLiveState.STOPPED, stop_reason=reason)

    def reconcile_telemetry(
        self,
        *,
        funding_start_time_ms: int,
        funding_end_time_ms: int,
    ) -> SolReconciliationSnapshot:
        self.events.append(f"reconcile:{funding_start_time_ms}:{funding_end_time_ms}")
        return _flat_venue()


class _Controller:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.decisions: list[SolLiveDecision] = []

    def process(self, decision: SolLiveDecision) -> SolLiveSnapshot:
        self.events.append("decision")
        self.decisions.append(decision)
        return SolLiveSnapshot(state=SolLiveState.FLAT)


def test_runner_excludes_historical_signals_and_reconciles_before_decision(
    tmp_path: Path,
) -> None:
    """Activation time is the first admissible decision boundary."""
    activation = datetime(2026, 7, 31, 12, 0, 30, tzinfo=timezone.utc)
    activation_ms = int(activation.timestamp() * 1_000)
    events: list[str] = []
    engine = _Engine(events)
    controller = _Controller(events)
    observed_after: list[int | None] = []

    def build(
        bars: pd.DataFrame,
        *,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> tuple[SolLiveDecision, ...]:
        del bars, observed_at
        observed_after.append(after_decision_time_ms)
        return (_decision(activation_ms + 30_000),)

    runner = SolRangeOnsetLiveRunner(
        engine=engine,
        controller=controller,
        stop_file=tmp_path / "STOP",
        fetch_bars=lambda _symbol, _timeframe, _days: pd.DataFrame({"x": [1]}),
        build_decisions=build,
        now_fn=lambda: activation,
        sleep_fn=lambda _: None,
        poll_seconds=15.0,
        lookback_days=5,
    )

    polls = runner.run(max_polls=1)

    assert polls == 1
    assert observed_after == [activation_ms]
    assert len(controller.decisions) == 1
    assert events[0] == "start"
    assert events[1].startswith("reconcile:")
    assert events[2] == "decision"
    assert events[3] == "stop:bounded_run_complete"


def test_preexisting_stop_file_refuses_arming(tmp_path: Path) -> None:
    """A stale or intentional operator stop cannot be silently deleted."""
    stop_file = tmp_path / "STOP"
    stop_file.write_text("stop", encoding="utf-8")
    events: list[str] = []
    runner = SolRangeOnsetLiveRunner(
        engine=_Engine(events),
        controller=_Controller(events),
        stop_file=stop_file,
        fetch_bars=lambda _symbol, _timeframe, _days: pd.DataFrame({"x": [1]}),
        build_decisions=lambda *_args, **_kwargs: (),
        now_fn=lambda: datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc),
        sleep_fn=lambda _: None,
        poll_seconds=15.0,
        lookback_days=5,
    )

    with pytest.raises(SolLiveRunnerError, match="stop file already exists"):
        runner.run(max_polls=1)

    assert events == []

"""Continuous polling and clean-stop contracts for the Apex MM canary."""

from __future__ import annotations

from pathlib import Path

import pytest
from hyperliquid.utils.error import ClientError

from hypervector.live.apex_mm_live_models import ApexMMLiveSnapshot, ApexMMLiveState
from hypervector.live.apex_mm_live_runner import ApexMMLiveRunner, ApexMMLiveRunnerError


class _Engine:
    def __init__(
        self,
        process_state: ApexMMLiveState = ApexMMLiveState.QUOTING,
        start_state: ApexMMLiveState = ApexMMLiveState.QUOTING,
    ) -> None:
        self.process_state = process_state
        self.start_state = start_state
        self.starts = 0
        self.processes = 0
        self.shutdowns = 0
        self.cleanup_required = False

    def start(self) -> ApexMMLiveSnapshot:
        self.starts += 1
        self.cleanup_required = True
        return ApexMMLiveSnapshot(self.start_state)

    def process(self) -> ApexMMLiveSnapshot:
        self.processes += 1
        return ApexMMLiveSnapshot(self.process_state)

    def shutdown(self) -> ApexMMLiveSnapshot:
        self.shutdowns += 1
        self.cleanup_required = False
        return ApexMMLiveSnapshot(ApexMMLiveState.STOPPED)


class _RateLimitedProcessEngine(_Engine):
    def process(self) -> ApexMMLiveSnapshot:
        self.processes += 1
        if self.processes == 1:
            raise _client_error(429)
        return ApexMMLiveSnapshot(self.process_state)


class _RateLimitedShutdownEngine(_Engine):
    def shutdown(self) -> ApexMMLiveSnapshot:
        self.shutdowns += 1
        if self.shutdowns == 1:
            raise _client_error(429)
        self.cleanup_required = False
        return ApexMMLiveSnapshot(ApexMMLiveState.STOPPED)


class _RateLimitedStartEngine(_Engine):
    def start(self) -> ApexMMLiveSnapshot:
        self.starts += 1
        self.cleanup_required = True
        raise _client_error(429)


class _RejectedProcessEngine(_Engine):
    def process(self) -> ApexMMLiveSnapshot:
        self.processes += 1
        raise _client_error(422)


def test_runner_refuses_preexisting_stop_file_without_starting(tmp_path: Path) -> None:
    stop = tmp_path / "STOP"
    stop.touch()
    engine = _Engine()
    runner = ApexMMLiveRunner(
        engine=engine, stop_file=stop, sleep_fn=lambda _: None, poll_seconds=1.0
    )

    with pytest.raises(ApexMMLiveRunnerError, match="already exists"):
        runner.run()

    assert engine.starts == 0


def test_bounded_runner_always_executes_verified_shutdown(tmp_path: Path) -> None:
    engine = _Engine()
    runner = ApexMMLiveRunner(
        engine=engine,
        stop_file=tmp_path / "STOP",
        sleep_fn=lambda _: None,
        poll_seconds=1.0,
    )

    assert runner.run(max_polls=2) == 2
    assert engine.starts == 1
    assert engine.processes == 2
    assert engine.shutdowns == 1


def test_poll_cadence_subtracts_processing_time_from_one_second_period(
    tmp_path: Path,
) -> None:
    engine = _Engine()
    sleeps: list[float] = []
    monotonic_values = iter((0.0, 0.3, 1.0))
    runner = ApexMMLiveRunner(
        engine=engine,
        stop_file=tmp_path / "STOP",
        sleep_fn=sleeps.append,
        poll_seconds=1.0,
        monotonic_fn=lambda: next(monotonic_values),
    )

    assert runner.run(max_polls=2) == 2
    assert sleeps == [pytest.approx(0.7)]


def test_fault_stops_polling_and_runs_shutdown(tmp_path: Path) -> None:
    engine = _Engine(ApexMMLiveState.FAULT)
    runner = ApexMMLiveRunner(
        engine=engine,
        stop_file=tmp_path / "STOP",
        sleep_fn=lambda _: None,
        poll_seconds=1.0,
    )

    assert runner.run(max_polls=10) == 1
    assert engine.shutdowns == 1


def test_startup_fault_never_enters_the_polling_loop(tmp_path: Path) -> None:
    engine = _Engine(start_state=ApexMMLiveState.FAULT)
    runner = ApexMMLiveRunner(
        engine=engine,
        stop_file=tmp_path / "STOP",
        sleep_fn=lambda _: None,
        poll_seconds=1.0,
    )

    assert runner.run(max_polls=10) == 0
    assert engine.processes == 0
    assert engine.shutdowns == 1


def test_stop_created_during_poll_causes_clean_shutdown(tmp_path: Path) -> None:
    stop = tmp_path / "STOP"
    engine = _Engine()

    def request_stop(_: float) -> None:
        stop.touch()

    runner = ApexMMLiveRunner(
        engine=engine,
        stop_file=stop,
        sleep_fn=request_stop,
        poll_seconds=1.0,
    )

    assert runner.run() == 1
    assert engine.shutdowns == 1


def test_rate_limited_process_retries_without_abandoning_quotes(tmp_path: Path) -> None:
    sleeps: list[float] = []
    engine = _RateLimitedProcessEngine()
    runner = ApexMMLiveRunner(
        engine=engine,
        stop_file=tmp_path / "STOP",
        sleep_fn=sleeps.append,
        poll_seconds=1.0,
    )

    assert runner.run(max_polls=1) == 1
    assert engine.processes == 2
    assert engine.shutdowns == 1
    assert sleeps == [10.0]


def test_rate_limited_shutdown_retries_until_cleanup_is_verified(
    tmp_path: Path,
) -> None:
    sleeps: list[float] = []
    engine = _RateLimitedShutdownEngine()
    runner = ApexMMLiveRunner(
        engine=engine,
        stop_file=tmp_path / "STOP",
        sleep_fn=sleeps.append,
        poll_seconds=1.0,
    )

    assert runner.run(max_polls=1) == 1
    assert engine.shutdowns == 2
    assert not engine.cleanup_required
    assert sleeps == [10.0]


def test_rate_limited_start_still_executes_verified_shutdown(tmp_path: Path) -> None:
    engine = _RateLimitedStartEngine()
    runner = ApexMMLiveRunner(
        engine=engine,
        stop_file=tmp_path / "STOP",
        sleep_fn=lambda _: None,
        poll_seconds=1.0,
    )

    with pytest.raises(ClientError) as caught:
        runner.run(max_polls=1)

    assert caught.value.status_code == 429
    assert engine.shutdowns == 1
    assert not engine.cleanup_required


def test_non_rate_limit_client_error_propagates_and_cleans_up(tmp_path: Path) -> None:
    engine = _RejectedProcessEngine()
    runner = ApexMMLiveRunner(
        engine=engine,
        stop_file=tmp_path / "STOP",
        sleep_fn=lambda _: None,
        poll_seconds=1.0,
    )

    with pytest.raises(ClientError) as caught:
        runner.run(max_polls=1)

    assert caught.value.status_code == 422
    assert engine.processes == 1
    assert engine.shutdowns == 1


def _client_error(status_code: int) -> ClientError:
    return ClientError(status_code, None, "injected", {})

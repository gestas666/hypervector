"""Normal observer termination is explicit and cannot hide a failed poll."""

from pathlib import Path
from datetime import UTC, datetime

import pytest

from test_multi_asset_observer_runner import _poll, _runner
from test_multi_asset_observer_audit import _observer_rows, _row, _RUN_ID
from hypervector.research.cohort_observer_audit import audit_cohort_observer_run
from hypervector.live.multi_asset_cohort_telemetry import MultiAssetCohortTelemetry
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.sol_range_onset_ledger import SolLiveLedger


def test_bounded_observer_publishes_stop_after_its_final_poll(tmp_path: Path) -> None:
    """A bounded diagnostic exit cannot leave running as its final heartbeat."""
    runner, _, telemetry = _runner(tmp_path, _poll())
    assert runner.run(max_polls=2) == 2
    assert telemetry.events[-2:] == ["heartbeat", "stopped:bounded_run_complete"]


@pytest.mark.parametrize("signal", [False, True])
def test_operator_stop_publishes_terminal_health(tmp_path: Path, signal: bool) -> None:
    """Both supported operator stop paths leave an explicit terminal event."""
    stopped = False

    def stop_on_sleep(_seconds: float) -> None:
        nonlocal stopped
        stopped = True
        if not signal:
            (tmp_path / "STOP").touch()

    runner, _, telemetry = _runner(
        tmp_path,
        _poll(),
        sleep_fn=stop_on_sleep,
        signal_stop_requested=lambda: signal and stopped,
    )
    assert runner.run() == 1
    assert telemetry.events[-2:] == ["heartbeat", "stopped:operator_stop"]


def test_unrecoverable_poll_does_not_claim_normal_stop(tmp_path: Path) -> None:
    """Normal-stop telemetry cannot replace or conceal an unrecoverable error."""
    runner, poller, telemetry = _runner(tmp_path, _poll())

    def fail(_observed: object) -> None:
        raise RuntimeError("terminal poll failure")

    poller.poll = fail  # type: ignore[method-assign, assignment]
    with pytest.raises(RuntimeError, match="terminal poll failure"):
        runner.run(max_polls=1)
    assert not any(event.startswith("stopped:") for event in telemetry.events)


def test_stop_telemetry_failure_is_propagated(tmp_path: Path) -> None:
    """Failure to record final health must remain a failed observer operation."""
    runner, _, telemetry = _runner(tmp_path, _poll())

    def fail(*, reason: str) -> None:
        raise OSError(f"could not record {reason}")

    telemetry.emit_stopped = fail  # type: ignore[method-assign]
    with pytest.raises(OSError, match="could not record bounded_run_complete"):
        runner.run(max_polls=1)


def _telemetry(tmp_path: Path) -> tuple[MultiAssetCohortTelemetry, SolLiveLedger]:
    config = load_multi_asset_live_config(
        "tests/fixtures/profiles/cohort_base.toml", mode="observe"
    )
    ledger = SolLiveLedger(
        path=tmp_path / "observe/decisions.jsonl",
        profile_id=config.profile_id,
        profile_fingerprint=config.profile_fingerprint,
        run_fingerprint=config.run_fingerprint,
        run_id="observer-stop-test",
        execution_mode="observe",
    )
    return MultiAssetCohortTelemetry(
        config=config, ledger=ledger, now_fn=lambda: datetime(2026, 9, 12, tzinfo=UTC)
    ), ledger


@pytest.mark.parametrize("reason", ["bounded_run_complete", "operator_stop"])
def test_stop_event_retains_disarmed_run_provenance(
    tmp_path: Path, reason: str
) -> None:
    """A real terminal ledger event retains the observer identity and no authority."""
    telemetry, ledger = _telemetry(tmp_path)
    telemetry.emit_stopped(reason=reason)
    (row,) = ledger.read_all()
    assert row["event_type"] == "runtime_stopped"
    assert row["payload"] == {"reason": reason}
    assert row["execution_mode"] == "observe"
    assert row["live_armed"] is False
    assert row["execution_authority"] == "none"
    assert row["run_id"] == "observer-stop-test"


def test_stop_event_rejects_unknown_reason(tmp_path: Path) -> None:
    """Unrecognized terminal reasons fail before emitting misleading health."""
    telemetry, ledger = _telemetry(tmp_path)
    with pytest.raises(ValueError, match="stop reason"):
        telemetry.emit_stopped(reason="unknown")
    assert ledger.read_all() == []


@pytest.mark.parametrize("signal", [False, True])
def test_preexisting_stop_cannot_claim_the_observer_started(
    tmp_path: Path, signal: bool
) -> None:
    """A pre-start stop fails before configuration, polling, or normal-exit evidence."""
    if not signal:
        (tmp_path / "STOP").touch()
    runner, poller, telemetry = _runner(
        tmp_path, _poll(), signal_stop_requested=lambda: signal
    )
    with pytest.raises(RuntimeError, match="stop requested before startup"):
        runner.run(max_polls=1)
    assert poller.activation_time_ms is None
    assert telemetry.events == []


def test_normal_stop_does_not_inflate_observer_polling_evidence(tmp_path: Path) -> None:
    """A real normal-exit event cannot become a successful market-data cycle."""
    telemetry, ledger = _telemetry(tmp_path)
    telemetry.emit_stopped(reason="operator_stop")
    (event,) = ledger.read_all()
    rows = _observer_rows()
    before = audit_cohort_observer_run(rows, run_id=_RUN_ID)["runtime"]
    rows.append(
        _row(
            len(rows) + 1,
            event["event_type"],
            event["payload"],
            "2026-08-01T12:31:00+00:00",
        )
    )
    after = audit_cohort_observer_run(rows, run_id=_RUN_ID)["runtime"]
    assert after == before

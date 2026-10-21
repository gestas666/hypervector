"""Adverse venue facts and execution failures cannot become successful deadline handling."""

from dataclasses import replace
from pathlib import Path

from multi_asset_live_runner_fixtures import venue_snapshot
import pytest
from test_cohort_degraded_deadlines import (
    FailingPoller,
    HARD_MS,
    NOW_MS,
    SOFT_MS,
    runner_fixture,
)

from hypervector.live.cohort_degraded_deadlines import reconciled_position_prices
from hypervector.live.multi_asset_live_runner_support import MultiAssetLiveRunnerError
from hypervector.live.multi_asset_market_bars import TransientCohortMarketDataError
from hypervector.live.asset_state import AssetLiveState


@pytest.mark.parametrize(
    "size, notional",
    [
        (float("nan"), 1),
        (float("inf"), 1),
        (float("-inf"), 1),
        (1, float("nan")),
        (1, float("inf")),
        (1, 0),
        (1, -1),
        (1e-300, 1e300),
        (1e300, 1e-300),
    ],
)
def test_invalid_native_price_facts_fail_explicitly(
    size: float, notional: float
) -> None:
    """A malformed or unrepresentable mark cannot reach the native close adapter."""
    venue = venue_snapshot(1)
    position = replace(venue.position, size_signed=size, position_value_usd=notional)
    venue = replace(venue, account=replace(venue.account, position=position))
    with pytest.raises(MultiAssetLiveRunnerError, match="reconciled position"):
        reconciled_position_prices(("BTC",), (venue,))


def test_flat_positions_do_not_acquire_fabricated_prices() -> None:
    """No zero, entry or stale candle price substitutes for a flat asset."""
    assert reconciled_position_prices(("BTC",), (venue_snapshot(0),)) == {}


def test_position_price_scope_must_match_exactly() -> None:
    """A mismatched namespace list cannot silently attach another asset's mark."""
    with pytest.raises(ValueError):
        reconciled_position_prices(("BTC", "ETH"), (venue_snapshot(1),))


@pytest.mark.parametrize("opened", [None, NOW_MS + 1])
def test_unconditional_scope_does_not_hide_invalid_open_clock(
    tmp_path: Path, opened: int | None
) -> None:
    """Filtering context-sensitive exits cannot suppress ownership validation."""
    runner, engine, _ = runner_fixture(
        tmp_path, age_ms=HARD_MS, side=-0.25, extension=True
    )
    engine.current = replace(engine.current, opened_at_ms=opened)
    runner.start(activation_time_ms=NOW_MS)
    with pytest.raises(MultiAssetLiveRunnerError, match="invalid opened_at_ms"):
        runner.poll_once()
    assert engine.exits == []


def test_unconditional_scope_preserves_nonopen_lifecycle(tmp_path: Path) -> None:
    """A stopped lifecycle cannot acquire automatic deadline authority."""
    runner, engine, telemetry = runner_fixture(
        tmp_path, age_ms=HARD_MS, side=-0.25, extension=True
    )
    engine.current = replace(engine.current, state=AssetLiveState.STOPPED)
    runner.start(activation_time_ms=NOW_MS)
    with pytest.raises(TransientCohortMarketDataError):
        runner.poll_once()
    assert engine.exits == [] and telemetry.maximum_hold_events == []


def test_missing_hard_contract_is_not_a_silent_extension(tmp_path: Path) -> None:
    """An adversarial invalid bound plan fails without authorizing a close."""
    runner, engine, _ = runner_fixture(
        tmp_path, age_ms=HARD_MS, side=-0.25, extension=True
    )
    assert engine.current.execution_plan is not None
    object.__setattr__(engine.current.execution_plan, "hard_maximum_hold_seconds", None)
    runner.start(activation_time_ms=NOW_MS)
    with pytest.raises(MultiAssetLiveRunnerError, match="lacks a hard maximum hold"):
        runner.poll_once()
    assert engine.exits == []


def test_repeated_data_failure_does_not_repeat_a_completed_close(
    tmp_path: Path,
) -> None:
    """A second failed acquisition reconciles flat and emits no duplicate action."""
    runner, engine, telemetry = runner_fixture(
        tmp_path, age_ms=HARD_MS, side=-0.25, extension=False
    )
    runner.start(activation_time_ms=NOW_MS)
    for _ in range(2):
        with pytest.raises(TransientCohortMarketDataError) as error:
            runner.poll_once()
        assert error.value is FailingPoller.failure
    assert (
        len(engine.exits)
        == len(telemetry.routings)
        == len(telemetry.maximum_hold_events)
        == 1
    )
    assert telemetry.heartbeats == 0


def test_fixed_position_before_deadline_remains_open(tmp_path: Path) -> None:
    """An acquisition outage cannot shorten the configured holding horizon."""
    runner, engine, telemetry = runner_fixture(
        tmp_path, age_ms=SOFT_MS - 1, side=-0.25, extension=False
    )
    runner.start(activation_time_ms=NOW_MS)
    with pytest.raises(TransientCohortMarketDataError):
        runner.poll_once()
    assert engine.snapshot.state is AssetLiveState.OPEN and engine.exits == []
    assert telemetry.maximum_hold_events == []


def test_close_failure_propagates_without_healthy_telemetry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An execution error takes precedence over the original strategy-data error."""
    runner, engine, telemetry = runner_fixture(
        tmp_path, age_ms=HARD_MS, side=-0.25, extension=False
    )
    failure = RuntimeError("offline close failure")

    def fail_close(*, mark_price: float, reason: str) -> None:
        """Stop at the explicit test execution failure."""
        raise failure

    monkeypatch.setattr(engine, "exit", fail_close)
    runner.start(activation_time_ms=NOW_MS)
    with pytest.raises(RuntimeError) as error:
        runner.poll_once()
    assert error.value is failure
    assert telemetry.heartbeats == 0 and telemetry.snapshots == []


def test_refresh_failure_prevents_close_and_propagates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The recovery read cannot reuse old venue exposure when its refresh fails."""
    runner, engine, telemetry = runner_fixture(
        tmp_path, age_ms=HARD_MS, side=-0.25, extension=False
    )
    original = engine.reconcile_telemetry
    failure = RuntimeError("offline refresh failure")

    def refresh(*, funding_start_time_ms: int, funding_end_time_ms: int) -> object:
        """Fail only the additional read following the acquisition outage."""
        if engine.reconciliations:
            raise failure
        return original(
            funding_start_time_ms=funding_start_time_ms,
            funding_end_time_ms=funding_end_time_ms,
        )

    monkeypatch.setattr(engine, "reconcile_telemetry", refresh)
    runner.start(activation_time_ms=NOW_MS)
    with pytest.raises(RuntimeError) as error:
        runner.poll_once()
    assert error.value is failure and engine.exits == []
    assert telemetry.heartbeats == 0 and telemetry.snapshots == []

"""Required deadline exits remain active during unrelated strategy-data failure."""

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from hyperliquid.utils.error import ServerError
from test_multi_asset_live_runner import (
    _Engine,
    _Poller,
    _SYMBOLS,
    _Telemetry,
    _contract,
    _router,
)

from hypervector.live.cohort_execution_plan import BoundExecutionPlan
from hypervector.live.hyperliquid_protocol import HyperliquidReconciliationSnapshot
from hypervector.live.multi_asset_intent_poller import CohortIntentPoll
from hypervector.live.multi_asset_live_runner import MultiAssetLiveRunner
from hypervector.live.multi_asset_market_bars import TransientCohortMarketDataError
from hypervector.live.asset_state import AssetLiveSnapshot, AssetLiveState

NOW = datetime(2026, 9, 13, 5, 30, tzinfo=UTC)
NOW_MS = int(NOW.timestamp() * 1_000)
SOFT_MS = 3_600_000
HARD_MS = 7_200_000
REFERENCE_PRICE = 101.0


class FailingPoller(_Poller):
    """Inject a classified acquisition failure after native reconciliation."""

    failure = TransientCohortMarketDataError(
        source="BTC_candles", reason="transport_timeout_retry_exhausted"
    )

    def poll(self, observed_at: datetime) -> CohortIntentPoll:
        """Fail without manufacturing provider evidence."""
        raise self.failure


class OwnedEngine(_Engine):
    """Retain an owned position and expose independent current position notional."""

    flatten_on_refresh = False

    def start(self) -> AssetLiveSnapshot:
        """Preserve the explicitly supplied recovered lifecycle."""
        return self.current

    def reconcile_telemetry(
        self, *, funding_start_time_ms: int, funding_end_time_ms: int
    ) -> HyperliquidReconciliationSnapshot:
        """Model a protective fill becoming visible only after acquisition fails."""
        if self.flatten_on_refresh and self.reconciliations:
            self.current = AssetLiveSnapshot(state=AssetLiveState.FLAT)
        venue = super().reconcile_telemetry(
            funding_start_time_ms=funding_start_time_ms,
            funding_end_time_ms=funding_end_time_ms,
        )
        position = replace(
            venue.position,
            position_value_usd=abs(self.current.position_size_signed) * REFERENCE_PRICE,
        )
        return replace(venue, account=replace(venue.account, position=position))


def runner_fixture(
    tmp_path: Path, *, age_ms: int, side: float, extension: bool, planless: bool = False
) -> tuple[MultiAssetLiveRunner, OwnedEngine, _Telemetry]:
    """Use the actual runner/controllers with declared offline native-engine doubles."""
    engines = {symbol: _Engine(symbol) for symbol in _SYMBOLS}
    owned = OwnedEngine("SOL")
    contract = _contract(maximum_hold_seconds=SOFT_MS // 1_000)
    if extension:
        contract = replace(
            contract,
            maximum_hold_policy="extend_while_regime_supported",
            hard_maximum_hold_seconds=HARD_MS // 1_000,
            maximum_hold_evidence_maximum_age_seconds=60,
        )
    plan: BoundExecutionPlan | None = (
        None if planless else contract.bind(strategy_id="test_trend_provider", stop_anchor=None)
    )
    owned.current = AssetLiveSnapshot(
        state=AssetLiveState.OPEN,
        entry_oid=91,
        stop_oid=92,
        position_size_signed=side,
        opened_at_ms=NOW_MS - age_ms,
        execution_plan=plan,
    )
    engines["SOL"] = owned
    telemetry = _Telemetry()
    runner = MultiAssetLiveRunner(
        symbols=_SYMBOLS,
        engines=engines,
        router=_router(),
        intent_poller=FailingPoller(()),
        telemetry=telemetry,
        stop_file=tmp_path / "STOP",
        now_fn=lambda: NOW,
        sleep_fn=lambda _: None,
        poll_seconds=15,
        signal_stop_requested=lambda: False,
        maximum_hold_seconds_by_symbol={s: SOFT_MS // 1_000 for s in _SYMBOLS},
        execution_contracts={"test_trend_provider": contract},
        maximum_entry_delay_ms_by_provider_symbol={
            ("test_trend_provider", s): 60_000 for s in _SYMBOLS
        },
        executable_provider_symbols=frozenset(("test_trend_provider", s) for s in _SYMBOLS),
    )
    return runner, owned, telemetry


@pytest.mark.parametrize("side", [-0.25, 0.25])
@pytest.mark.parametrize("age_ms", [SOFT_MS, SOFT_MS + 15 * SOFT_MS])
def test_failed_acquisition_executes_original_fixed_deadline(
    tmp_path: Path, side: float, age_ms: int
) -> None:
    """An overdue close uses reconciled notional/size and retains explicit degradation."""
    runner, engine, telemetry = runner_fixture(
        tmp_path, age_ms=age_ms, side=side, extension=False
    )
    runner.start(activation_time_ms=NOW_MS)
    with pytest.raises(TransientCohortMarketDataError) as error:
        runner.poll_once()
    assert error.value is FailingPoller.failure
    assert engine.exits == [(REFERENCE_PRICE, "maximum_hold_seconds")]
    assert engine.snapshot.state is AssetLiveState.FLAT
    assert telemetry.maximum_hold_events[0]["opened_at_ms"] == NOW_MS - age_ms
    assert len(engine.reconciliations) == 3
    assert len(telemetry.snapshots) == len(telemetry.funding_windows) == 1
    assert telemetry.heartbeats == 0 and telemetry.market_bars == []
    assert all(not engine.entries for engine in runner._engines.values())


@pytest.mark.parametrize(
    "age_ms, reason",
    [
        (SOFT_MS - 1, None),
        (SOFT_MS, None),
        (HARD_MS - 1, None),
        (HARD_MS, "hard_maximum_hold_seconds"),
        (HARD_MS + 1, "hard_maximum_hold_seconds"),
    ],
)
def test_data_failure_honors_only_unconditional_extension_deadline(
    tmp_path: Path, age_ms: int, reason: str | None
) -> None:
    """Missing fresh strategy context cannot invent a soft extension decision."""
    runner, engine, telemetry = runner_fixture(
        tmp_path, age_ms=age_ms, side=-0.25, extension=True
    )
    runner.start(activation_time_ms=NOW_MS)
    with pytest.raises(TransientCohortMarketDataError):
        runner.poll_once()
    assert engine.exits == ([] if reason is None else [(REFERENCE_PRICE, reason)])
    assert bool(telemetry.maximum_hold_events) == (reason is not None)
    assert telemetry.heartbeats == 0


def test_protection_observed_after_data_failure_prevents_duplicate_close(
    tmp_path: Path,
) -> None:
    """Refresh venue ownership after the outage before creating a timed action."""
    runner, engine, telemetry = runner_fixture(
        tmp_path, age_ms=HARD_MS, side=-0.25, extension=False
    )
    engine.flatten_on_refresh = True
    runner.start(activation_time_ms=NOW_MS)
    with pytest.raises(TransientCohortMarketDataError):
        runner.poll_once()
    assert engine.snapshot.state is AssetLiveState.FLAT
    assert engine.exits == [] and len(engine.reconciliations) == 2
    assert telemetry.maximum_hold_events == [] and telemetry.heartbeats == 0


def test_planless_recovery_uses_configured_fallback_hold(tmp_path: Path) -> None:
    """A legacy owned lifecycle retains its explicit configured holding limit."""
    runner, engine, _ = runner_fixture(
        tmp_path, age_ms=SOFT_MS, side=0.25, extension=False, planless=True
    )
    runner.start(activation_time_ms=NOW_MS)
    with pytest.raises(TransientCohortMarketDataError):
        runner.poll_once()
    assert engine.exits == [(REFERENCE_PRICE, "maximum_hold_seconds")]


def test_supervised_data_failure_reports_degraded_after_required_exit(
    tmp_path: Path,
) -> None:
    """The run loop records its source error while the deadline close remains effective."""
    runner, engine, telemetry = runner_fixture(
        tmp_path, age_ms=SOFT_MS, side=-0.25, extension=False
    )
    assert runner.run(max_polls=1) == 1
    assert engine.exits == [(REFERENCE_PRICE, "maximum_hold_seconds")]
    assert telemetry.degraded_polls == [
        ("BTC_candles", "transport_timeout_retry_exhausted")
    ]
    assert telemetry.heartbeats == 0


def test_failed_deadline_close_is_never_reported_as_a_degraded_poll(
    tmp_path: Path,
) -> None:
    """The unconditional deadline path submits orders inside the acquisition failure.

    `poll_with_deadlines` closes owned positions before re-raising the market-data
    error, so a transport failure on the close leaves the lifecycle mid-flight. The
    run loop must surface it instead of recording a degraded poll and continuing —
    this path exists precisely to protect a position while data is broken.
    """
    runner, owned, telemetry = runner_fixture(
        tmp_path, age_ms=SOFT_MS, side=-0.25, extension=False
    )
    attempted: list[tuple[float, str]] = []

    def failing_exit(
        *, mark_price: float, reason: str, **_kwargs: object
    ) -> AssetLiveSnapshot:
        attempted.append((mark_price, reason))
        raise ServerError(502, "Bad Gateway")

    owned.exit = failing_exit

    with pytest.raises(ServerError):
        runner.run(max_polls=1)

    assert attempted == [(REFERENCE_PRICE, "maximum_hold_seconds")]
    assert not telemetry.degraded_polls, (
        "a failed deadline close must not be recorded as a degraded poll"
    )

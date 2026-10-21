"""Failure injection after acknowledged fills, without network or venue orders."""

from dataclasses import replace
from pathlib import Path

import pytest
from requests import ConnectionError
from hyperliquid.utils.error import ClientError, ServerError

from hypervector.live.cohort_execution_plan import ProviderExecutionContract
from hypervector.live.hyperliquid_protocol import (
    HyperliquidOrderAck,
    HyperliquidOrderStatus,
    HyperliquidReconciliationSnapshot,
)
from hypervector.live.asset_engine import AssetLiveEngine
from hypervector.live.asset_engine_contract import AssetLiveEngineError
from hypervector.live.hyperliquid_parsing import HyperliquidAdapterError
from hypervector.live.asset_ledger import AssetLiveLedger, AssetLiveLedgerError
from hypervector.live.asset_state import AssetLiveState
from test_asset_live_engine import (
    FakeVenueAdapter,
    _now,
    _order,
    _runtime,
    _venue,
)

SENSITIVE_ERROR = "injected unavailable post-fill read with secret-value"
DECISION_MS = 1_785_495_600_123


def _failed_reader(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    permanent: bool = True,
    side: str = "long",
    failure: Exception | None = None,
) -> tuple[AssetLiveEngine, FakeVenueAdapter, AssetLiveLedger]:
    config, ledger = _runtime(tmp_path)
    size = 0.30 if side == "long" else -0.30
    stop = _order(
        202,
        size=abs(size),
        reduce_only=True,
        trigger=True,
        side="A" if size > 0 else "B",
    )
    adapter = FakeVenueAdapter([_venue(0.0), _venue(0.0), _venue(size, (stop,))])
    original = adapter.reconcile

    def reconcile() -> HyperliquidReconciliationSnapshot:
        operations = [name for name, _ in adapter.calls]
        if "submit_entry" in operations:
            if permanent or "place_protective_stop" not in operations:
                raise (
                    failure if failure is not None else ConnectionError(SENSITIVE_ERROR)
                )
        return original()

    monkeypatch.setattr(adapter, "reconcile", reconcile)
    engine = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=_now,
        sleep_fn=lambda _: None,
    )
    engine.start()
    return engine, adapter, ledger


@pytest.mark.parametrize("side", ["long", "short"])
def test_filled_entry_attempts_protection_when_subsequent_reads_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, side: str
) -> None:
    """A direct confirmed fill retains a stop attempt and restart evidence."""
    engine, adapter, ledger = _failed_reader(tmp_path, monkeypatch, side=side)
    with pytest.raises(ConnectionError, match="injected"):
        engine.enter(side=side, mark_price=73.0, decision_time_ms=DECISION_MS)
    stops = [value for name, value in adapter.calls if name == "place_protective_stop"]
    assert len(stops) == 1, "acknowledged fill lost its stop attempt to a read failure"
    assert stops[0]["position_size_signed"] == (0.30 if side == "long" else -0.30)
    assert engine.snapshot.state is AssetLiveState.PROTECTING
    assert engine.snapshot.entry_oid == 101
    assert engine.snapshot.opened_at_ms == DECISION_MS
    records = ledger.read_all()
    assert any(r["event_type"] == "stop_order" for r in records)
    failures = [
        r["payload"]
        for r in records
        if r["event_type"] == "entry_reconciliation_failure"
    ]
    assert len(failures) == 1
    assert failures[0]["recovery_action"] == "protect_acknowledged_fill"
    assert failures[0]["venue_snapshot_available"] is False
    assert "secret-value" not in ledger.path.read_text()
    assert not any(name == "close_position" for name, _ in adapter.calls)


@pytest.mark.parametrize("side", ["long", "short"])
def test_recovered_read_still_requires_full_protection_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, side: str
) -> None:
    """Once reads recover, complete verification may report OPEN."""
    engine, adapter, _ = _failed_reader(
        tmp_path, monkeypatch, side=side, permanent=False
    )
    result = engine.enter(side=side, mark_price=73.0, decision_time_ms=DECISION_MS)
    assert result.state is AssetLiveState.OPEN
    assert result.stop_oid == 202
    assert result.opened_at_ms == DECISION_MS
    assert [name for name, _ in adapter.calls].count("submit_entry") == 1
    assert [name for name, _ in adapter.calls].count("place_protective_stop") == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "resting"),
        ("status", "canceled"),
        ("filled_size", None),
        ("filled_size", 0.0),
        ("filled_size", float("nan")),
        ("filled_size", True),
        ("average_price", None),
        ("average_price", -1.0),
        ("average_price", float("inf")),
        ("recovered_after_transport_error", True),
        ("recovered_after_restart", True),
    ],
)
def test_unqualified_acknowledgement_cannot_supply_invented_exposure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str, value: object
) -> None:
    """Ambiguous or malformed acknowledgements do not become invented positions."""
    engine, adapter, ledger = _failed_reader(tmp_path, monkeypatch)
    adapter.entry_ack = replace(adapter.entry_ack, **{field: value})
    with pytest.raises((ConnectionError, ValueError, AssetLiveLedgerError)):
        engine.enter(side="long", mark_price=73.0, decision_time_ms=DECISION_MS)
    assert not any(name == "place_protective_stop" for name, _ in adapter.calls)
    assert engine.snapshot.state is not AssetLiveState.OPEN
    assert "secret-value" not in ledger.path.read_text()


def test_provider_structural_anchor_survives_read_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Recovery binds the same anchor instead of reverting to legacy risk."""
    engine, adapter, _ = _failed_reader(tmp_path, monkeypatch, side="short")
    plan = ProviderExecutionContract(
        entry_liquidity="taker_ioc",
        stop_policy="structural_clamped_bps",
        minimum_stop_bps=20.0,
        maximum_stop_bps=250.0,
        target_policy="none",
        maximum_hold_seconds=86400,
    ).bind(strategy_id="native-hourly", stop_anchor=74.20)
    engine.record_strategy_decision({"execution_plan": plan.as_payload()})
    with pytest.raises(ConnectionError):
        engine.enter(side="short", mark_price=73.0, decision_time_ms=DECISION_MS)
    stops = [value for name, value in adapter.calls if name == "place_protective_stop"]
    assert stops[0]["trigger_price"] == pytest.approx(74.20)
    assert engine.snapshot.execution_plan == plan


def test_read_failure_before_submission_does_not_create_protection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Recovery authority requires an actual acknowledged opening fill."""
    engine, adapter, _ = _failed_reader(tmp_path, monkeypatch)

    def fail() -> HyperliquidReconciliationSnapshot:
        raise ConnectionError(SENSITIVE_ERROR)

    monkeypatch.setattr(adapter, "reconcile", fail)
    with pytest.raises(ConnectionError):
        engine.enter(side="long", mark_price=73.0)
    assert not any(
        name in {"submit_entry", "place_protective_stop"} for name, _ in adapter.calls
    )


def test_stop_rejection_still_attempts_existing_reduce_only_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rejected recovery stop retains the existing emergency-close action."""
    engine, adapter, _ = _failed_reader(tmp_path, monkeypatch)
    adapter.stop_ack = HyperliquidOrderAck(
        False, None, "error", error="injected stop rejection"
    )
    with pytest.raises(ConnectionError):
        engine.enter(side="long", mark_price=73.0)
    names = [name for name, _ in adapter.calls]
    assert names.count("place_protective_stop") == 1
    assert names.count("close_position") == 1
    assert engine.snapshot.state is not AssetLiveState.FLAT


@pytest.mark.parametrize("side", ["long", "short"])
def test_restart_adopts_acknowledged_recovery_stop_without_resubmission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, side: str
) -> None:
    """A stopped verification read leaves sufficient durable ownership to resume."""
    engine, _, ledger = _failed_reader(tmp_path, monkeypatch, side=side)
    with pytest.raises(ConnectionError):
        engine.enter(side=side, mark_price=73.0, decision_time_ms=DECISION_MS)
    intent = next(
        r["payload"]
        for r in ledger.read_all()
        if r["event_type"] == "order_intent"
        and r["payload"]["operation"] == "protective_stop"
    )
    size = 0.30 if side == "long" else -0.30
    stop = _order(
        202,
        size=abs(size),
        reduce_only=True,
        trigger=True,
        side="A" if size > 0 else "B",
    )
    adapter = FakeVenueAdapter([_venue(size, (stop,))])
    identity = intent["client_order_id"]
    adapter.client_statuses[identity] = HyperliquidOrderStatus(
        202,
        "SOL",
        "open",
        abs(size),
        DECISION_MS,
        identity,
    )
    config, restarted_ledger = _runtime(tmp_path)
    resumed = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=restarted_ledger,
        credentials_present=True,
        now_fn=_now,
        sleep_fn=lambda _: None,
    )
    result = resumed.start()
    assert result.state is AssetLiveState.OPEN
    assert result.entry_oid == 101 and result.stop_oid == 202
    assert result.position_size_signed == size and result.opened_at_ms == DECISION_MS
    assert not any(
        name in {"submit_entry", "place_protective_stop"} for name, _ in adapter.calls
    )


@pytest.mark.parametrize(
    "failure",
    [
        ClientError(429, None, SENSITIVE_ERROR, {}),
        ServerError(503, SENSITIVE_ERROR),
        HyperliquidAdapterError(SENSITIVE_ERROR),
    ],
)
def test_known_read_errors_preserve_protection_and_secret_safe_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    """SDK transport/status and parsing failures share the qualified recovery path."""
    engine, adapter, ledger = _failed_reader(tmp_path, monkeypatch, failure=failure)
    with pytest.raises(type(failure)):
        engine.enter(side="long", mark_price=73.0)
    assert [name for name, _ in adapter.calls].count("place_protective_stop") == 1
    assert "secret-value" not in ledger.path.read_text()
    assert engine.snapshot.state is AssetLiveState.PROTECTING


def test_programming_error_is_not_converted_into_fill_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unexpected implementation errors propagate outside the known read-error policy."""
    failure = RuntimeError("injected programming error")
    engine, adapter, _ = _failed_reader(tmp_path, monkeypatch, failure=failure)
    with pytest.raises(RuntimeError, match="programming error"):
        engine.enter(side="long", mark_price=73.0)
    assert not any(name == "place_protective_stop" for name, _ in adapter.calls)


def test_non_ioc_fill_does_not_skip_residual_order_reconciliation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A maker acknowledgement cannot authorize protection before residual checks."""
    engine, adapter, _ = _failed_reader(tmp_path, monkeypatch)
    plan = ProviderExecutionContract(
        entry_liquidity="maker_post_only",
        stop_policy="fixed_bps",
        stop_bps=80.0,
        target_policy="none",
        maximum_hold_seconds=86400,
    ).bind(strategy_id="maker", stop_anchor=None)
    engine.record_strategy_decision({"execution_plan": plan.as_payload()})
    with pytest.raises(ConnectionError):
        engine.enter(side="long", mark_price=73.0)
    assert not any(name == "place_protective_stop" for name, _ in adapter.calls)


@pytest.mark.parametrize("no_fill", [False, True])
def test_rejected_entry_does_not_become_acknowledged_fill_recovery(
    tmp_path: Path, no_fill: bool
) -> None:
    """Definitive rejection and contradictory no-fill truth preserve prior errors."""
    config, ledger = _runtime(tmp_path)
    adapter = FakeVenueAdapter([_venue(0.0), _venue(0.0)] + [_venue(0.30)] * 4)
    message = (
        "Order could not immediately match against any resting orders"
        if no_fill
        else "injected rejection"
    )
    adapter.entry_ack = HyperliquidOrderAck(False, None, "error", error=message)
    engine = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=_now,
        sleep_fn=lambda _: None,
    )
    engine.start()
    with pytest.raises(AssetLiveEngineError):
        engine.enter(side="long", mark_price=73.0)
    assert engine.snapshot.state is AssetLiveState.FAULTED
    assert not any(name == "place_protective_stop" for name, _ in adapter.calls)


def test_mismatched_recovered_position_cannot_be_reported_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The existing ownership check still rejects a changed post-stop position."""
    engine, adapter, _ = _failed_reader(tmp_path, monkeypatch, permanent=False)
    stop = _order(202, size=0.30, reduce_only=True, trigger=True)
    adapter.reconciliations = [_venue(0.0), _venue(0.20, (stop,)), _venue(0.0)]
    with pytest.raises(AssetLiveEngineError):
        engine.enter(side="long", mark_price=73.0)
    assert engine.snapshot.state is not AssetLiveState.OPEN
    closes = [value for name, value in adapter.calls if name == "close_position"]
    assert closes[0]["position_size_signed"] == 0.20


def test_unverified_protection_blocks_a_second_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unresolved read outage cannot admit another opening order."""
    engine, adapter, _ = _failed_reader(tmp_path, monkeypatch)
    with pytest.raises(ConnectionError):
        engine.enter(side="long", mark_price=73.0)
    calls = list(adapter.calls)
    with pytest.raises(AssetLiveEngineError, match="requires FLAT"):
        engine.enter(side="long", mark_price=73.0)
    assert adapter.calls == calls


def test_new_unowned_exposure_before_entry_still_faults_without_orders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pre-entry venue-flat check remains an independent requirement."""
    engine, adapter, _ = _failed_reader(tmp_path, monkeypatch)
    adapter.reconciliations = [_venue(0.30)] * 4
    with pytest.raises(AssetLiveEngineError, match="venue is not flat"):
        engine.enter(side="long", mark_price=73.0)
    assert engine.snapshot.state is AssetLiveState.FAULTED
    assert not any(
        name in {"submit_entry", "place_protective_stop"} for name, _ in adapter.calls
    )

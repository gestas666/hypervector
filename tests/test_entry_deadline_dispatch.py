"""Entry freshness must hold after blocking reconciliation and persistence."""

from collections.abc import Mapping
from pathlib import Path

import pytest
from entry_deadline_fixtures import DECISION_MS, Case, reconciliations, scenario
from test_asset_live_engine import FakeVenueAdapter, _runtime, _venue

from hypervector.live.hyperliquid_protocol import (
    HyperliquidOrderAck,
    HyperliquidOrderStatus,
)
from hypervector.live.multi_asset_cohort_payloads import routing_action_payload
from hypervector.live.asset_order_restart import (
    interrupted_lifecycle_intent,
    pending_order_intent,
)
from hypervector.live.asset_engine import AssetLiveEngine
from hypervector.live.asset_state import AssetLiveState


@pytest.mark.parametrize(
    ("case", "expected_entries"),
    [
        (Case("fresh", 29_000_000), 1),
        (Case("exact_after_check", 28_000_000, 0, 2_000_000), 1),
        (Case("already_stale", 30_001_000), 0),
        (Case("provider_expires", 29_000_000, 2_000_000), 0),
        (Case("flat_check_expires_30s", 29_000_000, 0, 2_000_000), 0),
        (Case("flat_check_expires_60s", 59_000_000, 0, 2_000_000, 60_000), 0),
        (Case("persistence_expires", 29_000_000, persistence_delay_us=2_000_000), 0),
    ],
    ids=lambda value: value.name if isinstance(value, Case) else None,
)
def test_configured_deadline_holds_at_dispatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: Case,
    expected_entries: int,
) -> None:
    """A stale signal cannot dispatch after either blocking pre-entry stage."""
    state = scenario(tmp_path, case)
    original_emit = state.engine._events.emit

    def delayed_emit(event_type: str, payload: Mapping[str, object]) -> None:
        original_emit(event_type, payload)
        if event_type == "order_intent" and payload["operation"] == "entry":
            state.clock.offset_us += case.persistence_delay_us

    monkeypatch.setattr(state.engine._events, "emit", delayed_emit)
    action_count = state.runner.poll_once()

    ages = [stamp - DECISION_MS for stamp in state.adapter.entry_times_ms]
    assert all(age <= case.deadline_ms for age in ages), f"overdue dispatch: {ages}"
    assert action_count == len(ages) == expected_entries
    records = state.ledger.read_all()
    assert not [row for row in records if row["event_type"] == "fault"]
    assert pending_order_intent(records) is None
    assert interrupted_lifecycle_intent(records) is None
    if not expected_entries:
        assert state.engine.snapshot.state is AssetLiveState.FLAT
        report = state.telemetry.routings[0][1]
        assert [item.reason for item in report.withheld] == ["stale_before_submission"]
    else:
        report = state.telemetry.routings[0][1]
        assert (
            report.actions[0].submission_observed_at_ms
            == state.adapter.entry_times_ms[0]
        )


def test_expired_entry_does_not_poison_the_next_cycle(tmp_path: Path) -> None:
    """A subsequent fresh signal can enter, reconcile and protect normally."""
    state = scenario(tmp_path, Case("expires", 29_000_000, 0, 2_000_000))
    assert state.runner.poll_once() == 0
    assert state.engine.snapshot.state is AssetLiveState.FLAT
    state.adapter.reconciliations = reconciliations()[1:]
    state.clock.offset_us = 60_000_000
    state.poller.decision_ms = DECISION_MS + 60_000
    assert state.runner.poll_once() == 1
    assert state.engine.snapshot.state is AssetLiveState.OPEN
    assert state.engine.snapshot.stop_oid == 202
    assert pending_order_intent(state.ledger.read_all()) is None


def test_unsent_marker_resolves_restart_before_flat_state_write(tmp_path: Path) -> None:
    """A crash after the no-dispatch record cannot resurrect the stale intent."""
    state = scenario(tmp_path, Case("expires", 29_000_000, 0, 2_000_000))
    assert state.runner.poll_once() == 0
    records = state.ledger.read_all()
    index = next(
        i for i, row in enumerate(records) if row["event_type"] == "entry_not_submitted"
    )
    assert pending_order_intent(records[: index + 1]) is None
    assert interrupted_lifecycle_intent(records[: index + 1]) is None


def test_expiry_during_reconciliation_retries_is_withheld(tmp_path: Path) -> None:
    """The check follows every bounded retry, not just the initial venue read."""
    state = scenario(tmp_path, Case("retry_expiry", 29_600_000))
    state.adapter.reconciliations = [_venue(0), _venue(0.3), _venue(0.3), _venue(0)]
    assert state.runner.poll_once() == 0
    assert state.clock.offset_us == 30_100_000
    assert state.adapter.entry_times_ms == []
    assert state.engine.snapshot.state is AssetLiveState.FLAT


def test_response_loss_after_dispatch_keeps_recovery_and_protection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An in-time dispatch is reconciled once even when recovery crosses expiry."""
    state = scenario(tmp_path, Case("response_loss", 29_000_000))
    state.adapter.response_loss.add("entry")
    original_lookup = state.adapter.order_status_by_client_id

    def slow_lookup(client_order_id: str) -> HyperliquidOrderStatus:
        state.clock.offset_us += 2_000_000
        return original_lookup(client_order_id)

    monkeypatch.setattr(state.adapter, "order_status_by_client_id", slow_lookup)
    assert state.runner.poll_once() == 1
    assert state.adapter.entry_times_ms == [DECISION_MS + 29_000]
    assert state.clock.offset_us == 31_000_000
    assert state.engine.snapshot.state is AssetLiveState.OPEN
    assert state.engine.snapshot.stop_oid == 202
    records = state.ledger.read_all()
    assert not [row for row in records if row["event_type"] == "entry_not_submitted"]
    ack = next(
        row["payload"]
        for row in records
        if row["event_type"] == "order_acknowledgement"
    )
    assert ack["recovered_after_transport_error"] is True
    assert ack["submission_observed_at_ms"] == DECISION_MS + 29_000
    action = state.telemetry.routings[0][1].actions[0]
    payload = routing_action_payload(action)
    for field in (
        "decision_time_ms",
        "submission_observed_at_ms",
        "submission_age_ms",
        "submission_limit_ms",
        "submission_boundary",
    ):
        assert payload[field] == ack[field]


def test_restart_after_unsent_marker_performs_no_order_lookup_or_dispatch(
    tmp_path: Path,
) -> None:
    """Restart from the crash prefix verifies flatness without reviving the entry."""
    state = scenario(tmp_path, Case("expires", 29_000_000, 0, 2_000_000))
    assert state.runner.poll_once() == 0
    records = state.ledger.read_all()
    index = next(
        i for i, row in enumerate(records) if row["event_type"] == "entry_not_submitted"
    )
    original = state.ledger.path.read_bytes()
    state.ledger.path.with_suffix(".complete.jsonl").write_bytes(original)
    state.ledger.path.write_bytes(
        b"".join(original.splitlines(keepends=True)[: index + 1])
    )
    config, ledger = _runtime(tmp_path)
    adapter = FakeVenueAdapter([_venue(0)])
    restarted = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=state.clock.now,
        sleep_fn=state.clock.sleep,
    )
    assert restarted.start().state is AssetLiveState.FLAT
    assert not [
        name
        for name, _ in adapter.calls
        if name in {"submit_entry", "order_status_by_client_id"}
    ]


def test_guarded_ioc_no_fill_remains_a_submitted_no_fill(tmp_path: Path) -> None:
    """A venue IOC rejection is distinct from local expiry before dispatch."""
    state = scenario(tmp_path, Case("ioc_no_fill", 29_000_000))
    state.adapter.entry_ack = HyperliquidOrderAck(
        False,
        None,
        "error",
        error="Order could not immediately match against any resting orders",
    )
    state.adapter.reconciliations = [_venue(0), _venue(0), _venue(0)]
    assert state.runner.poll_once() == 0
    assert state.adapter.entry_times_ms == [DECISION_MS + 29_000]
    assert state.engine.snapshot.state is AssetLiveState.FLAT
    report = state.telemetry.routings[0][1]
    assert [item.reason for item in report.withheld] == ["entry_ioc_no_fill"]
    assert report.withheld[0].submission_boundary == "sdk_dispatch"
    assert not [
        row
        for row in state.ledger.read_all()
        if row["event_type"] == "entry_not_submitted"
    ]

"""Entry expiry must preserve independent actions and durable failure evidence."""

from collections.abc import Mapping
from pathlib import Path

import pytest
from entry_deadline_fixtures import DECISION_MS, Case, Clock, scenario

from hypervector.live.bidirectional_intents import RoutingAction
from hypervector.live.cohort_entry_submission import execute_fresh_routed_actions
from hypervector.live.entry_submission_deadline import EntrySubmissionDeadline
from hypervector.live.asset_order_restart import pending_order_intent
from hypervector.live.asset_state import AssetLiveState


def test_expired_first_entry_preserves_fresh_route_and_selected_exit() -> None:
    """Each entry gets its own deadline; an exit gets no entry-age restriction."""
    clock = Clock(29_000_000)
    expired = RoutingAction("enter", "first", "SOL", "long", DECISION_MS, 73)
    fresh = RoutingAction("enter", "second", "BTC", "short", DECISION_MS, 100)
    close = RoutingAction("close", "third", "ETH", "long", DECISION_MS, 100)
    dispatched: list[RoutingAction] = []

    def execute(
        action: RoutingAction, deadline: EntrySubmissionDeadline | None
    ) -> None:
        if action is close:
            assert deadline is None
        else:
            assert deadline is not None
            if action.symbol == "SOL":
                clock.offset_us += 2_000_000
            deadline.check("sdk_dispatch")
        dispatched.append(action)

    submitted, withheld = execute_fresh_routed_actions(
        (expired, fresh, close),
        now_ms=clock.milliseconds,
        delays={("first", "SOL"): 30_000, ("second", "BTC"): 60_000},
        execute=execute,
    )
    assert [action.symbol for action in submitted] == ["BTC", "ETH"]
    assert [action.symbol for action in dispatched] == ["BTC", "ETH"]
    assert submitted[0].submission_age_ms == 31_000
    assert [(item.intent.symbol, item.submission_boundary) for item in withheld] == [
        ("SOL", "sdk_dispatch")
    ]


def test_failed_non_submission_write_keeps_pending_intent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed evidence write cannot claim a safely resolved entry lifecycle."""
    state = scenario(tmp_path, Case("write_failure", 29_000_000, 0, 2_000_000))
    original_emit = state.engine._events.emit

    def failing_emit(event_type: str, payload: Mapping[str, object]) -> None:
        if event_type == "entry_not_submitted":
            raise OSError("simulated persistence failure")
        original_emit(event_type, payload)

    monkeypatch.setattr(state.engine._events, "emit", failing_emit)
    with pytest.raises(OSError, match="simulated persistence failure"):
        state.runner.poll_once()
    assert state.adapter.entry_times_ms == []
    assert state.engine.snapshot.state is AssetLiveState.ENTRY_PENDING
    records = state.ledger.read_all()
    assert pending_order_intent(records) is not None
    assert not [row for row in records if row["event_type"] == "entry_not_submitted"]


def test_missing_route_deadline_is_an_actionable_configuration_error() -> None:
    """The public executor retains the missing-policy diagnostic for callers."""
    action = RoutingAction("enter", "first", "SOL", "long", DECISION_MS, 73)
    with pytest.raises(ValueError, match="entry-delay policy is missing route"):
        execute_fresh_routed_actions(
            (action,), now_ms=lambda: DECISION_MS, delays={}, execute=lambda *_: None
        )

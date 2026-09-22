"""Durable, side-correct adaptive exits without network or live clients."""

from collections.abc import Mapping
from dataclasses import replace
from unittest.mock import Mock

import pytest

from test_cohort_profit_lock_controller import _snapshot, _bar, _Engine
from hypervector.live.cohort_adaptive_exit_controller import adaptive_exit_action
from hypervector.live.cohort_adaptive_exit_journal import AdaptiveExitJournal
from hypervector.live.cohort_adaptive_exit_policy import ADAPTIVE_EXIT_POLICY
from hypervector.live.hyperliquid_protocol import SolBookLevel, SolBookSnapshot
from hypervector.live.multi_asset_market_bars import CohortMarketBar


def engine(side: str = "long") -> _Engine:
    """Create an exact owned lifecycle carrying the new explicit policy."""
    current = _snapshot(enabled=False)
    return _Engine(replace(current, opened_at_ms=1_200_000,
                          position_size_signed=1.0 if side == "long" else -1.0,
                          execution_plan=replace(current.execution_plan, adaptive_exit_policy=ADAPTIVE_EXIT_POLICY)))


def book(now: int, price: float) -> SolBookSnapshot:
    """Build a small uncrossed executable snapshot."""
    return SolBookSnapshot(now, (SolBookLevel(price, 10, 1),),
                           (SolBookLevel(price + .001, 10, 1),),
                           price + .0005, .1, 10, 10, 0)


def bars(now: int) -> tuple[CohortMarketBar, ...]:
    """Provide 21 contiguous completed one-minute bars for ATR."""
    last = now // 60_000 * 60_000 - 60_000
    return tuple(_bar(stamp, body=100.0, high=100.1, low=99.9)
                 for stamp in range(last - 20 * 60_000, last + 1, 60_000))


def act(owner: _Engine, journal: AdaptiveExitJournal, now: int, price: float,
        history: tuple[CohortMarketBar, ...] | None = None) -> object:
    """Invoke the production controller against explicitly supplied observations."""
    return adaptive_exit_action(symbol="SOL", snapshot=owner.snapshot, book=book(now, price),
                                observed_ms=now, entry_price=100.0,
                                market_bars=bars(now) if history is None else history,
                                evaluations=(), journal=journal, degraded=Mock())


@pytest.mark.parametrize("side,peak,cross", [("long", 101.0, 100.2), ("short", 99.0, 99.8)])
def test_side_correct_exit_and_restart_preserve_floor(side: str, peak: float, cross: float) -> None:
    """Either side locks profit and reconstructs the floor after a new owner."""
    rows: list[dict[str, object]] = []

    def emit(event: str, payload: Mapping[str, object]) -> None:
        rows.append({"event_type": event, "payload": dict(payload)})

    owner = engine(side)
    journal = AdaptiveExitJournal([], emit)
    assert act(owner, journal, 1_260_000, peak) is None
    restored = AdaptiveExitJournal(rows, emit)
    action = act(owner, restored, 1_275_000, cross)
    assert action is not None and action.side == side
    assert action.exit_reason == "adaptive_profit_floor"
    assert rows[-1]["payload"]["state"]["exit_reason"] == action.exit_reason
    assert act(owner, AdaptiveExitJournal(rows, emit), 1_290_000, peak, ()) is not None


def test_journal_failure_prevents_returning_an_order_action() -> None:
    """A floor cannot claim durability when its append failed."""
    journal = AdaptiveExitJournal([], Mock(side_effect=OSError("disk unavailable")))
    with pytest.raises(OSError):
        act(engine(), journal, 1_260_000, 101.0)
    assert journal.recorded("SOL:7:1200000") is None


def test_recovery_refuses_changed_entry_identity() -> None:
    """Venue entry-price drift cannot reuse another lifecycle's earned floor."""
    journal = AdaptiveExitJournal([], Mock())
    act(engine(), journal, 1_260_000, 101.0)
    with pytest.raises(ValueError, match="identity"):
        adaptive_exit_action(symbol="SOL", snapshot=engine().snapshot,
                             book=book(1_275_000, 100.2), observed_ms=1_275_000,
                             entry_price=101.0, market_bars=bars(1_275_000),
                             evaluations=(), journal=journal, degraded=Mock())


def test_contract_roundtrip_preserves_old_payload_and_binds_new_policy() -> None:
    """Inactive defaults leave old approvals intact; active policy survives restart."""
    from hypervector.live.cohort_execution_plan import BoundExecutionPlan
    legacy = _snapshot(enabled=False).execution_plan
    assert "adaptive_exit_policy" not in legacy.as_payload()
    active = engine().snapshot.execution_plan
    assert BoundExecutionPlan.from_payload(active.as_payload()) == active

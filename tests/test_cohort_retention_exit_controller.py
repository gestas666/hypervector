"""Durable, side-correct v2 retention exits and break-even requests without network."""

from collections.abc import Mapping
from dataclasses import replace
from unittest.mock import Mock

import pytest

from test_cohort_adaptive_exit_controller import bars, book
from test_cohort_profit_lock_controller import _Engine, _snapshot
from hypervector.live.cohort_adaptive_exit_controller import (
    adaptive_exit_action,
    lifecycle_risk_bps,
    retention_breakeven_requested,
)
from hypervector.live.cohort_adaptive_exit_journal import AdaptiveExitJournal
from hypervector.live.cohort_adaptive_exit_policy import (
    ADAPTIVE_EXIT_POLICY,
    RETENTION_EXIT_POLICY,
)
from hypervector.live.canonical_regime_telemetry import (
    CANONICAL_REGIME_TELEMETRY_STRATEGY,
)
from hypervector.live.provider_evaluation import ProviderEvaluation
from hypervector.live.provider_readiness import SignalReadiness


def engine(side: str = "long") -> _Engine:
    """Create an exact owned lifecycle bound to the v2 policy (fixed 80 bps stop, so R = 80)."""
    current = _snapshot(enabled=False)
    return _Engine(
        replace(
            current,
            opened_at_ms=1_200_000,
            position_size_signed=1.0 if side == "long" else -1.0,
            execution_plan=replace(
                current.execution_plan, adaptive_exit_policy=RETENTION_EXIT_POLICY
            ),
        )
    )


def regime(now: int, state: str) -> ProviderEvaluation:
    """One canonical row whose three states share one direction."""
    return ProviderEvaluation(
        CANONICAL_REGIME_TELEMETRY_STRATEGY,
        "SOL",
        now - 30_000,
        100.0,
        "regime_observation",
        False,
        "canonical_regime_observation",
        None,
        SignalReadiness(None, 0, 3, ("warmup",), ("ema_gap",), {}),
        primary_regime=state,
        state_1m=state,
        state_5m=state,
        context_15m=state,
    )


def act(
    owner: _Engine,
    journal: AdaptiveExitJournal,
    now: int,
    price: float,
    evaluations: tuple[ProviderEvaluation, ...] = (),
) -> object:
    return adaptive_exit_action(
        symbol="SOL",
        snapshot=owner.snapshot,
        book=book(now, price),
        observed_ms=now,
        entry_price=100.0,
        market_bars=bars(now),
        evaluations=evaluations,
        journal=journal,
        degraded=Mock(),
    )


def _rows() -> tuple[list[dict[str, object]], object]:
    rows: list[dict[str, object]] = []

    def emit(event: str, payload: Mapping[str, object]) -> None:
        rows.append({"event_type": event, "payload": dict(payload)})

    return rows, emit


def test_risk_unit_comes_from_the_bound_stop_distance() -> None:
    plan = engine().snapshot.execution_plan
    assert lifecycle_risk_bps(plan, 100.0, "long") == pytest.approx(80.0)
    assert lifecycle_risk_bps(plan, 100.0, "short") == pytest.approx(80.0)


@pytest.mark.parametrize(
    "side,peak,floor_cross", [("long", 101.7, 100.39), ("short", 98.3, 99.61)]
)
def test_profit_floor_arms_at_two_risk_and_exits_at_half_risk(
    side: str, peak: float, floor_cross: float
) -> None:
    rows, emit = _rows()
    owner = engine(side)
    journal = AdaptiveExitJournal([], emit)
    assert act(owner, journal, 1_260_000, peak) is None
    state = rows[-1]["payload"]["state"]
    assert (
        state["armed"]
        and state["floor_armed"]
        and state["floor_bps"] == pytest.approx(40.0)
    )
    assert rows[-1]["payload"]["policy"] == RETENTION_EXIT_POLICY
    assert retention_breakeven_requested(
        symbol="SOL", snapshot=owner.snapshot, entry_price=100.0, journal=journal
    )
    restored = AdaptiveExitJournal(rows, emit)
    action = act(owner, restored, 1_275_000, floor_cross)
    assert (
        action is not None
        and action.side == side
        and action.exit_reason == "profit_floor"
    )
    assert not retention_breakeven_requested(
        symbol="SOL", snapshot=owner.snapshot, entry_price=100.0, journal=restored
    )
    replay = act(owner, AdaptiveExitJournal(rows, emit), 1_290_000, peak)
    assert replay is not None and replay.exit_reason == "profit_floor"


def test_regime_flip_giveback_requires_opposed_canonical_alignment() -> None:
    rows, emit = _rows()
    owner = engine("long")
    journal = AdaptiveExitJournal([], emit)
    assert act(owner, journal, 1_260_000, 101.2) is None
    assert (
        act(owner, journal, 1_275_000, 100.7, (regime(1_275_000, "TREND_UP"),)) is None
    )
    assert act(owner, journal, 1_290_000, 100.7) is None
    action = act(owner, journal, 1_305_000, 100.7, (regime(1_305_000, "TREND_DOWN"),))
    assert action is not None and action.exit_reason == "regime_flip_giveback"
    assert rows[-1]["payload"]["alignment"] == pytest.approx(-1.0)


def test_unarmed_lifecycle_requests_no_breakeven_and_never_exits() -> None:
    rows, emit = _rows()
    owner = engine("long")
    journal = AdaptiveExitJournal([], emit)
    for now, price in ((1_260_000, 100.2), (1_275_000, 99.5), (1_290_000, 100.3)):
        assert act(owner, journal, now, price, (regime(now, "TREND_DOWN"),)) is None
    assert not retention_breakeven_requested(
        symbol="SOL", snapshot=owner.snapshot, entry_price=100.0, journal=journal
    )


def test_journal_failure_prevents_returning_an_order_action() -> None:
    journal = AdaptiveExitJournal([], Mock(side_effect=OSError("disk unavailable")))
    with pytest.raises(OSError):
        act(engine(), journal, 1_260_000, 101.7)
    assert journal.recorded("SOL:7:1200000") is None


def test_recovery_refuses_a_v1_row_for_the_same_lifecycle() -> None:
    rows, emit = _rows()
    v1 = _Engine(
        replace(
            engine().snapshot,
            execution_plan=replace(
                engine().snapshot.execution_plan,
                adaptive_exit_policy=ADAPTIVE_EXIT_POLICY,
            ),
        )
    )
    act(v1, AdaptiveExitJournal([], emit), 1_260_000, 101.0)
    with pytest.raises(ValueError, match="identity|policy"):
        act(engine(), AdaptiveExitJournal(rows, emit), 1_275_000, 101.7)


def test_missing_price_is_degraded_not_acted_on() -> None:
    degraded = Mock()
    result = adaptive_exit_action(
        symbol="SOL",
        snapshot=engine().snapshot,
        book=None,
        observed_ms=1_260_000,
        entry_price=100.0,
        market_bars=(),
        evaluations=(),
        journal=AdaptiveExitJournal([], Mock()),
        degraded=degraded,
    )
    assert result is None
    assert degraded.call_args.kwargs["source"] == "retention_exit_inputs"

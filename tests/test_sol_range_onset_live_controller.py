"""Completed-bar decision routing tests for the SOL live controller."""

from __future__ import annotations

from pathlib import Path

import pytest

from hypervector.live.sol_range_onset_config import load_sol_range_onset_config
from hypervector.live.sol_range_onset_controller import (
    SolLiveDecision,
    SolRangeOnsetLiveController,
)
from hypervector.live.sol_range_onset_state import SolLiveSnapshot, SolLiveState


class FakeEngine:
    """Record controller actions without venue access."""

    def __init__(self, snapshot: SolLiveSnapshot) -> None:
        self._snapshot = snapshot
        self.calls: list[tuple[str, object]] = []

    @property
    def snapshot(self) -> SolLiveSnapshot:
        return self._snapshot

    def record_strategy_decision(self, payload: dict[str, object]) -> None:
        self.calls.append(("record_strategy_decision", payload))

    def enter(
        self,
        *,
        side: str,
        mark_price: float,
        decision_time_ms: int | None = None,
    ) -> SolLiveSnapshot:
        assert decision_time_ms is not None
        size = 0.30 if side == "long" else -0.30
        self.calls.append(
            (
                "enter",
                {
                    "side": side,
                    "mark_price": mark_price,
                    "decision_time_ms": decision_time_ms,
                },
            )
        )
        self._snapshot = SolLiveSnapshot(
            state=SolLiveState.OPEN,
            entry_oid=101,
            stop_oid=202,
            position_size_signed=size,
            opened_at_ms=decision_time_ms,
        )
        return self._snapshot

    def exit(self, *, mark_price: float, reason: str) -> SolLiveSnapshot:
        self.calls.append(("exit", {"mark_price": mark_price, "reason": reason}))
        self._snapshot = SolLiveSnapshot(state=SolLiveState.FLAT)
        return self._snapshot


def _decision(
    timestamp_ms: int,
    *,
    long_entry: bool = False,
    short_entry: bool = False,
    long_exit: bool = False,
    short_exit: bool = False,
) -> SolLiveDecision:
    return SolLiveDecision(
        decision_time_ms=timestamp_ms,
        reference_price=73.0,
        long_entry=long_entry,
        short_entry=short_entry,
        long_exit=long_exit,
        short_exit=short_exit,
        primary_regime="RANGE",
        state_1m="RANGE",
        state_5m="RANGE",
        context_15m="TREND_DOWN",
        confidence=0.62,
        structural_direction="long"
        if long_entry
        else "short"
        if short_entry
        else "neutral",
        regime_admitted=long_entry or short_entry,
    )


def _controller(engine: FakeEngine) -> SolRangeOnsetLiveController:
    config = load_sol_range_onset_config(
        Path("tests/fixtures/profiles/sol_range_onset_canary.toml"),
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )
    return SolRangeOnsetLiveController(engine=engine, config=config)


def test_flat_entry_routes_once_with_decision_timestamp() -> None:
    """One completed-bar onset opens at most one SOL position."""
    engine = FakeEngine(SolLiveSnapshot(state=SolLiveState.FLAT))
    controller = _controller(engine)

    result = controller.process(_decision(1_000, long_entry=True))

    assert result.state is SolLiveState.OPEN
    entries = [call for call in engine.calls if call[0] == "enter"]
    assert len(entries) == 1
    assert entries[0][1]["side"] == "long"
    assert entries[0][1]["decision_time_ms"] == 1_000


def test_same_direction_reentry_signal_cannot_duplicate_open_position() -> None:
    """Repeated long onset while already long is telemetry-only."""
    engine = FakeEngine(
        SolLiveSnapshot(
            state=SolLiveState.OPEN,
            entry_oid=101,
            stop_oid=202,
            position_size_signed=0.30,
            opened_at_ms=1_000,
        )
    )
    controller = _controller(engine)

    result = controller.process(_decision(2_000, long_entry=True))

    assert result.state is SolLiveState.OPEN
    assert not any(name == "enter" for name, _ in engine.calls)
    assert not any(name == "exit" for name, _ in engine.calls)


def test_opposite_signal_closes_but_never_reverses_on_same_bar() -> None:
    """A short onset while long first verifies flat and waits for a future bar."""
    engine = FakeEngine(
        SolLiveSnapshot(
            state=SolLiveState.OPEN,
            entry_oid=101,
            stop_oid=202,
            position_size_signed=0.30,
            opened_at_ms=1_000,
        )
    )
    controller = _controller(engine)

    result = controller.process(_decision(2_000, short_entry=True, long_exit=True))

    assert result.state is SolLiveState.FLAT
    exits = [value for name, value in engine.calls if name == "exit"]
    assert len(exits) == 1
    assert exits[0]["reason"] == "opposite_signal"
    assert not any(name == "enter" for name, _ in engine.calls)


def test_maximum_hold_exits_even_without_signal() -> None:
    """The frozen 48-hour maximum hold is enforced from persisted open time."""
    config = load_sol_range_onset_config(
        Path("tests/fixtures/profiles/sol_range_onset_canary.toml"),
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )
    opened = 1_000
    engine = FakeEngine(
        SolLiveSnapshot(
            state=SolLiveState.OPEN,
            entry_oid=101,
            stop_oid=202,
            position_size_signed=-0.30,
            opened_at_ms=opened,
        )
    )
    controller = SolRangeOnsetLiveController(engine=engine, config=config)

    result = controller.process(_decision(opened + config.maximum_hold_seconds * 1_000))

    assert result.state is SolLiveState.FLAT
    exit_call = next(value for name, value in engine.calls if name == "exit")
    assert exit_call["reason"] == "maximum_hold"


def test_invalid_dual_entry_and_nonmonotonic_decisions_are_rejected() -> None:
    """Ambiguous or time-reversed completed-bar input is a technical fault."""
    with pytest.raises(ValueError, match="both long and short"):
        _decision(1_000, long_entry=True, short_entry=True)

    engine = FakeEngine(SolLiveSnapshot(state=SolLiveState.FLAT))
    controller = _controller(engine)
    controller.process(_decision(2_000))
    with pytest.raises(ValueError, match="strictly increasing"):
        controller.process(_decision(2_000))


def test_every_decision_is_recorded_before_action() -> None:
    """The strategy input remains auditable even when it results in hold."""
    engine = FakeEngine(SolLiveSnapshot(state=SolLiveState.FLAT))
    controller = _controller(engine)

    controller.process(_decision(1_000))

    assert engine.calls[0][0] == "record_strategy_decision"
    payload = engine.calls[0][1]
    assert isinstance(payload, dict)
    assert payload["state_5m"] == "RANGE"
    assert payload["decision_action"] == "hold"

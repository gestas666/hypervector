"""Real engine and adapter execution of the venue break-even stop raise, offline."""

from decimal import Decimal
import json
from pathlib import Path

import pytest
from native_replay_engine_fixture import EngineReplayFixture

from hypervector.live.cohort_adaptive_exit_policy import RETENTION_EXIT_POLICY
from hypervector.live.cohort_execution_plan import ProviderExecutionContract
from hypervector.live.sol_range_onset_state import SolLiveState


def _open(tmp_path: Path, side: str):
    replay = EngineReplayFixture(
        tmp_path, partial_entry=False, initial_cash=Decimal(5000)
    )
    symbol = "xyz:SNDK"
    engine = replay.engine(replay.assets[symbol])
    contract = ProviderExecutionContract(
        entry_liquidity="taker_ioc",
        stop_policy="fixed_bps",
        stop_bps=250,
        target_policy="none",
        maximum_hold_seconds=86400,
        adaptive_exit_policy=RETENTION_EXIT_POLICY,
    )
    engine.start()
    replay.prepare_entry(symbol, side, replay.clock.now_ms)
    engine.record_strategy_decision(
        {
            "routing_action": "enter",
            "execution_plan": contract.bind(
                strategy_id="test", stop_anchor=None
            ).as_payload(),
        }
    )
    result = engine.enter(
        side=side, mark_price=100, decision_time_ms=replay.clock.now_ms
    )
    assert result.state is SolLiveState.OPEN and result.stop_oid is not None
    return replay, engine, symbol


def _rows(tmp_path: Path, symbol: str) -> list[dict[str, object]]:
    ledger = tmp_path / "live/bidirectional_cohort" / f"{symbol}.jsonl"
    return [json.loads(line) for line in ledger.read_text().splitlines()]


@pytest.mark.parametrize("side,trigger", [("long", 100.25), ("short", 99.75)])
def test_raise_replaces_the_owned_stop_and_survives_reconciliation(
    tmp_path: Path, side: str, trigger: float
) -> None:
    replay, engine, symbol = _open(tmp_path, side)
    previous = engine.snapshot.stop_oid
    assert engine.raise_protective_stop(trigger_price=trigger) is True
    assert engine.snapshot.state is SolLiveState.OPEN
    assert engine.snapshot.stop_oid != previous
    assert previous not in replay.orders
    resting = replay.orders[engine.snapshot.stop_oid]
    assert float(resting["triggerPx"]) == pytest.approx(trigger, abs=0.01)
    assert resting["reduceOnly"] and resting["isTrigger"]
    assert replay.mutations[-1] == "modify"
    rows = _rows(tmp_path, symbol)
    intent = next(
        r
        for r in rows
        if r["event_type"] == "order_intent"
        and r["payload"]["operation"] == "raise_protective_stop"
    )
    raised = next(r for r in rows if r["event_type"] == "protective_stop_raised")
    assert rows.index(intent) < rows.index(raised)
    assert raised["payload"]["previous_stop_oid"] == previous
    assert raised["payload"]["stop_oid"] == engine.snapshot.stop_oid
    # a fresh owner adopts the replaced identity from the durable ledger and the venue
    restored = replay.engine(replay.assets[symbol])
    assert restored.start().stop_oid == engine.snapshot.stop_oid


def test_raise_never_loosens_the_stop(tmp_path: Path) -> None:
    replay, engine, symbol = _open(tmp_path, "long")
    previous = engine.snapshot.stop_oid
    assert engine.raise_protective_stop(trigger_price=97.0) is False
    assert engine.snapshot.stop_oid == previous and previous in replay.orders
    assert "modify" not in replay.mutations


def test_rejected_modify_keeps_the_original_stop(tmp_path: Path) -> None:
    replay, engine, symbol = _open(tmp_path, "long")
    previous = engine.snapshot.stop_oid
    original_modify = replay._exchange.modify_order.side_effect
    replay._exchange.modify_order.side_effect = lambda *a, **k: replay._ack(
        {"error": "Insufficient margin"}
    )
    assert engine.raise_protective_stop(trigger_price=100.25) is False
    assert engine.snapshot.stop_oid == previous and previous in replay.orders
    assert engine.snapshot.state is SolLiveState.OPEN
    replay._exchange.modify_order.side_effect = original_modify
    restored = replay.engine(replay.assets[symbol])
    assert restored.start().stop_oid == previous


def test_raise_interrupted_after_the_venue_applied_it_is_adopted_on_restart(
    tmp_path: Path,
) -> None:
    replay, engine, symbol = _open(tmp_path, "long")
    previous = engine.snapshot.stop_oid
    applied = replay._modify

    def crash_after_mutation(*args: object, **kwargs: object) -> object:
        applied(*args, **kwargs)
        raise RuntimeError("simulated crash after the venue accepted the replacement")

    replay._exchange.modify_order.side_effect = crash_after_mutation
    with pytest.raises(RuntimeError):
        engine.raise_protective_stop(trigger_price=100.25)
    assert previous not in replay.orders and len(replay.orders) == 1
    new_oid = next(iter(replay.orders))
    replay._exchange.modify_order.side_effect = applied
    restored = replay.engine(replay.assets[symbol])
    snapshot = restored.start()
    assert snapshot.state is SolLiveState.OPEN and snapshot.stop_oid == new_oid
    rows = _rows(tmp_path, symbol)
    recovered = [
        r
        for r in rows
        if r["event_type"] == "protective_stop_raised"
        and r["payload"].get("recovered_after_restart")
    ]
    assert recovered and recovered[-1]["payload"]["stop_oid"] == new_oid


def test_raise_interrupted_before_the_venue_saw_it_keeps_the_original_stop(
    tmp_path: Path,
) -> None:
    replay, engine, symbol = _open(tmp_path, "long")
    previous = engine.snapshot.stop_oid
    replay._exchange.modify_order.side_effect = lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("crash before dispatch")
    )
    with pytest.raises(RuntimeError):
        engine.raise_protective_stop(trigger_price=100.25)
    assert previous in replay.orders
    restored = replay.engine(replay.assets[symbol])
    snapshot = restored.start()
    assert snapshot.state is SolLiveState.OPEN and snapshot.stop_oid == previous
    resolved = _unindexed_raise_resolutions(_rows(tmp_path, symbol))
    assert len(resolved) == 1 and resolved[0]["accepted"] is False
    assert resolved[0]["oid"] is None


def test_repeated_pre_dispatch_raise_crashes_never_accumulate_unresolved_intents(
    tmp_path: Path,
) -> None:
    replay, engine, symbol = _open(tmp_path, "long")
    previous = engine.snapshot.stop_oid
    replay._exchange.modify_order.side_effect = lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("crash before dispatch")
    )
    for _ in range(3):
        with pytest.raises(RuntimeError):
            engine.raise_protective_stop(trigger_price=100.25)
        engine = replay.engine(replay.assets[symbol])
        snapshot = engine.start()
        assert snapshot.state is SolLiveState.OPEN and snapshot.stop_oid == previous
    rows = _rows(tmp_path, symbol)
    intents = [
        r["payload"]["client_order_id"]
        for r in rows
        if r["event_type"] == "order_intent"
        and r["payload"]["operation"] == "raise_protective_stop"
    ]
    resolved = _unindexed_raise_resolutions(rows)
    assert len(intents) == 3
    assert [r["client_order_id"] for r in resolved] == intents
    assert not [r for r in rows if r["event_type"] == "fault"]
    assert "modify" not in replay.mutations and previous in replay.orders


def _unindexed_raise_resolutions(
    rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    return [
        r["payload"]
        for r in rows
        if r["event_type"] == "stop_order"
        and r["payload"]["operation"] == "protective_stop_raise_restart_recovery"
        and r["payload"]["status"] == "not_indexed_after_restart"
    ]

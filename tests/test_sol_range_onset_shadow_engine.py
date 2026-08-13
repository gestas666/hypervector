from __future__ import annotations

import json

import pytest

from hypervector.data.hl_events import (
    AssetContextEvent,
    BookLevel,
    L2SnapshotEvent,
    StreamGap,
)
from hypervector.research import range_onset_forward_observer
from hypervector.research.range_onset_event_models import EventSignal


def _book(
    timestamp_ms: int,
    *,
    bid_price: float = 99.9,
    bid_size: float = 40.0,
    ask_price: float = 100.1,
    ask_size: float = 40.0,
) -> L2SnapshotEvent:
    return L2SnapshotEvent(
        symbol="SOL",
        exchange_ts_ms=timestamp_ms,
        received_ts_ns=timestamp_ms * 1_000_000,
        bids=(BookLevel(bid_price, bid_size, 1),),
        asks=(BookLevel(ask_price, ask_size, 1),),
    )


def _context(
    timestamp_ms: int,
    *,
    mark_price: float,
    funding_rate: float = 0.0,
) -> AssetContextEvent:
    return AssetContextEvent(
        symbol="SOL",
        observed_ts_ms=timestamp_ms,
        received_ts_ns=timestamp_ms * 1_000_000,
        mark_price=mark_price,
        oracle_price=mark_price,
        funding_rate_hourly=funding_rate,
        open_interest=1_000_000.0,
        mid_price=mark_price,
    )


def test_shadow_engine_contract_is_available() -> None:
    assert hasattr(range_onset_forward_observer, "SolRangeOnsetShadowEngine")


def test_entry_uses_first_fresh_finite_depth_and_shared_capital() -> None:
    config = range_onset_forward_observer.SolShadowConfig()
    engine = range_onset_forward_observer.SolRangeOnsetShadowEngine(config)
    engine.update_shared_capital(
        range_onset_forward_observer.SharedCapitalSnapshot(
            observed_time_ms=1_000,
            equity_usd=15_000.0,
            reserved_margin_usd=5_250.0,
            source_run_id="btc-run",
        )
    )
    engine.ingest_decision(EventSignal(1_000, 100.0, True, False, False, False))

    engine.ingest_event(_book(1_100))

    state = engine.snapshot
    assert state.status == "active"
    assert state.position is not None
    assert state.position.direction == "long"
    assert state.position.notional_usd == pytest.approx(2_250.0)
    assert state.position.margin_usd == pytest.approx(450.0)
    assert state.position.quantity == pytest.approx(22.5)
    assert state.position.entry_price == pytest.approx(100.1)
    assert state.position.entry_fee_usd == pytest.approx(1.0135125)
    assert state.position.stop_price == pytest.approx(99.4994)
    assert state.sol_realized_delta_usd == pytest.approx(-1.0135125)
    records = engine.drain_records()
    assert records[-1]["action"] == "entry_filled"
    assert records[-1]["execution_authority"] == "none"
    assert records[-1]["submitted"] is False
    assert records[-1]["place_attempted"] is False
    assert records[-1]["direction"] == "long"
    assert records[-1]["fill_px"] == pytest.approx(100.1)
    assert records[-1]["fill_qty"] == pytest.approx(22.5)
    assert records[-1]["position_qty"] == pytest.approx(22.5)
    assert records[-1]["fee_usd"] == pytest.approx(1.0135125)
    assert records[-1]["equity_delta_usd"] == pytest.approx(-1.0135125)


def test_incomplete_first_snapshot_rejects_entry_without_retrying_size() -> None:
    engine = range_onset_forward_observer.SolRangeOnsetShadowEngine()
    engine.update_shared_capital(
        range_onset_forward_observer.SharedCapitalSnapshot(
            1_000,
            15_000.0,
            0.0,
            "btc-run",
        )
    )
    engine.ingest_decision(EventSignal(1_000, 100.0, False, True, False, False))

    engine.ingest_event(_book(1_100, bid_size=10.0))

    assert engine.snapshot.position is None
    assert engine.snapshot.pending_entry is None
    record = engine.drain_records()[-1]
    assert record["action"] == "entry_depth_rejected"
    assert record["requested_quantity"] == pytest.approx(22.5)
    assert record["visible_filled_quantity"] == pytest.approx(10.0)


def test_shared_margin_shortfall_rejects_entry_with_auditable_amounts() -> None:
    engine = range_onset_forward_observer.SolRangeOnsetShadowEngine()
    engine.update_shared_capital(
        range_onset_forward_observer.SharedCapitalSnapshot(
            1_000,
            15_000.0,
            14_700.0,
            "btc-run",
        )
    )
    engine.ingest_decision(EventSignal(1_000, 100.0, True, False, False, False))

    engine.ingest_event(_book(1_100))

    assert engine.snapshot.position is None
    record = engine.drain_records()[-1]
    assert record["action"] == "entry_shared_margin_rejected"
    assert record["combined_equity_usd"] == pytest.approx(15_000.0)
    assert record["reserved_margin_usd"] == pytest.approx(14_700.0)
    assert record["required_margin_usd"] == pytest.approx(450.0)


def test_future_shared_capital_cannot_authorize_an_earlier_fill() -> None:
    engine = range_onset_forward_observer.SolRangeOnsetShadowEngine()
    engine.update_shared_capital(
        range_onset_forward_observer.SharedCapitalSnapshot(
            1_200,
            15_000.0,
            0.0,
            "btc-run",
        )
    )
    engine.ingest_decision(EventSignal(1_000, 100.0, True, False, False, False))

    engine.ingest_event(_book(1_100))

    assert engine.snapshot.position is None
    record = engine.drain_records()[-1]
    assert record["action"] == "entry_capital_unavailable"
    assert record["capital_age_ms"] == -100


def test_wrong_symbol_public_event_is_rejected() -> None:
    engine = range_onset_forward_observer.SolRangeOnsetShadowEngine()
    wrong_book = L2SnapshotEvent(
        symbol="BTC",
        exchange_ts_ms=1_100,
        received_ts_ns=1_100_000_000,
        bids=(BookLevel(99.9, 40.0, 1),),
        asks=(BookLevel(100.1, 40.0, 1),),
    )

    with pytest.raises(ValueError, match="SOL shadow event symbol"):
        engine.ingest_event(wrong_book)


def test_stale_entry_decision_cannot_open_at_the_restart_book() -> None:
    engine = range_onset_forward_observer.SolRangeOnsetShadowEngine()
    engine.update_shared_capital(
        range_onset_forward_observer.SharedCapitalSnapshot(
            1_000,
            15_000.0,
            0.0,
            "btc-run",
        )
    )

    engine.ingest_decision(
        EventSignal(1_000, 100.0, True, False, False, False),
        fresh_at_observation=False,
    )
    engine.ingest_event(_book(1_100))

    assert engine.snapshot.position is None
    assert engine.snapshot.pending_entry is None
    record = engine.drain_records()[-1]
    assert record["action"] == "stale_entry_ignored"
    assert record["decision_time_ms"] == 1_000


def test_stale_opposite_decision_closes_without_reversing() -> None:
    engine = range_onset_forward_observer.SolRangeOnsetShadowEngine()
    engine.update_shared_capital(
        range_onset_forward_observer.SharedCapitalSnapshot(
            1_000,
            15_000.0,
            0.0,
            "btc-run",
        )
    )
    engine.ingest_decision(EventSignal(1_000, 100.0, True, False, False, False))
    engine.ingest_event(_book(1_100))
    engine.drain_records()

    engine.ingest_decision(
        EventSignal(2_000, 101.0, False, True, False, False),
        fresh_at_observation=False,
    )
    engine.ingest_event(_book(2_100))

    assert engine.snapshot.position is None
    assert engine.snapshot.pending_reversal is None
    assert engine.snapshot.completed_trades[-1].exit_reason == "opposite_signal"
    assert [record["action"] for record in engine.drain_records()] == [
        "stale_opposite_signal_exit_triggered",
        "position_closed",
    ]


def test_mark_stop_triggers_then_exits_at_next_finite_depth() -> None:
    engine = range_onset_forward_observer.SolRangeOnsetShadowEngine()
    engine.update_shared_capital(
        range_onset_forward_observer.SharedCapitalSnapshot(
            1_000,
            15_000.0,
            0.0,
            "btc-run",
        )
    )
    engine.ingest_decision(EventSignal(1_000, 100.0, True, False, False, False))
    engine.ingest_event(_book(1_100))
    engine.drain_records()

    engine.ingest_event(_context(1_200, mark_price=99.4))

    assert engine.snapshot.position is not None
    assert engine.snapshot.pending_exit_reason == "stop"
    engine.ingest_event(_book(1_300, bid_price=99.3))

    assert engine.snapshot.position is None
    assert engine.snapshot.pending_exit_reason is None
    assert len(engine.snapshot.completed_trades) == 1
    trade = engine.snapshot.completed_trades[0]
    assert trade.exit_reason == "stop"
    assert trade.exit_price == pytest.approx(99.3)
    assert trade.gross_pnl_usd == pytest.approx(-18.0)
    assert trade.net_pnl_usd == pytest.approx(-20.018925)
    assert engine.snapshot.sol_realized_delta_usd == pytest.approx(-20.018925)
    records = engine.drain_records()
    assert [record["action"] for record in records] == [
        "stop_triggered",
        "position_closed",
    ]
    close = records[-1]
    assert close["fill_px"] == pytest.approx(99.3)
    assert close["fill_qty"] == pytest.approx(22.5)
    assert close["position_qty"] == 0.0
    assert close["exit_reason"] == "stop"
    assert close["equity_delta_usd"] == pytest.approx(-20.018925)


def test_liquidation_has_priority_when_mark_crosses_both_boundaries() -> None:
    engine = range_onset_forward_observer.SolRangeOnsetShadowEngine()
    engine.update_shared_capital(
        range_onset_forward_observer.SharedCapitalSnapshot(
            1_000,
            15_000.0,
            0.0,
            "btc-run",
        )
    )
    engine.ingest_decision(EventSignal(1_000, 100.0, True, False, False, False))
    engine.ingest_event(_book(1_100))
    position = engine.snapshot.position
    assert position is not None
    liquidation = position.liquidation_price
    engine.drain_records()

    engine.ingest_event(_context(1_200, mark_price=liquidation - 1.0))

    record = engine.drain_records()[-1]
    assert engine.snapshot.pending_exit_reason == "liquidation"
    assert record["action"] == "liquidation_triggered"
    assert record["mark_price"] == pytest.approx(liquidation - 1.0)
    assert record["liquidation_price"] == pytest.approx(liquidation)


def test_hourly_funding_settles_once_and_moves_liquidation_boundary() -> None:
    entry_decision_ms = 3_590_000
    engine = range_onset_forward_observer.SolRangeOnsetShadowEngine()
    engine.update_shared_capital(
        range_onset_forward_observer.SharedCapitalSnapshot(
            entry_decision_ms,
            15_000.0,
            0.0,
            "btc-run",
        )
    )
    engine.ingest_decision(
        EventSignal(entry_decision_ms, 100.0, True, False, False, False)
    )
    engine.ingest_event(_book(3_590_100))
    before = engine.snapshot.position
    assert before is not None
    engine.drain_records()

    engine.ingest_event(_context(3_605_000, mark_price=100.0, funding_rate=0.0001))
    engine.ingest_event(_context(3_606_000, mark_price=100.0, funding_rate=0.0001))

    after = engine.snapshot.position
    assert after is not None
    assert after.funding_cashflow_usd == pytest.approx(-0.225)
    assert after.liquidation_price > before.liquidation_price
    assert engine.snapshot.sol_realized_delta_usd == pytest.approx(-1.2385125)
    records = engine.drain_records()
    assert [record["action"] for record in records] == ["funding_settled"]
    assert records[0]["funding_cashflow_usd"] == pytest.approx(-0.225)
    assert records[0]["funding_payment_usd"] == pytest.approx(-0.225)
    assert records[0]["position_qty"] == pytest.approx(22.5)
    assert records[0]["equity_delta_usd"] == pytest.approx(-1.2385125)


def test_opposite_signal_closes_then_reverses_on_the_same_snapshot() -> None:
    engine = range_onset_forward_observer.SolRangeOnsetShadowEngine()
    engine.update_shared_capital(
        range_onset_forward_observer.SharedCapitalSnapshot(
            1_000,
            15_000.0,
            0.0,
            "btc-run",
        )
    )
    engine.ingest_decision(EventSignal(1_000, 100.0, True, False, False, False))
    engine.ingest_event(_book(1_100))
    engine.drain_records()

    engine.ingest_decision(EventSignal(2_000, 101.0, False, True, False, False))

    assert engine.snapshot.pending_exit_reason == "opposite_signal"
    assert engine.snapshot.pending_reversal is not None
    engine.ingest_event(_book(2_100))

    assert len(engine.snapshot.completed_trades) == 1
    assert engine.snapshot.completed_trades[0].exit_reason == "opposite_signal"
    assert engine.snapshot.position is not None
    assert engine.snapshot.position.direction == "short"
    assert engine.snapshot.pending_reversal is None
    assert [record["action"] for record in engine.drain_records()] == [
        "opposite_signal_triggered",
        "position_closed",
        "entry_filled",
    ]


def test_maximum_hold_exits_on_first_depth_at_or_after_deadline() -> None:
    config = range_onset_forward_observer.SolShadowConfig(max_hold_ms=1_000)
    engine = range_onset_forward_observer.SolRangeOnsetShadowEngine(config)
    engine.update_shared_capital(
        range_onset_forward_observer.SharedCapitalSnapshot(
            1_000,
            15_000.0,
            0.0,
            "btc-run",
        )
    )
    engine.ingest_decision(EventSignal(1_000, 100.0, True, False, False, False))
    engine.ingest_event(_book(1_100))
    engine.drain_records()

    engine.ingest_event(_book(2_099))
    assert engine.snapshot.position is not None
    engine.ingest_event(_book(2_100))

    assert engine.snapshot.position is None
    assert engine.snapshot.completed_trades[-1].exit_reason == "max_hold"
    assert [record["action"] for record in engine.drain_records()] == [
        "max_hold_triggered",
        "position_closed",
    ]


def test_stream_gap_censors_active_lifecycle_but_not_flat_observation() -> None:
    flat = range_onset_forward_observer.SolRangeOnsetShadowEngine()
    gap = StreamGap(
        "SOL", "l2Book,trades,activeAssetCtx", 2_000_000_000, "test", 1_000, None
    )

    flat.ingest_event(gap)

    assert flat.snapshot.status == "active"
    assert flat.drain_records()[-1]["action"] == "flat_stream_gap"

    active = range_onset_forward_observer.SolRangeOnsetShadowEngine()
    active.update_shared_capital(
        range_onset_forward_observer.SharedCapitalSnapshot(
            1_000,
            15_000.0,
            0.0,
            "btc-run",
        )
    )
    active.ingest_decision(EventSignal(1_000, 100.0, True, False, False, False))
    active.ingest_event(_book(1_100))
    active.drain_records()

    active.ingest_event(gap)

    assert active.snapshot.status == "evidence_failed"
    assert active.snapshot.position is not None
    record = active.drain_records()[-1]
    assert record["action"] == "active_stream_gap"
    assert record["reason"] == "test"


def test_missing_funding_hour_censors_open_position() -> None:
    engine = range_onset_forward_observer.SolRangeOnsetShadowEngine()
    engine.update_shared_capital(
        range_onset_forward_observer.SharedCapitalSnapshot(
            1_000,
            15_000.0,
            0.0,
            "btc-run",
        )
    )
    engine.ingest_decision(EventSignal(1_000, 100.0, True, False, False, False))
    engine.ingest_event(_book(1_100))
    engine.drain_records()

    engine.ingest_event(_context(7_201_000, mark_price=100.0))

    assert engine.snapshot.status == "evidence_failed"
    record = engine.drain_records()[-1]
    assert record["action"] == "funding_evidence_gap"
    assert record["last_funding_hour_ms"] == 0
    assert record["observed_funding_hour_ms"] == 7_200_000


def test_state_round_trip_preserves_open_position_and_accounting() -> None:
    config = range_onset_forward_observer.SolShadowConfig()
    engine = range_onset_forward_observer.SolRangeOnsetShadowEngine(config)
    engine.update_shared_capital(
        range_onset_forward_observer.SharedCapitalSnapshot(
            1_000,
            15_000.0,
            0.0,
            "btc-run",
        )
    )
    engine.ingest_decision(EventSignal(1_000, 100.0, False, True, False, False))
    engine.ingest_event(_book(1_100))

    payload = json.loads(json.dumps(engine.export_state()))
    restored = range_onset_forward_observer.SolRangeOnsetShadowEngine.from_state(
        config,
        payload,
    )

    assert restored.snapshot == engine.snapshot
    assert restored.config_fingerprint == engine.config_fingerprint
    assert restored.drain_records() == ()

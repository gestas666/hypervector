"""Failure-injected lifecycle tests for the per-symbol live execution engine."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from hypervector.live.cohort_entry_sizing import CohortEntrySizing
from hypervector.live.cohort_execution_plan import ProviderExecutionContract
from hypervector.live.hyperliquid_protocol import (
    HyperliquidFeeSchedule,
    HyperliquidOrderAck,
    HyperliquidOrderStatus,
    HyperliquidAccountSnapshot,
    HyperliquidBookLevel,
    HyperliquidBookSnapshot,
    HyperliquidFill,
    HyperliquidMarketMetadata,
    HyperliquidFundingPayment,
    HyperliquidOpenOrder,
    HyperliquidPositionSnapshot,
    HyperliquidReconciliationSnapshot,
    HyperliquidVenuePreflight,
)
from hypervector.live.asset_engine_config import AssetEngineConfig
from hypervector.live.asset_engine import (
    AssetEntryNotFilledError,
    AssetLiveEngineError,
    AssetLiveEngine,
)
from hypervector.live.asset_ledger import AssetLiveLedger
from hypervector.live.asset_state import AssetLiveState
from hypervector.live.asset_order_transport import (
    AssetCancelTransportError,
    AssetOrderTransportError,
)

from engine_config_fixtures import engine_asset_config, engine_ledger_path


class FakeVenueAdapter:
    """Script venue reconciliation and record every authenticated operation."""

    def __init__(self, reconciliations: list[HyperliquidReconciliationSnapshot]) -> None:
        self.reconciliations = list(reconciliations)
        self.calls: list[tuple[str, object]] = []
        self.entry_ack = HyperliquidOrderAck(True, 101, "filled", 0.30, 73.10)
        self.stop_ack = HyperliquidOrderAck(True, 202, "resting")
        self.target_ack = HyperliquidOrderAck(True, 203, "resting")
        self.cancel_ack = HyperliquidOrderAck(True, 202, "canceled")
        self.close_ack = HyperliquidOrderAck(True, 303, "filled", 0.30, 73.20)
        self.funding: tuple[HyperliquidFundingPayment, ...] = ()
        self.response_loss: set[str] = set()
        self.client_statuses: dict[str, HyperliquidOrderStatus] = {}
        self.cancel_response_loss = False
        self.oid_statuses: dict[int, HyperliquidOrderStatus] = {}

    def preflight(self, *, expected_max_leverage: int) -> HyperliquidVenuePreflight:
        self.calls.append(("preflight", expected_max_leverage))
        return HyperliquidVenuePreflight(
            market=HyperliquidMarketMetadata("SOL", 2, 20),
            mark_price=73.0,
            price_tick=0.001,
            size_step=0.01,
            fees=HyperliquidFeeSchedule(0.00015, 0.00045),
            account_value_usd=150.0,
            withdrawable_usd=150.0,
            position=_position(0.0),
        )

    def book_snapshot(self, *, depth_levels: int) -> HyperliquidBookSnapshot:
        self.calls.append(("book_snapshot", depth_levels))
        return HyperliquidBookSnapshot(
            1_785_499_200_123,
            (HyperliquidBookLevel(73.0, 10.0, 2),),
            (HyperliquidBookLevel(73.1, 8.0, 2),),
            73.05,
            (0.1 / 73.05) * 10_000.0,
            10.0,
            8.0,
            2.0 / 18.0,
        )

    def configure_isolated_leverage(self, leverage: int) -> None:
        self.calls.append(("configure_isolated_leverage", leverage))

    def submit_entry(
        self,
        *,
        side: str,
        requested_notional_usd: float,
        mark_price: float,
        client_order_id: str,
    ) -> HyperliquidOrderAck:
        self.calls.append(
            (
                "submit_entry",
                {
                    "side": side,
                    "requested_notional_usd": requested_notional_usd,
                    "mark_price": mark_price,
                    "client_order_id": client_order_id,
                },
            )
        )
        return self._ack_or_lose("entry", client_order_id, self.entry_ack)

    def place_protective_stop(
        self,
        *,
        position_size_signed: float,
        trigger_price: float,
        client_order_id: str,
    ) -> HyperliquidOrderAck:
        self.calls.append(
            (
                "place_protective_stop",
                {
                    "position_size_signed": position_size_signed,
                    "trigger_price": trigger_price,
                    "client_order_id": client_order_id,
                },
            )
        )
        return self._ack_or_lose(
            "protective_stop",
            client_order_id,
            self.stop_ack,
        )

    def cancel_order(self, oid: int) -> HyperliquidOrderAck:
        self.calls.append(("cancel_order", oid))
        if self.cancel_response_loss:
            raise AssetCancelTransportError(
                operation="cancel_order",
                oid=oid,
                detail="injected response loss",
            )
        return replace(self.cancel_ack, oid=oid)

    def submit_target(
        self,
        *,
        position_size_signed: float,
        limit_price: float,
        client_order_id: str,
    ) -> HyperliquidOrderAck:
        self.calls.append(
            (
                "submit_target",
                {
                    "position_size_signed": position_size_signed,
                    "limit_price": limit_price,
                    "client_order_id": client_order_id,
                },
            )
        )
        return self._ack_or_lose("target", client_order_id, self.target_ack)

    def close_position(
        self,
        *,
        position_size_signed: float,
        mark_price: float,
        client_order_id: str,
    ) -> HyperliquidOrderAck:
        self.calls.append(
            (
                "close_position",
                {
                    "position_size_signed": position_size_signed,
                    "mark_price": mark_price,
                    "client_order_id": client_order_id,
                },
            )
        )
        return self._ack_or_lose(
            "reduce_only_close",
            client_order_id,
            self.close_ack,
        )

    def reconcile(self) -> HyperliquidReconciliationSnapshot:
        self.calls.append(("reconcile", None))
        if not self.reconciliations:
            raise AssertionError("unexpected reconciliation call")
        return self.reconciliations.pop(0)

    def order_status(self, oid: int) -> HyperliquidOrderStatus:
        self.calls.append(("order_status", oid))
        return self.oid_statuses.get(
            oid,
            HyperliquidOrderStatus(oid, "SOL", "filled", 0.30, 1),
        )

    def order_status_by_client_id(
        self,
        client_order_id: str,
    ) -> HyperliquidOrderStatus:
        self.calls.append(("order_status_by_client_id", client_order_id))
        return self.client_statuses[client_order_id]

    def _ack_or_lose(
        self,
        operation: str,
        client_order_id: str,
        ack: HyperliquidOrderAck,
    ) -> HyperliquidOrderAck:
        identified = replace(ack, client_order_id=client_order_id)
        status = "open" if ack.status == "resting" else ack.status
        if ack.oid is not None:
            self.client_statuses[client_order_id] = HyperliquidOrderStatus(
                ack.oid,
                "SOL",
                status,
                ack.filled_size or 0.30,
                1,
                client_order_id,
            )
        if operation in self.response_loss:
            raise AssetOrderTransportError(
                operation=operation,
                client_order_id=client_order_id,
                detail="injected response loss",
            )
        return identified

    def funding_payments(
        self,
        *,
        start_time_ms: int,
        end_time_ms: int,
    ) -> tuple[HyperliquidFundingPayment, ...]:
        self.calls.append(("funding_payments", (start_time_ms, end_time_ms)))
        return self.funding


def _position(size: float, *, entry_price: float = 73.10) -> HyperliquidPositionSnapshot:
    return HyperliquidPositionSnapshot(
        size_signed=size,
        entry_price=entry_price if size else None,
        liquidation_price=60.5 if size else None,
        margin_used_usd=4.386 if size else 0.0,
        position_value_usd=abs(size) * entry_price,
        unrealized_pnl_usd=0.0,
        leverage_type="isolated" if size else None,
        leverage=5 if size else None,
    )


def _order(
    oid: int,
    *,
    size: float,
    reduce_only: bool,
    trigger: bool,
    side: str = "A",
    limit_price: float | None = None,
) -> HyperliquidOpenOrder:
    return HyperliquidOpenOrder(
        oid=oid,
        size=size,
        original_size=size,
        side=side,
        reduce_only=reduce_only,
        is_trigger=trigger,
        trigger_price=72.5152 if trigger else None,
        order_type="Stop Market" if trigger else "Market",
        timestamp_ms=1,
        limit_price=limit_price,
    )


def _venue(
    size: float,
    orders: tuple[HyperliquidOpenOrder, ...] = (),
    fills: tuple[HyperliquidFill, ...] = (),
) -> HyperliquidReconciliationSnapshot:
    return HyperliquidReconciliationSnapshot(
        account=HyperliquidAccountSnapshot(
            account_value_usd=150.0,
            withdrawable_usd=150.0,
            total_margin_used_usd=4.386 if size else 0.0,
            total_notional_position_usd=abs(size) * 73.10,
            position=_position(size),
        ),
        open_orders=orders,
        fills=fills,
    )


def _stop_fill(oid: int = 202, size: float = 0.30) -> HyperliquidFill:
    return HyperliquidFill(
        oid=oid,
        price=72.5152,
        size=size,
        side="A",
        timestamp_ms=1_785_499_200_123,
        fee_usd=0.0098,
        fee_token="USDC",
        closed_pnl_usd=-0.21,
        crossed=True,
        direction="Close Long",
        transaction_hash="0xstop",
        trade_id=40_202,
    )


def _target_fill(oid: int = 203, size: float = 0.30) -> HyperliquidFill:
    return HyperliquidFill(
        oid=oid,
        price=74.0,
        size=size,
        side="A",
        timestamp_ms=1_785_499_200_123,
        fee_usd=0.0098,
        fee_token="USDC",
        closed_pnl_usd=0.27,
        crossed=False,
        direction="Close Long",
        transaction_hash="0xtarget",
        trade_id=40_203,
    )


def _runtime(tmp_path: Path) -> tuple[AssetEngineConfig, AssetLiveLedger]:
    live_path = engine_ledger_path(tmp_path)
    config = engine_asset_config(live_path)
    ledger = AssetLiveLedger(
        path=live_path,
        profile_id=config.profile_id,
        profile_fingerprint=config.profile_fingerprint,
        run_fingerprint=config.run_fingerprint,
        run_id="run-test",
    )
    return config, ledger


def _now() -> datetime:
    return datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)


def test_entry_is_sized_from_live_equity_then_protected_before_open(
    tmp_path: Path,
) -> None:
    """The engine caps at $22.50 and does not report OPEN before stop visibility."""
    config, ledger = _runtime(tmp_path)
    stop = _order(202, size=0.30, reduce_only=True, trigger=True)
    adapter = FakeVenueAdapter(
        [_venue(0.0), _venue(0.0), _venue(0.30), _venue(0.30, (stop,))]
    )
    engine = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=_now,
    )

    engine.start()
    result = engine.enter(side="long", mark_price=73.0)

    assert result.state is AssetLiveState.OPEN
    assert result.stop_oid == 202
    entry = next(value for name, value in adapter.calls if name == "submit_entry")
    assert isinstance(entry, dict)
    assert entry["requested_notional_usd"] == pytest.approx(22.50)
    records = ledger.read_all()
    intent = next(
        record for record in records if record["event_type"] == "order_intent"
    )
    assert intent["payload"]["client_order_id"] == entry["client_order_id"]
    entry_ack = next(
        record
        for record in records
        if record["event_type"] == "order_acknowledgement"
        and record["payload"].get("operation") == "entry"
    )
    assert entry_ack["payload"]["client_order_id"] == entry["client_order_id"]
    stop_call = next(
        value for name, value in adapter.calls if name == "place_protective_stop"
    )
    assert isinstance(stop_call, dict)
    assert stop_call["position_size_signed"] == pytest.approx(0.30)
    assert stop_call["trigger_price"] == pytest.approx(73.10 * (1.0 - 0.008))


def test_entry_uses_explicit_provider_symbol_sizing_below_asset_ceiling(
    tmp_path: Path,
) -> None:
    """The selected provider policy controls notional without widening authority."""
    config, ledger = _runtime(tmp_path)
    stop = _order(202, size=0.30, reduce_only=True, trigger=True)
    adapter = FakeVenueAdapter(
        [_venue(0.0), _venue(0.0), _venue(0.30), _venue(0.30, (stop,))]
    )
    engine = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=_now,
    )

    engine.start()
    engine.enter(
        side="long",
        mark_price=73.0,
        entry_sizing=CohortEntrySizing(0.06, 20.0),
    )

    entry = next(value for name, value in adapter.calls if name == "submit_entry")
    assert isinstance(entry, dict)
    assert entry["requested_notional_usd"] == pytest.approx(20.0)


def test_reconciliation_retains_venue_maximum_depth_for_telemetry(
    tmp_path: Path,
) -> None:
    """The live journal retains all twenty levels already returned by Hyperliquid."""
    config, ledger = _runtime(tmp_path)
    adapter = FakeVenueAdapter([_venue(0.0), _venue(0.0)])
    engine = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=_now,
    )

    engine.start()
    engine.reconcile_telemetry(
        funding_start_time_ms=1_000,
        funding_end_time_ms=2_000,
    )

    assert ("book_snapshot", 20) in adapter.calls


def test_recorded_provider_plan_controls_stop_and_is_persisted(tmp_path: Path) -> None:
    """A selected range entry uses its 60-bps stop rather than asset fallback."""
    config, ledger = _runtime(tmp_path)
    stop = _order(202, size=0.30, reduce_only=True, trigger=True)
    adapter = FakeVenueAdapter(
        [_venue(0.0), _venue(0.0), _venue(0.30), _venue(0.30, (stop,))]
    )
    engine = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=_now,
    )
    contract = ProviderExecutionContract(
        entry_liquidity="taker_ioc",
        stop_policy="fixed_bps",
        stop_bps=60.0,
        target_policy="none",
        maximum_hold_seconds=172_800,
    )

    engine.start()
    engine.record_strategy_decision(
        {
            "strategy_id": "test_breakout_1m",
            "routing_action": "enter",
            "execution_plan": contract.bind(
                strategy_id="test_breakout_1m",
                stop_anchor=None,
            ).as_payload(),
        }
    )
    result = engine.enter(side="long", mark_price=73.0)

    stop_call = next(
        value for name, value in adapter.calls if name == "place_protective_stop"
    )
    assert isinstance(stop_call, dict)
    assert stop_call["trigger_price"] == pytest.approx(73.10 * (1.0 - 0.006))
    assert result.execution_plan is not None
    assert result.execution_plan.maximum_hold_seconds == 172_800
    states = [
        row["payload"]
        for row in ledger.read_all()
        if row["event_type"] == "state_transition"
    ]
    assert states[-1]["execution_plan"]["strategy_id"] == (
        "test_breakout_1m"
    )


def test_target_plan_places_and_verifies_complete_bracket(tmp_path: Path) -> None:
    """A target-bearing provider reports OPEN only after both legs are visible."""
    config, ledger = _runtime(tmp_path)
    stop = _order(202, size=0.30, reduce_only=True, trigger=True)
    target = _order(
        203,
        size=0.30,
        reduce_only=True,
        trigger=False,
        limit_price=74.74475,
    )
    adapter = FakeVenueAdapter(
        [
            _venue(0.0),
            _venue(0.0),
            _venue(0.30),
            _venue(0.30, (stop,)),
            _venue(0.30, (stop, target)),
        ]
    )
    engine = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=_now,
    )
    plan = ProviderExecutionContract(
        entry_liquidity="taker_ioc",
        stop_policy="fixed_bps",
        stop_bps=75.0,
        target_policy="reward_risk",
        target_r_multiple=3.0,
        maximum_hold_seconds=86_400,
    ).bind(strategy_id="test_strategy", stop_anchor=None)

    engine.start()
    engine.record_strategy_decision(
        {"routing_action": "enter", "execution_plan": plan.as_payload()}
    )
    result = engine.enter(side="long", mark_price=73.0)

    assert result.state is AssetLiveState.OPEN
    assert result.stop_oid == 202
    assert result.target_oid == 203
    target_call = next(
        value for name, value in adapter.calls if name == "submit_target"
    )
    assert isinstance(target_call, dict)
    assert target_call["limit_price"] == pytest.approx(74.74475)


def test_target_fill_cancels_residual_stop_and_journals_exact_exit(
    tmp_path: Path,
) -> None:
    """A filled target cannot leave its sibling stop armed after venue-flat."""
    config, ledger = _runtime(tmp_path)
    stop = _order(202, size=0.30, reduce_only=True, trigger=True)
    target = _order(
        203,
        size=0.30,
        reduce_only=True,
        trigger=False,
        limit_price=74.74475,
    )
    adapter = FakeVenueAdapter(
        [
            _venue(0.0),
            _venue(0.0),
            _venue(0.30),
            _venue(0.30, (stop,)),
            _venue(0.30, (stop, target)),
            _venue(0.0, (stop,), (_target_fill(),)),
            _venue(0.0, (), (_target_fill(),)),
        ]
    )
    engine = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=_now,
        reconciliation_attempts=1,
    )
    plan = ProviderExecutionContract(
        entry_liquidity="taker_ioc",
        stop_policy="fixed_bps",
        stop_bps=75.0,
        target_policy="reward_risk",
        target_r_multiple=3.0,
        maximum_hold_seconds=86_400,
    ).bind(strategy_id="test_strategy", stop_anchor=None)
    engine.start()
    engine.record_strategy_decision({"execution_plan": plan.as_payload()})
    engine.enter(side="long", mark_price=73.0)

    engine.reconcile_telemetry(
        funding_start_time_ms=1_785_495_600_000,
        funding_end_time_ms=1_785_499_200_000,
    )

    assert engine.snapshot.state is AssetLiveState.FLAT
    assert ("cancel_order", 202) in adapter.calls
    closes = [row for row in ledger.read_all() if row["event_type"] == "close"]
    assert closes[-1]["payload"]["reason"] == "target"


def test_scheduled_bracket_exit_keeps_stop_until_position_is_flat(
    tmp_path: Path,
) -> None:
    """The target is canceled first and the stop only after close reconciliation."""
    config, ledger = _runtime(tmp_path)
    stop = _order(202, size=0.30, reduce_only=True, trigger=True)
    target = _order(
        203,
        size=0.30,
        reduce_only=True,
        trigger=False,
        limit_price=74.74475,
    )
    adapter = FakeVenueAdapter(
        [
            _venue(0.0),
            _venue(0.0),
            _venue(0.30),
            _venue(0.30, (stop,)),
            _venue(0.30, (stop, target)),
            _venue(0.30, (stop, target)),
            _venue(0.30, (stop,)),
            _venue(0.0, (stop,)),
            _venue(0.0),
        ]
    )
    engine = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=_now,
        reconciliation_attempts=1,
    )
    plan = ProviderExecutionContract(
        entry_liquidity="taker_ioc",
        stop_policy="fixed_bps",
        stop_bps=75.0,
        target_policy="reward_risk",
        target_r_multiple=3.0,
        maximum_hold_seconds=86_400,
    ).bind(strategy_id="test_strategy", stop_anchor=None)
    engine.start()
    engine.record_strategy_decision({"execution_plan": plan.as_payload()})
    engine.enter(side="long", mark_price=73.0)

    result = engine.exit(mark_price=73.2, reason="maximum_hold_seconds")

    assert result.state is AssetLiveState.FLAT
    operations = [name for name, _ in adapter.calls]
    target_cancel = next(
        index
        for index, item in enumerate(adapter.calls)
        if item == ("cancel_order", 203)
    )
    close = operations.index("close_position")
    stop_cancel = next(
        index
        for index, item in enumerate(adapter.calls)
        if item == ("cancel_order", 202)
    )
    assert target_cancel < close < stop_cancel


def test_entry_and_stop_reconciliation_tolerate_bounded_stale_reads(
    tmp_path: Path,
) -> None:
    """One stale post-write read cannot trigger an unnecessary emergency close."""
    config, ledger = _runtime(tmp_path)
    stop = _order(202, size=0.30, reduce_only=True, trigger=True)
    adapter = FakeVenueAdapter(
        [
            _venue(0.0),
            _venue(0.0),
            _venue(0.0),
            _venue(0.30),
            _venue(0.30),
            _venue(0.30, (stop,)),
        ]
    )
    delays: list[float] = []
    engine = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=_now,
        reconciliation_attempts=3,
        reconciliation_delay_seconds=0.01,
        sleep_fn=delays.append,
    )

    engine.start()
    result = engine.enter(side="long", mark_price=73.0)

    assert result.state is AssetLiveState.OPEN
    assert result.stop_oid == 202
    assert delays == [0.01, 0.01]
    assert not any(name == "close_position" for name, _ in adapter.calls)


def test_partial_fill_cancels_only_residual_entry_then_protects_actual_size(
    tmp_path: Path,
) -> None:
    """Protection is sized from clearinghouse exposure, not requested quantity."""
    config, ledger = _runtime(tmp_path)
    residual = _order(101, size=0.10, reduce_only=False, trigger=False)
    stop = _order(202, size=0.20, reduce_only=True, trigger=True)
    adapter = FakeVenueAdapter(
        [
            _venue(0.0),
            _venue(0.0),
            _venue(0.20, (residual,)),
            _venue(0.20, (stop,)),
        ]
    )
    adapter.entry_ack = HyperliquidOrderAck(True, 101, "resting")
    engine = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=_now,
    )

    engine.start()
    result = engine.enter(side="long", mark_price=73.0)

    assert result.state is AssetLiveState.OPEN
    assert ("cancel_order", 101) in adapter.calls
    stop_call = next(
        value for name, value in adapter.calls if name == "place_protective_stop"
    )
    assert isinstance(stop_call, dict)
    assert stop_call["position_size_signed"] == pytest.approx(0.20)
    assert not any(name == "cancel_all" for name, _ in adapter.calls)


def test_ioc_no_match_reconciles_flat_without_faulting_the_engine(
    tmp_path: Path,
) -> None:
    """A definitive IOC no-fill must release the slot and remain nonfatal."""
    config, ledger = _runtime(tmp_path)
    adapter = FakeVenueAdapter([_venue(0.0), _venue(0.0), _venue(0.0)])
    adapter.entry_ack = HyperliquidOrderAck(
        False,
        None,
        "error",
        error="Order could not immediately match against any resting orders. asset=214",
    )
    engine = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=_now,
    )

    engine.start()
    with pytest.raises(AssetEntryNotFilledError, match="IOC entry not filled"):
        engine.enter(side="long", mark_price=73.0)

    assert engine.snapshot.state is AssetLiveState.FLAT
    records = ledger.read_all()
    assert any(row["event_type"] == "entry_not_filled" for row in records)
    assert not any(row["event_type"] == "fault" for row in records)


def test_stop_rejection_emergency_closes_reconciles_flat_and_faults(
    tmp_path: Path,
) -> None:
    """An unprotected fill is flattened rather than left live."""
    config, ledger = _runtime(tmp_path)
    adapter = FakeVenueAdapter([_venue(0.0), _venue(0.0), _venue(0.30), _venue(0.0)])
    adapter.stop_ack = HyperliquidOrderAck(
        False,
        None,
        "error",
        error="trigger rejected",
    )
    engine = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=_now,
    )

    engine.start()
    with pytest.raises(AssetLiveEngineError, match="protective stop rejected"):
        engine.enter(side="long", mark_price=73.0)

    assert engine.snapshot.state is AssetLiveState.FAULTED
    assert any(name == "close_position" for name, _ in adapter.calls)
    events = [record["event_type"] for record in ledger.read_all()]
    assert "fault" in events


def test_exact_stop_cancel_reduce_only_close_and_flat_before_next_entry(
    tmp_path: Path,
) -> None:
    """Normal exit cancels only owned protection and verifies venue flat."""
    config, ledger = _runtime(tmp_path)
    stop = _order(202, size=0.30, reduce_only=True, trigger=True)
    adapter = FakeVenueAdapter(
        [
            _venue(0.0),
            _venue(0.0),
            _venue(0.30),
            _venue(0.30, (stop,)),
            _venue(0.30, (stop,)),
            _venue(0.0, (stop,)),
            _venue(0.0),
        ]
    )
    engine = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=_now,
    )

    engine.start()
    engine.enter(side="long", mark_price=73.0)
    result = engine.exit(mark_price=73.2, reason="signal_exit")

    assert result.state is AssetLiveState.FLAT
    assert ("cancel_order", 202) in adapter.calls
    assert any(name == "close_position" for name, _ in adapter.calls)
    assert [name for name, _ in adapter.calls].index("close_position") < (
        adapter.calls.index(("cancel_order", 202))
    )
    close_records = [
        record for record in ledger.read_all() if record["event_type"] == "close"
    ]
    assert any(
        record["payload"].get("reason") == "signal_exit"
        and record["payload"].get("intent") is True
        for record in close_records
    )


def test_lost_entry_stop_and_close_responses_recover_without_resubmission(
    tmp_path: Path,
) -> None:
    """Exact CLOIDs recover one full lifecycle after committed response loss."""
    config, ledger = _runtime(tmp_path)
    stop = _order(202, size=0.30, reduce_only=True, trigger=True)
    adapter = FakeVenueAdapter(
        [
            _venue(0.0),
            _venue(0.0),
            _venue(0.30),
            _venue(0.30, (stop,)),
            _venue(0.30, (stop,)),
            _venue(0.0),
        ]
    )
    adapter.response_loss = {"entry", "protective_stop", "reduce_only_close"}
    identities = iter(
        (
            "0x11111111111111111111111111111111",
            "0x22222222222222222222222222222222",
            "0x33333333333333333333333333333333",
        )
    )
    engine = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=_now,
        client_order_id_fn=lambda: next(identities),
    )

    engine.start()
    engine.enter(side="long", mark_price=73.0)
    result = engine.exit(mark_price=73.2, reason="signal_exit")

    assert result.state is AssetLiveState.FLAT
    assert sum(name == "submit_entry" for name, _ in adapter.calls) == 1
    assert sum(name == "place_protective_stop" for name, _ in adapter.calls) == 1
    assert sum(name == "close_position" for name, _ in adapter.calls) == 1
    assert sum(name == "order_status_by_client_id" for name, _ in adapter.calls) == 3
    recovered = [
        record
        for record in ledger.read_all()
        if record["event_type"] in {"order_acknowledgement", "stop_order", "close"}
        and record["payload"].get("recovered_after_transport_error") is True
    ]
    assert len(recovered) == 3


def test_lost_stop_response_that_filled_immediately_confirms_flat(
    tmp_path: Path,
) -> None:
    """An immediate owned native-stop fill does not submit a duplicate close."""
    config, ledger = _runtime(tmp_path)
    adapter = FakeVenueAdapter(
        [
            _venue(0.0),
            _venue(0.0),
            _venue(0.30),
            _venue(0.0, fills=(_stop_fill(),)),
        ]
    )
    adapter.stop_ack = HyperliquidOrderAck(True, 202, "filled", 0.30, 72.5152)
    adapter.response_loss = {"protective_stop"}
    identities = iter(
        (
            "0x11111111111111111111111111111111",
            "0x22222222222222222222222222222222",
        )
    )
    engine = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=_now,
        reconciliation_attempts=1,
        client_order_id_fn=lambda: next(identities),
    )

    engine.start()
    result = engine.enter(side="long", mark_price=73.0)

    assert result.state is AssetLiveState.FLAT
    assert not any(name == "close_position" for name, _ in adapter.calls)
    closes = [record for record in ledger.read_all() if record["event_type"] == "close"]
    assert closes[-1]["payload"]["reason"] == "protective_stop_during_protection"


def test_restart_restores_only_ledger_owned_position_and_stop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Known protected exposure resumes without submitting or changing leverage."""
    config, ledger = _runtime(tmp_path)
    ledger.append(
        event_type="state_transition",
        observed_at_utc="2026-07-31T11:59:00+00:00",
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={
            "state": "OPEN",
            "entry_oid": 101,
            "stop_oid": 202,
            "close_oid": None,
            "position_size_signed": -0.30,
            "opened_at_ms": 1_785_495_600_000,
        },
    )
    stop = _order(202, size=0.30, reduce_only=True, trigger=True, side="B")
    adapter = FakeVenueAdapter([_venue(-0.30, (stop,))])
    engine = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=_now,
    )
    monkeypatch.setattr(
        ledger,
        "read_all",
        lambda: pytest.fail("startup recovery must stream profile history"),
    )

    result = engine.start()

    assert result.state is AssetLiveState.OPEN
    assert result.position_size_signed == pytest.approx(-0.30)
    assert not any(name.startswith("submit") for name, _ in adapter.calls)
    assert not any(name == "configure_isolated_leverage" for name, _ in adapter.calls)


def test_restart_rejects_foreign_profile_ownership_before_venue_mutation(
    tmp_path: Path,
) -> None:
    """A new profile cannot adopt a protected position recorded by its predecessor."""
    config, ledger = _runtime(tmp_path)
    prior = AssetLiveLedger(
        path=ledger.path,
        profile_id="prior-profile",
        profile_fingerprint="b" * 64,
        run_fingerprint="c" * 64,
        run_id="prior-run",
    )
    prior.append(
        event_type="state_transition",
        observed_at_utc="2026-07-31T11:59:00+00:00",
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={
            "state": "OPEN",
            "entry_oid": 101,
            "stop_oid": 202,
            "position_size_signed": -0.30,
            "opened_at_ms": 1_785_495_600_000,
        },
    )
    ledger = AssetLiveLedger(
        path=ledger.path,
        profile_id=config.profile_id,
        profile_fingerprint=config.profile_fingerprint,
        run_fingerprint=config.run_fingerprint,
        run_id="current-run",
    )
    stop = _order(202, size=0.30, reduce_only=True, trigger=True, side="B")
    adapter = FakeVenueAdapter([_venue(-0.30, (stop,))])
    engine = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=_now,
    )

    with pytest.raises(AssetLiveEngineError, match="without local ownership"):
        engine.start()

    mutations = {
        "configure_isolated_leverage",
        "submit_entry",
        "place_protective_stop",
        "place_target",
        "cancel_order",
        "close_position",
    }
    assert not any(name in mutations for name, _ in adapter.calls)


def test_restart_restores_open_provider_execution_plan(tmp_path: Path) -> None:
    """Stable restart retains the entry's exact stop and hold contract."""
    config, ledger = _runtime(tmp_path)
    plan = ProviderExecutionContract(
        entry_liquidity="taker_ioc",
        stop_policy="fixed_bps",
        stop_bps=60.0,
        target_policy="none",
        maximum_hold_seconds=172_800,
    ).bind(strategy_id="range", stop_anchor=None)
    ledger.append(
        event_type="state_transition",
        observed_at_utc="2026-07-31T11:59:00+00:00",
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={
            "state": "OPEN",
            "entry_oid": 101,
            "stop_oid": 202,
            "position_size_signed": 0.30,
            "opened_at_ms": 1_785_495_600_000,
            "execution_plan": plan.as_payload(),
        },
    )
    stop = _order(202, size=0.30, reduce_only=True, trigger=True)
    engine = AssetLiveEngine(
        config=config,
        adapter=FakeVenueAdapter([_venue(0.30, (stop,))]),
        ledger=ledger,
        credentials_present=True,
        now_fn=_now,
    )

    result = engine.start()

    assert result.execution_plan == plan


def test_restart_restores_exact_open_target_bracket(tmp_path: Path) -> None:
    """Restart adopts both owned legs without submitting or canceling orders."""
    config, ledger = _runtime(tmp_path)
    plan = ProviderExecutionContract(
        entry_liquidity="taker_ioc",
        stop_policy="fixed_bps",
        stop_bps=75.0,
        target_policy="reward_risk",
        target_r_multiple=3.0,
        maximum_hold_seconds=86_400,
    ).bind(strategy_id="test_strategy", stop_anchor=None)
    ledger.append(
        event_type="state_transition",
        observed_at_utc="2026-07-31T11:59:00+00:00",
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={
            "state": "OPEN",
            "entry_oid": 101,
            "stop_oid": 202,
            "target_oid": 203,
            "target_price": 74.0,
            "position_size_signed": 0.30,
            "opened_at_ms": 1_785_495_600_000,
            "execution_plan": plan.as_payload(),
        },
    )
    stop = _order(202, size=0.30, reduce_only=True, trigger=True)
    target = _order(
        203,
        size=0.30,
        reduce_only=True,
        trigger=False,
        limit_price=74.0,
    )
    adapter = FakeVenueAdapter([_venue(0.30, (stop, target))])
    engine = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=_now,
    )

    result = engine.start()

    assert result.state is AssetLiveState.OPEN
    assert result.target_oid == 203
    assert not any(name.startswith("submit") for name, _ in adapter.calls)
    assert not any(name == "cancel_order" for name, _ in adapter.calls)


def test_restart_cleans_residual_stop_after_target_fill(tmp_path: Path) -> None:
    """Stable OPEN recovery attributes a target fill and removes its sibling."""
    config, ledger = _runtime(tmp_path)
    plan = ProviderExecutionContract(
        entry_liquidity="taker_ioc",
        stop_policy="fixed_bps",
        stop_bps=75.0,
        target_policy="reward_risk",
        target_r_multiple=3.0,
        maximum_hold_seconds=86_400,
    ).bind(strategy_id="test_strategy", stop_anchor=None)
    ledger.append(
        event_type="state_transition",
        observed_at_utc="2026-07-31T11:59:00+00:00",
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={
            "state": "OPEN",
            "entry_oid": 101,
            "stop_oid": 202,
            "target_oid": 203,
            "target_price": 74.0,
            "position_size_signed": 0.30,
            "opened_at_ms": 1_785_495_600_000,
            "execution_plan": plan.as_payload(),
        },
    )
    stop = _order(202, size=0.30, reduce_only=True, trigger=True)
    adapter = FakeVenueAdapter([_venue(0.0, (stop,), (_target_fill(),)), _venue(0.0)])
    engine = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=_now,
        reconciliation_attempts=1,
    )

    result = engine.start()

    assert result.state is AssetLiveState.FLAT
    assert ("cancel_order", 202) in adapter.calls
    closes = [row for row in ledger.read_all() if row["event_type"] == "close"]
    assert closes[-1]["payload"]["reason"] == "target"


def test_restart_recovers_committed_target_without_resubmission(tmp_path: Path) -> None:
    """A target response-loss window adopts its CLOID and exact venue bracket."""
    config, ledger = _runtime(tmp_path)
    plan = ProviderExecutionContract(
        entry_liquidity="taker_ioc",
        stop_policy="fixed_bps",
        stop_bps=75.0,
        target_policy="reward_risk",
        target_r_multiple=3.0,
        maximum_hold_seconds=86_400,
    ).bind(strategy_id="test_strategy", stop_anchor=None)
    target_client_id = "0x33333333333333333333333333333333"
    ledger.append(
        event_type="state_transition",
        observed_at_utc="2026-07-31T11:59:00+00:00",
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={
            "state": "TARGET_PENDING",
            "entry_oid": 101,
            "stop_oid": 202,
            "target_oid": None,
            "target_price": 74.0,
            "position_size_signed": 0.30,
            "opened_at_ms": 1_785_495_600_000,
            "execution_plan": plan.as_payload(),
        },
    )
    ledger.append(
        event_type="order_intent",
        observed_at_utc="2026-07-31T11:59:01+00:00",
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={
            "operation": "target",
            "client_order_id": target_client_id,
            "position_size_signed": 0.30,
            "limit_price": 74.0,
        },
    )
    stop = _order(202, size=0.30, reduce_only=True, trigger=True)
    target = _order(
        203,
        size=0.30,
        reduce_only=True,
        trigger=False,
        limit_price=74.0,
    )
    adapter = FakeVenueAdapter([_venue(0.30, (stop, target))])
    adapter.client_statuses[target_client_id] = HyperliquidOrderStatus(
        203,
        "SOL",
        "open",
        0.30,
        1_785_495_600_123,
        target_client_id,
    )
    engine = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=_now,
    )

    result = engine.start()

    assert result.state is AssetLiveState.OPEN
    assert result.target_oid == 203
    assert not any(name == "submit_target" for name, _ in adapter.calls)


def test_restart_adopts_bracket_after_false_target_visibility_fault(
    tmp_path: Path,
) -> None:
    """A known stale-read fault adopts the exact acknowledged target and stop."""
    config, ledger = _runtime(tmp_path)
    plan = ProviderExecutionContract(
        entry_liquidity="taker_ioc",
        stop_policy="fixed_bps",
        stop_bps=75.0,
        target_policy="reward_risk",
        target_r_multiple=3.0,
        maximum_hold_seconds=86_400,
    ).bind(strategy_id="test_strategy", stop_anchor=None)
    target_client_id = "0x33333333333333333333333333333333"
    common = {
        "entry_oid": 101,
        "stop_oid": 202,
        "target_oid": None,
        "target_price": 74.0,
        "position_size_signed": 0.30,
        "opened_at_ms": 1_785_495_600_000,
        "execution_plan": plan.as_payload(),
    }
    ledger.append(
        event_type="state_transition",
        observed_at_utc="2026-07-31T11:59:00+00:00",
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={"state": "TARGET_PENDING", **common},
    )
    ledger.append(
        event_type="order_intent",
        observed_at_utc="2026-07-31T11:59:01+00:00",
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={
            "operation": "target",
            "client_order_id": target_client_id,
            "position_size_signed": 0.30,
            "limit_price": 74.0,
        },
    )
    ledger.append(
        event_type="target_order",
        observed_at_utc="2026-07-31T11:59:02+00:00",
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={
            "operation": "target",
            "client_order_id": target_client_id,
            "accepted": True,
            "oid": 203,
        },
    )
    ledger.append(
        event_type="fault",
        observed_at_utc="2026-07-31T11:59:03+00:00",
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={
            "reason": "target acknowledged but complete bracket is not venue-visible"
        },
    )
    ledger.append(
        event_type="state_transition",
        observed_at_utc="2026-07-31T11:59:04+00:00",
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={"state": "FAULTED", **common},
    )
    stop = _order(202, size=0.30, reduce_only=True, trigger=True)
    target = _order(
        203,
        size=0.30,
        reduce_only=True,
        trigger=False,
        limit_price=74.0,
    )
    adapter = FakeVenueAdapter([_venue(0.30, (stop, target))])
    adapter.client_statuses[target_client_id] = HyperliquidOrderStatus(
        203,
        "SOL",
        "open",
        0.30,
        1_785_495_600_123,
        target_client_id,
    )
    engine = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=_now,
    )

    result = engine.start()

    assert result.state is AssetLiveState.OPEN
    assert result.stop_oid == 202
    assert result.target_oid == 203
    assert not any(name == "submit_target" for name, _ in adapter.calls)
    assert ("order_status_by_client_id", target_client_id) in adapter.calls


def test_restart_recovers_committed_entry_intent_then_places_protection(
    tmp_path: Path,
) -> None:
    """A crash after entry commit adopts its CLOID and protects actual exposure."""
    config, ledger = _runtime(tmp_path)
    entry_client_id = "0x11111111111111111111111111111111"
    stop_client_id = "0x22222222222222222222222222222222"
    ledger.append(
        event_type="state_transition",
        observed_at_utc="2026-07-31T11:59:00+00:00",
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={
            "state": "ENTRY_PENDING",
            "entry_oid": None,
            "stop_oid": None,
            "close_oid": None,
            "position_size_signed": 0.0,
            "opened_at_ms": None,
            "last_fault": None,
            "stop_reason": None,
        },
    )
    ledger.append(
        event_type="order_intent",
        observed_at_utc="2026-07-31T11:59:01+00:00",
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={
            "operation": "entry",
            "client_order_id": entry_client_id,
            "side": "long",
            "requested_notional_usd": 22.50,
            "mark_price": 73.0,
        },
    )
    stop = _order(202, size=0.30, reduce_only=True, trigger=True)
    adapter = FakeVenueAdapter([_venue(0.30), _venue(0.30, (stop,))])
    adapter.client_statuses[entry_client_id] = HyperliquidOrderStatus(
        101,
        "SOL",
        "filled",
        0.30,
        1_785_495_600_123,
        entry_client_id,
    )
    engine = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=_now,
        client_order_id_fn=lambda: stop_client_id,
    )

    result = engine.start()

    assert result.state is AssetLiveState.OPEN
    assert result.entry_oid == 101
    assert result.stop_oid == 202
    assert not any(name == "submit_entry" for name, _ in adapter.calls)
    assert ("order_status_by_client_id", entry_client_id) in adapter.calls
    assert sum(name == "place_protective_stop" for name, _ in adapter.calls) == 1


def test_restart_recovers_entry_after_ack_but_before_protection(tmp_path: Path) -> None:
    """The ack-to-protection crash window recovers by the original entry CLOID."""
    config, ledger = _runtime(tmp_path)
    entry_client_id = "0x11111111111111111111111111111111"
    stop_client_id = "0x22222222222222222222222222222222"
    ledger.append(
        event_type="state_transition",
        observed_at_utc="2026-07-31T11:59:00+00:00",
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={"state": "ENTRY_PENDING", "position_size_signed": 0.0},
    )
    ledger.append(
        event_type="order_intent",
        observed_at_utc="2026-07-31T11:59:01+00:00",
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={
            "operation": "entry",
            "client_order_id": entry_client_id,
            "side": "long",
            "requested_notional_usd": 22.50,
            "mark_price": 73.0,
        },
    )
    ledger.append(
        event_type="order_acknowledgement",
        observed_at_utc="2026-07-31T11:59:02+00:00",
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={
            "operation": "entry",
            "client_order_id": entry_client_id,
            "accepted": True,
            "oid": 101,
        },
    )
    stop = _order(202, size=0.30, reduce_only=True, trigger=True)
    adapter = FakeVenueAdapter([_venue(0.30), _venue(0.30, (stop,))])
    adapter.client_statuses[entry_client_id] = HyperliquidOrderStatus(
        101, "SOL", "filled", 0.30, 1_785_495_600_123, entry_client_id
    )
    engine = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=_now,
        client_order_id_fn=lambda: stop_client_id,
    )

    result = engine.start()

    assert result.state is AssetLiveState.OPEN
    assert result.stop_oid == 202
    assert not any(name == "submit_entry" for name, _ in adapter.calls)


def test_restart_places_stop_when_crash_preceded_stop_intent(tmp_path: Path) -> None:
    """Known exposure in PROTECTING is re-protected exactly once on startup."""
    config, ledger = _runtime(tmp_path)
    stop_client_id = "0x22222222222222222222222222222222"
    ledger.append(
        event_type="state_transition",
        observed_at_utc="2026-07-31T11:59:00+00:00",
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={
            "state": "PROTECTING",
            "entry_oid": 101,
            "stop_oid": None,
            "position_size_signed": 0.30,
            "opened_at_ms": 1_785_495_600_123,
        },
    )
    stop = _order(202, size=0.30, reduce_only=True, trigger=True)
    adapter = FakeVenueAdapter([_venue(0.30), _venue(0.30, (stop,))])
    engine = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=_now,
        client_order_id_fn=lambda: stop_client_id,
    )

    result = engine.start()

    assert result.state is AssetLiveState.OPEN
    assert result.stop_oid == 202
    assert sum(name == "place_protective_stop" for name, _ in adapter.calls) == 1
    assert not any(name == "submit_entry" for name, _ in adapter.calls)


def test_restart_abandons_entry_state_when_no_intent_was_committed(
    tmp_path: Path,
) -> None:
    """A verified-flat pre-intent crash safely returns the sole slot to FLAT."""
    config, ledger = _runtime(tmp_path)
    ledger.append(
        event_type="state_transition",
        observed_at_utc="2026-07-31T11:59:00+00:00",
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={"state": "ENTRY_PENDING", "position_size_signed": 0.0},
    )
    adapter = FakeVenueAdapter([_venue(0.0)])
    engine = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=_now,
    )

    result = engine.start()

    assert result.state is AssetLiveState.FLAT
    assert not any(name == "submit_entry" for name, _ in adapter.calls)


def test_restart_recovers_committed_protective_stop_without_replacing_it(
    tmp_path: Path,
) -> None:
    """A crash after stop commit adopts that exact native protection."""
    config, ledger = _runtime(tmp_path)
    stop_client_id = "0x22222222222222222222222222222222"
    ledger.append(
        event_type="state_transition",
        observed_at_utc="2026-07-31T11:59:00+00:00",
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={
            "state": "PROTECTING",
            "entry_oid": 101,
            "stop_oid": None,
            "close_oid": None,
            "position_size_signed": 0.30,
            "opened_at_ms": 1_785_495_600_123,
        },
    )
    ledger.append(
        event_type="order_intent",
        observed_at_utc="2026-07-31T11:59:01+00:00",
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={
            "operation": "protective_stop",
            "client_order_id": stop_client_id,
            "position_size_signed": 0.30,
            "trigger_price": 72.5152,
        },
    )
    stop = _order(202, size=0.30, reduce_only=True, trigger=True)
    adapter = FakeVenueAdapter([_venue(0.30, (stop,))])
    adapter.client_statuses[stop_client_id] = HyperliquidOrderStatus(
        202,
        "SOL",
        "open",
        0.30,
        1_785_495_600_123,
        stop_client_id,
    )
    engine = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=_now,
    )

    result = engine.start()

    assert result.state is AssetLiveState.OPEN
    assert result.entry_oid == 101
    assert result.stop_oid == 202
    assert not any(name == "place_protective_stop" for name, _ in adapter.calls)
    assert ("order_status_by_client_id", stop_client_id) in adapter.calls


def test_restart_replaces_committed_stop_that_was_rejected(tmp_path: Path) -> None:
    """A definitively rejected stop is replaced without duplicating the entry."""
    config, ledger = _runtime(tmp_path)
    rejected_client_id = "0x22222222222222222222222222222222"
    replacement_client_id = "0x44444444444444444444444444444444"
    ledger.append(
        event_type="state_transition",
        observed_at_utc="2026-07-31T11:59:00+00:00",
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={
            "state": "PROTECTING",
            "entry_oid": 101,
            "position_size_signed": 0.30,
            "opened_at_ms": 1_785_495_600_123,
        },
    )
    ledger.append(
        event_type="order_intent",
        observed_at_utc="2026-07-31T11:59:01+00:00",
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={
            "operation": "protective_stop",
            "client_order_id": rejected_client_id,
            "position_size_signed": 0.30,
            "trigger_price": 72.5152,
        },
    )
    replacement = _order(404, size=0.30, reduce_only=True, trigger=True)
    adapter = FakeVenueAdapter([_venue(0.30), _venue(0.30, (replacement,))])
    adapter.stop_ack = HyperliquidOrderAck(True, 404, "resting")
    adapter.client_statuses[rejected_client_id] = HyperliquidOrderStatus(
        202, "SOL", "rejected", 0.30, 1_785_499_200_123, rejected_client_id
    )
    engine = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=_now,
        client_order_id_fn=lambda: replacement_client_id,
    )

    result = engine.start()

    assert result.state is AssetLiveState.OPEN
    assert result.stop_oid == 404
    assert not any(name == "submit_entry" for name, _ in adapter.calls)
    assert sum(name == "place_protective_stop" for name, _ in adapter.calls) == 1


def test_restart_recognizes_committed_stop_that_filled_during_crash(
    tmp_path: Path,
) -> None:
    """Exact stop fill recovery returns FLAT without emergency close."""
    config, ledger = _runtime(tmp_path)
    stop_client_id = "0x22222222222222222222222222222222"
    ledger.append(
        event_type="state_transition",
        observed_at_utc="2026-07-31T11:59:00+00:00",
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={
            "state": "PROTECTING",
            "entry_oid": 101,
            "stop_oid": None,
            "position_size_signed": 0.30,
            "opened_at_ms": 1_785_495_600_123,
        },
    )
    ledger.append(
        event_type="order_intent",
        observed_at_utc="2026-07-31T11:59:01+00:00",
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={
            "operation": "protective_stop",
            "client_order_id": stop_client_id,
            "position_size_signed": 0.30,
            "trigger_price": 72.5152,
        },
    )
    adapter = FakeVenueAdapter([_venue(0.0, fills=(_stop_fill(),))])
    adapter.client_statuses[stop_client_id] = HyperliquidOrderStatus(
        202,
        "SOL",
        "filled",
        0.30,
        1_785_499_200_123,
        stop_client_id,
    )
    engine = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=_now,
    )

    result = engine.start()

    assert result.state is AssetLiveState.FLAT
    assert not any(name == "close_position" for name, _ in adapter.calls)
    closes = [row for row in ledger.read_all() if row["event_type"] == "close"]
    assert closes[-1]["payload"]["reason"] == "protective_stop_during_protection"


def test_restart_recovers_committed_close_without_resubmission(tmp_path: Path) -> None:
    """A filled close cleans its still-armed owned stop after restart."""
    config, ledger = _runtime(tmp_path)
    close_client_id = "0x33333333333333333333333333333333"
    ledger.append(
        event_type="state_transition",
        observed_at_utc="2026-07-31T11:59:00+00:00",
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={
            "state": "EXIT_PENDING",
            "entry_oid": 101,
            "stop_oid": 202,
            "close_oid": None,
            "position_size_signed": 0.30,
            "opened_at_ms": 1_785_495_600_123,
        },
    )
    ledger.append(
        event_type="order_intent",
        observed_at_utc="2026-07-31T11:59:01+00:00",
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={
            "operation": "reduce_only_close",
            "client_order_id": close_client_id,
            "position_size_signed": 0.30,
            "mark_price": 73.0,
        },
    )
    stop = _order(202, size=0.30, reduce_only=True, trigger=True)
    adapter = FakeVenueAdapter([_venue(0.0, (stop,)), _venue(0.0)])
    adapter.client_statuses[close_client_id] = HyperliquidOrderStatus(
        303,
        "SOL",
        "filled",
        0.30,
        1_785_499_200_123,
        close_client_id,
    )
    engine = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=_now,
        reconciliation_attempts=1,
    )

    result = engine.start()

    assert result.state is AssetLiveState.FLAT
    assert ("order_status_by_client_id", close_client_id) in adapter.calls
    assert ("cancel_order", 202) in adapter.calls
    assert not any(name == "close_position" for name, _ in adapter.calls)


def test_restart_cleans_residual_stop_after_filled_bracket_close(
    tmp_path: Path,
) -> None:
    """A recovered filled close cancels only its known residual stop."""
    config, ledger = _runtime(tmp_path)
    close_client_id = "0x33333333333333333333333333333333"
    plan = ProviderExecutionContract(
        entry_liquidity="taker_ioc",
        stop_policy="fixed_bps",
        stop_bps=75.0,
        target_policy="reward_risk",
        target_r_multiple=3.0,
        maximum_hold_seconds=86_400,
    ).bind(strategy_id="test_strategy", stop_anchor=None)
    ledger.append(
        event_type="state_transition",
        observed_at_utc="2026-07-31T11:59:00+00:00",
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={
            "state": "EXIT_PENDING",
            "entry_oid": 101,
            "stop_oid": 202,
            "target_oid": 203,
            "target_price": 74.0,
            "position_size_signed": 0.30,
            "opened_at_ms": 1_785_495_600_123,
            "execution_plan": plan.as_payload(),
        },
    )
    ledger.append(
        event_type="order_intent",
        observed_at_utc="2026-07-31T11:59:01+00:00",
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={
            "operation": "reduce_only_close",
            "client_order_id": close_client_id,
            "position_size_signed": 0.30,
            "mark_price": 73.0,
        },
    )
    stop = _order(202, size=0.30, reduce_only=True, trigger=True)
    adapter = FakeVenueAdapter([_venue(0.0, (stop,)), _venue(0.0)])
    adapter.client_statuses[close_client_id] = HyperliquidOrderStatus(
        303,
        "SOL",
        "filled",
        0.30,
        1_785_499_200_123,
        close_client_id,
    )
    engine = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=_now,
        reconciliation_attempts=1,
    )

    result = engine.start()

    assert result.state is AssetLiveState.FLAT
    assert ("cancel_order", 202) in adapter.calls
    assert not any(name == "close_position" for name, _ in adapter.calls)


def test_restart_restores_target_after_exit_crash_before_close_intent(
    tmp_path: Path,
) -> None:
    """A stop-only crash window restores the missing target before OPEN."""
    config, ledger = _runtime(tmp_path)
    plan = ProviderExecutionContract(
        entry_liquidity="taker_ioc",
        stop_policy="fixed_bps",
        stop_bps=75.0,
        target_policy="reward_risk",
        target_r_multiple=3.0,
        maximum_hold_seconds=86_400,
    ).bind(strategy_id="test_strategy", stop_anchor=None)
    ledger.append(
        event_type="state_transition",
        observed_at_utc="2026-07-31T11:59:00+00:00",
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={
            "state": "EXIT_PENDING",
            "entry_oid": 101,
            "stop_oid": 202,
            "target_oid": 203,
            "target_price": 74.0,
            "position_size_signed": 0.30,
            "opened_at_ms": 1_785_495_600_123,
            "execution_plan": plan.as_payload(),
        },
    )
    stop = _order(202, size=0.30, reduce_only=True, trigger=True)
    replacement = _order(
        404,
        size=0.30,
        reduce_only=True,
        trigger=False,
        limit_price=74.0,
    )
    adapter = FakeVenueAdapter([_venue(0.30, (stop,)), _venue(0.30, (stop, replacement))])
    adapter.target_ack = HyperliquidOrderAck(True, 404, "resting")
    engine = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=_now,
        reconciliation_attempts=1,
    )

    result = engine.start()

    assert result.state is AssetLiveState.OPEN
    assert result.stop_oid == 202
    assert result.target_oid == 404
    assert sum(name == "submit_target" for name, _ in adapter.calls) == 1
    assert not any(name == "close_position" for name, _ in adapter.calls)


def test_restart_restores_target_after_bracket_close_rejection(
    tmp_path: Path,
) -> None:
    """A rejected committed close restores the missing target under the stop."""
    config, ledger = _runtime(tmp_path)
    close_client_id = "0x33333333333333333333333333333333"
    plan = ProviderExecutionContract(
        entry_liquidity="taker_ioc",
        stop_policy="fixed_bps",
        stop_bps=75.0,
        target_policy="reward_risk",
        target_r_multiple=3.0,
        maximum_hold_seconds=86_400,
    ).bind(strategy_id="test_strategy", stop_anchor=None)
    ledger.append(
        event_type="state_transition",
        observed_at_utc="2026-07-31T11:59:00+00:00",
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={
            "state": "EXIT_PENDING",
            "entry_oid": 101,
            "stop_oid": 202,
            "target_oid": 203,
            "target_price": 74.0,
            "position_size_signed": 0.30,
            "opened_at_ms": 1_785_495_600_123,
            "execution_plan": plan.as_payload(),
        },
    )
    ledger.append(
        event_type="order_intent",
        observed_at_utc="2026-07-31T11:59:01+00:00",
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={
            "operation": "reduce_only_close",
            "client_order_id": close_client_id,
            "position_size_signed": 0.30,
            "mark_price": 73.0,
        },
    )
    stop = _order(202, size=0.30, reduce_only=True, trigger=True)
    target = _order(
        404,
        size=0.30,
        reduce_only=True,
        trigger=False,
        limit_price=74.0,
    )
    adapter = FakeVenueAdapter([_venue(0.30, (stop,)), _venue(0.30, (stop, target))])
    adapter.target_ack = HyperliquidOrderAck(True, 404, "resting")
    adapter.client_statuses[close_client_id] = HyperliquidOrderStatus(
        303,
        "SOL",
        "rejected",
        0.30,
        1_785_499_200_123,
        close_client_id,
    )
    engine = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=_now,
        reconciliation_attempts=1,
    )

    result = engine.start()

    assert result.state is AssetLiveState.OPEN
    assert result.stop_oid == 202
    assert result.target_oid == 404
    assert sum(name == "submit_target" for name, _ in adapter.calls) == 1
    assert not any(name == "close_position" for name, _ in adapter.calls)


def test_restart_reprotects_after_committed_close_was_canceled(tmp_path: Path) -> None:
    """A definitively canceled close cannot leave the remaining position naked."""
    config, ledger = _runtime(tmp_path)
    close_client_id = "0x33333333333333333333333333333333"
    replacement_client_id = "0x44444444444444444444444444444444"
    ledger.append(
        event_type="state_transition",
        observed_at_utc="2026-07-31T11:59:00+00:00",
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={
            "state": "EXIT_PENDING",
            "entry_oid": 101,
            "stop_oid": 202,
            "position_size_signed": 0.30,
            "opened_at_ms": 1_785_495_600_123,
        },
    )
    ledger.append(
        event_type="order_intent",
        observed_at_utc="2026-07-31T11:59:01+00:00",
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={
            "operation": "reduce_only_close",
            "client_order_id": close_client_id,
            "position_size_signed": 0.30,
            "mark_price": 73.0,
        },
    )
    replacement = _order(404, size=0.30, reduce_only=True, trigger=True)
    adapter = FakeVenueAdapter([_venue(0.30), _venue(0.30, (replacement,))])
    adapter.stop_ack = HyperliquidOrderAck(True, 404, "resting")
    adapter.client_statuses[close_client_id] = HyperliquidOrderStatus(
        303, "SOL", "canceled", 0.30, 1_785_499_200_123, close_client_id
    )
    engine = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=_now,
        client_order_id_fn=lambda: replacement_client_id,
    )

    result = engine.start()

    assert result.state is AssetLiveState.OPEN
    assert result.stop_oid == 404
    assert not any(name == "close_position" for name, _ in adapter.calls)
    assert sum(name == "place_protective_stop" for name, _ in adapter.calls) == 1


def test_restart_restores_open_when_exit_crashed_before_stop_cancel(
    tmp_path: Path,
) -> None:
    """EXIT_PENDING with the exact old stop still active safely resumes OPEN."""
    config, ledger = _runtime(tmp_path)
    ledger.append(
        event_type="state_transition",
        observed_at_utc="2026-07-31T11:59:00+00:00",
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={
            "state": "EXIT_PENDING",
            "entry_oid": 101,
            "stop_oid": 202,
            "position_size_signed": 0.30,
            "opened_at_ms": 1_785_495_600_123,
        },
    )
    stop = _order(202, size=0.30, reduce_only=True, trigger=True)
    adapter = FakeVenueAdapter([_venue(0.30, (stop,))])
    engine = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=_now,
    )

    result = engine.start()

    assert result.state is AssetLiveState.OPEN
    assert result.stop_oid == 202
    assert not any(
        name in {"cancel_order", "close_position", "place_protective_stop"}
        for name, _ in adapter.calls
    )


def test_restart_reprotects_when_exit_crashed_after_stop_cancel(tmp_path: Path) -> None:
    """An unprotected EXIT_PENDING position receives exactly one replacement stop."""
    config, ledger = _runtime(tmp_path)
    replacement_client_id = "0x44444444444444444444444444444444"
    ledger.append(
        event_type="state_transition",
        observed_at_utc="2026-07-31T11:59:00+00:00",
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={
            "state": "EXIT_PENDING",
            "entry_oid": 101,
            "stop_oid": 202,
            "position_size_signed": 0.30,
            "opened_at_ms": 1_785_495_600_123,
        },
    )
    replacement = _order(404, size=0.30, reduce_only=True, trigger=True)
    adapter = FakeVenueAdapter([_venue(0.30), _venue(0.30, (replacement,))])
    adapter.stop_ack = HyperliquidOrderAck(True, 404, "resting")
    engine = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=_now,
        client_order_id_fn=lambda: replacement_client_id,
    )

    result = engine.start()

    assert result.state is AssetLiveState.OPEN
    assert result.stop_oid == 404
    assert sum(name == "place_protective_stop" for name, _ in adapter.calls) == 1
    assert not any(name == "close_position" for name, _ in adapter.calls)


def test_unknown_startup_exposure_faults_without_mutating_venue(tmp_path: Path) -> None:
    """No ledger ownership means the engine may observe but not guess or cancel."""
    config, ledger = _runtime(tmp_path)
    unknown_stop = _order(999, size=0.30, reduce_only=True, trigger=True)
    adapter = FakeVenueAdapter([_venue(0.30, (unknown_stop,))])
    engine = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=_now,
    )

    with pytest.raises(AssetLiveEngineError, match="unknown venue exposure"):
        engine.start()

    assert engine.snapshot.state is AssetLiveState.FAULTED
    assert not any(
        name in {"cancel_order", "close_position", "submit_entry"}
        for name, _ in adapter.calls
    )


def test_shutdown_while_open_preserves_stop_and_records_stopped(tmp_path: Path) -> None:
    """Operator shutdown leaves venue-native protection in force."""
    config, ledger = _runtime(tmp_path)
    stop = _order(202, size=0.30, reduce_only=True, trigger=True)
    adapter = FakeVenueAdapter(
        [_venue(0.0), _venue(0.0), _venue(0.30), _venue(0.30, (stop,))]
    )
    engine = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=_now,
    )
    engine.start()
    engine.enter(side="long", mark_price=73.0)

    result = engine.stop("operator_stop")

    assert result.state is AssetLiveState.STOPPED
    assert result.stop_oid == 202
    assert not any(name == "cancel_order" for name, _ in adapter.calls)


def test_wrong_direction_fill_is_emergency_closed_before_fault(tmp_path: Path) -> None:
    """An unexpected opposite exposure is not left unprotected at the venue."""
    config, ledger = _runtime(tmp_path)
    adapter = FakeVenueAdapter([_venue(0.0), _venue(0.0), _venue(-0.30), _venue(0.0)])
    engine = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=_now,
    )

    engine.start()
    with pytest.raises(AssetLiveEngineError, match="direction mismatch"):
        engine.enter(side="long", mark_price=73.0)

    assert engine.snapshot.state is AssetLiveState.FAULTED
    assert any(name == "close_position" for name, _ in adapter.calls)


def test_close_rejection_retains_original_stop_and_restores_open(
    tmp_path: Path,
) -> None:
    """A rejected exit leaves the original stop armed and resumes OPEN."""
    config, ledger = _runtime(tmp_path)
    stop = _order(202, size=0.30, reduce_only=True, trigger=True)
    adapter = FakeVenueAdapter(
        [
            _venue(0.0),
            _venue(0.0),
            _venue(0.30),
            _venue(0.30, (stop,)),
            _venue(0.30, (stop,)),
            _venue(0.30, (stop,)),
        ]
    )
    adapter.close_ack = HyperliquidOrderAck(
        False,
        None,
        "error",
        error="close rejected",
    )
    engine = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=_now,
    )
    engine.start()
    engine.enter(side="long", mark_price=73.0)

    result = engine.exit(mark_price=73.2, reason="signal_exit")

    assert result.state is AssetLiveState.OPEN
    assert result.stop_oid == 202
    assert adapter.reconciliations == []
    assert sum(name == "place_protective_stop" for name, _ in adapter.calls) == 1
    assert not any(name == "cancel_order" for name, _ in adapter.calls)


def test_missing_stop_after_rejected_close_is_replaced(tmp_path: Path) -> None:
    """A rejected close cannot leave unexplained residual exposure naked."""
    config, ledger = _runtime(tmp_path)
    stop = _order(202, size=0.30, reduce_only=True, trigger=True)
    replacement = _order(204, size=0.30, reduce_only=True, trigger=True)
    adapter = FakeVenueAdapter(
        [
            _venue(0.0),
            _venue(0.0),
            _venue(0.30),
            _venue(0.30, (stop,)),
            _venue(0.30, (stop,)),
            _venue(0.30),
            _venue(0.30, (replacement,)),
        ]
    )
    adapter.close_ack = HyperliquidOrderAck(
        False, None, "error", error="close rejected"
    )
    engine = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=_now,
        reconciliation_attempts=1,
    )
    engine.start()
    engine.enter(side="long", mark_price=73.0)
    adapter.stop_ack = HyperliquidOrderAck(True, 204, "resting")

    result = engine.exit(mark_price=73.2, reason="signal_exit")

    assert result.state is AssetLiveState.OPEN
    assert result.stop_oid == 204
    assert sum(name == "place_protective_stop" for name, _ in adapter.calls) == 2
    assert not any(name == "cancel_order" for name, _ in adapter.calls)


def test_unverified_replacement_stop_faults_instead_of_restoring_open(
    tmp_path: Path,
) -> None:
    """A replacement acknowledgement alone cannot claim venue protection."""
    config, ledger = _runtime(tmp_path)
    stop = _order(202, size=0.30, reduce_only=True, trigger=True)
    adapter = FakeVenueAdapter(
        [
            _venue(0.0),
            _venue(0.0),
            _venue(0.30),
            _venue(0.30, (stop,)),
            _venue(0.30, (stop,)),
            _venue(0.30),
            _venue(0.30),
        ]
    )
    adapter.close_ack = HyperliquidOrderAck(
        False, None, "error", error="close rejected"
    )
    engine = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=_now,
        reconciliation_attempts=1,
    )
    engine.start()
    engine.enter(side="long", mark_price=73.0)
    adapter.stop_ack = HyperliquidOrderAck(True, 204, "resting")

    with pytest.raises(AssetLiveEngineError, match="requires exactly its owned stop"):
        engine.exit(mark_price=73.2, reason="signal_exit")

    assert engine.snapshot.state is AssetLiveState.FAULTED
    assert sum(name == "place_protective_stop" for name, _ in adapter.calls) == 2


def test_lost_residual_cancel_response_recovers_oid_after_close(
    tmp_path: Path,
) -> None:
    """A lost residual-stop cancel is recovered only after the close."""
    config, ledger = _runtime(tmp_path)
    stop = _order(202, size=0.30, reduce_only=True, trigger=True)
    adapter = FakeVenueAdapter(
        [
            _venue(0.0),
            _venue(0.0),
            _venue(0.30),
            _venue(0.30, (stop,)),
            _venue(0.30, (stop,)),
            _venue(0.0, (stop,)),
            _venue(0.0),
        ]
    )
    adapter.cancel_response_loss = True
    adapter.oid_statuses[202] = HyperliquidOrderStatus(
        202, "SOL", "canceled", 0.30, 1_785_499_200_123
    )
    engine = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=_now,
        reconciliation_attempts=1,
    )
    engine.start()
    engine.enter(side="long", mark_price=73.0)

    result = engine.exit(mark_price=73.2, reason="signal_exit")

    assert result.state is AssetLiveState.FLAT
    assert sum(name == "cancel_order" for name, _ in adapter.calls) == 1
    assert ("order_status", 202) in adapter.calls
    assert sum(name == "close_position" for name, _ in adapter.calls) == 1
    assert [name for name, _ in adapter.calls].index("close_position") < (
        adapter.calls.index(("cancel_order", 202))
    )


def test_original_stop_fill_during_rejected_exit_confirms_flat(tmp_path: Path) -> None:
    """An original-stop fill during a rejected close resolves exact FLAT."""
    config, ledger = _runtime(tmp_path)
    stop = _order(202, size=0.30, reduce_only=True, trigger=True)
    adapter = FakeVenueAdapter(
        [
            _venue(0.0),
            _venue(0.0),
            _venue(0.30),
            _venue(0.30, (stop,)),
            _venue(0.30, (stop,)),
            _venue(0.0, fills=(_stop_fill(oid=202),)),
        ]
    )
    adapter.close_ack = HyperliquidOrderAck(
        False,
        None,
        "error",
        error="close rejected",
    )
    engine = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=_now,
        reconciliation_attempts=1,
    )
    engine.start()
    engine.enter(side="long", mark_price=73.0)
    result = engine.exit(mark_price=73.2, reason="signal_exit")

    assert result.state is AssetLiveState.FLAT
    closes = [row for row in ledger.read_all() if row["event_type"] == "close"]
    assert closes[-1]["payload"]["reason"] == ("protective_stop_during_rejected_exit")


def test_monitoring_reconciles_flat_and_records_exact_funding(tmp_path: Path) -> None:
    """Ongoing telemetry uses account funding ledger updates, not estimates."""
    config, ledger = _runtime(tmp_path)
    adapter = FakeVenueAdapter([_venue(0.0), _venue(0.0)])
    adapter.funding = (
        HyperliquidFundingPayment(
            1_785_499_200_068,
            -0.001234,
            0.30,
            0.000056,
            "0xfunding",
        ),
    )
    engine = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=_now,
    )
    engine.start()

    venue = engine.reconcile_telemetry(
        funding_start_time_ms=1_785_495_600_000,
        funding_end_time_ms=1_785_499_300_000,
    )

    assert venue.is_flat is True
    records = ledger.read_all()
    funding = [record for record in records if record["event_type"] == "funding"]
    assert len(funding) == 1


def test_monitoring_retries_one_stale_missing_stop_before_faulting(
    tmp_path: Path,
) -> None:
    """Continuous monitoring tolerates bounded venue read-after-write lag."""
    config, ledger = _runtime(tmp_path)
    stop = _order(202, size=0.30, reduce_only=True, trigger=True)
    adapter = FakeVenueAdapter(
        [
            _venue(0.0),
            _venue(0.0),
            _venue(0.30),
            _venue(0.30, (stop,)),
            _venue(0.30),
            _venue(0.30, (stop,)),
        ]
    )
    delays: list[float] = []
    engine = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=_now,
        reconciliation_attempts=3,
        reconciliation_delay_seconds=0.01,
        sleep_fn=delays.append,
    )
    engine.start()
    engine.enter(side="long", mark_price=73.0)

    venue = engine.reconcile_telemetry(
        funding_start_time_ms=1_785_495_600_000,
        funding_end_time_ms=1_785_499_300_000,
    )

    assert venue.position.size_signed == pytest.approx(0.30)
    assert engine.snapshot.state is AssetLiveState.OPEN
    assert delays == [0.01]


def test_monitoring_confirms_exact_native_stop_fill_as_flat(tmp_path: Path) -> None:
    """The owned protective stop fill closes the lifecycle without a false fault."""
    config, ledger = _runtime(tmp_path)
    stop = _order(202, size=0.30, reduce_only=True, trigger=True)
    adapter = FakeVenueAdapter(
        [
            _venue(0.0),
            _venue(0.0),
            _venue(0.30),
            _venue(0.30, (stop,)),
            _venue(0.0, fills=(_stop_fill(),)),
        ]
    )
    engine = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=_now,
        sleep_fn=lambda _: None,
    )
    engine.start()
    engine.enter(side="long", mark_price=73.0)

    engine.reconcile_telemetry(
        funding_start_time_ms=1_785_495_600_000,
        funding_end_time_ms=1_785_499_300_000,
    )

    assert engine.snapshot.state is AssetLiveState.FLAT
    records = ledger.read_all()
    closes = [record for record in records if record["event_type"] == "close"]
    assert closes[-1]["payload"]["reason"] == "protective_stop"
    assert closes[-1]["payload"]["oid"] == 202


def test_restart_recovers_exact_native_stop_fill_as_flat(tmp_path: Path) -> None:
    """Restart converts prior OPEN to FLAT only with the exact owned stop fill."""
    config, ledger = _runtime(tmp_path)
    ledger.append(
        event_type="state_transition",
        observed_at_utc="2026-07-31T11:59:00+00:00",
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={
            "state": "OPEN",
            "entry_oid": 101,
            "stop_oid": 202,
            "close_oid": None,
            "position_size_signed": 0.30,
            "opened_at_ms": 1_785_495_600_000,
            "last_fault": None,
            "stop_reason": None,
        },
    )
    adapter = FakeVenueAdapter([_venue(0.0, fills=(_stop_fill(),))])
    engine = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=_now,
    )

    result = engine.start()

    assert result.state is AssetLiveState.FLAT
    closes = [record for record in ledger.read_all() if record["event_type"] == "close"]
    assert closes[-1]["payload"]["reason"] == "protective_stop_restart_recovery"

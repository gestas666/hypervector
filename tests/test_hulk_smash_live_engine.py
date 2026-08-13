from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
import json
from pathlib import Path

import pandas as pd
import pytest

from hypervector.live.hulk_smash_live_config import load_hulk_smash_live_config
from hypervector.live.hulk_smash_live_decisions import HulkSmashLiveDecision
from hypervector.live.hulk_smash_live_engine import (
    HulkSmashLiveEngine,
    HulkSmashLiveEngineError,
)
from hypervector.live.hulk_smash_live_ledger import HulkSmashLiveLedger
from hypervector.live.hulk_smash_live_models import (
    HulkSmashLiveSnapshot,
    HulkSmashLiveState,
)
from hypervector.live.hyperliquid_protocol import (
    HyperliquidFeeSchedule,
    HyperliquidOrderAck,
    HyperliquidOrderStatus,
    SolAccountSnapshot,
    SolBookLevel,
    SolBookSnapshot,
    SolFill,
    SolMarketMetadata,
    SolOpenOrder,
    SolPositionSnapshot,
    SolReconciliationSnapshot,
    SolVenuePreflight,
)
from hypervector.live.hyperliquid_sol_parsing import (
    HyperliquidOrderUnavailableError,
)
from hypervector.live.sol_order_transport import (
    SolCancelTransportError,
    SolOrderTransportError,
)


class FakeAdapter:
    def __init__(self, snapshots: list[SolReconciliationSnapshot]) -> None:
        self.snapshots = snapshots
        self.calls: list[tuple[str, object]] = []
        self.stop_ack = _ack(201)
        self.target_ack = _ack(202)
        self.close_ack = _ack(203)
        self.stop_transport_error = False
        self.entry_transport_error = False
        self.close_transport_error = False
        self.cancel_transport_error = False
        self.status_unavailable = False

    def preflight(self, *, expected_max_leverage: int) -> SolVenuePreflight:
        self.calls.append(("preflight", expected_max_leverage))
        return _preflight(self.snapshots[0].position)

    def configure_isolated_leverage(self, leverage: int) -> None:
        self.calls.append(("leverage", leverage))

    def reconcile(self) -> SolReconciliationSnapshot:
        self.calls.append(("reconcile", None))
        if len(self.snapshots) > 1:
            return self.snapshots.pop(0)
        return self.snapshots[0]

    def book_snapshot(self, *, depth_levels: int) -> SolBookSnapshot:
        self.calls.append(("book", depth_levels))
        return _book()

    def funding_payments(self, **kwargs: int) -> tuple[object, ...]:
        self.calls.append(("funding", kwargs))
        return ()

    def submit_market_entry(self, **kwargs: object) -> HyperliquidOrderAck:
        self.calls.append(("market_entry", kwargs))
        if self.entry_transport_error:
            raise SolOrderTransportError(
                operation="entry",
                client_order_id=str(kwargs["client_order_id"]),
                detail="response and status unavailable",
            )
        return replace(_ack(101), client_order_id=str(kwargs["client_order_id"]))

    def place_protective_stop(self, **kwargs: object) -> HyperliquidOrderAck:
        self.calls.append(("stop", kwargs))
        identity = str(kwargs["client_order_id"])
        if self.stop_transport_error:
            raise SolOrderTransportError(
                operation="protective_stop",
                client_order_id=identity,
                detail="response lost",
            )
        return replace(self.stop_ack, client_order_id=identity)

    def submit_target(self, **kwargs: object) -> HyperliquidOrderAck:
        self.calls.append(("target", kwargs))
        return replace(
            self.target_ack,
            client_order_id=str(kwargs["client_order_id"]),
        )

    def cancel_order(self, oid: int) -> HyperliquidOrderAck:
        self.calls.append(("cancel", oid))
        if self.cancel_transport_error:
            raise SolCancelTransportError(
                operation="cancel_order",
                oid=oid,
                detail="response lost",
            )
        return _ack(oid)

    def close_position(self, **kwargs: object) -> HyperliquidOrderAck:
        self.calls.append(("close", kwargs))
        identity = str(kwargs["client_order_id"])
        if self.close_transport_error:
            raise SolOrderTransportError(
                operation="reduce_only_close",
                client_order_id=identity,
                detail="response lost",
            )
        return replace(
            self.close_ack,
            client_order_id=identity,
        )

    def order_status_by_client_id(self, client_order_id: str) -> HyperliquidOrderStatus:
        self.calls.append(("status_by_client_id", client_order_id))
        if self.status_unavailable:
            raise HyperliquidOrderUnavailableError("status endpoint unavailable")
        close = client_order_id.endswith("04")
        return HyperliquidOrderStatus(
            203 if close else 201,
            "BTC",
            "filled" if close else "open",
            0.75,
            2,
            client_order_id,
        )

    def order_status(self, oid: int) -> HyperliquidOrderStatus:
        self.calls.append(("order_status", oid))
        if self.status_unavailable:
            raise HyperliquidOrderUnavailableError("status endpoint unavailable")
        return HyperliquidOrderStatus(oid, "BTC", "canceled", 0.0, 2)


def test_hulk_engine_enters_short_and_verifies_both_native_exits(
    tmp_path: Path,
) -> None:
    flat = _venue(_position())
    opened = _venue(_position(size=-0.75, entry=100.0))
    stopped = _venue(
        _position(size=-0.75, entry=100.0),
        orders=(_stop_order(),),
    )
    bracketed = _venue(
        _position(size=-0.75, entry=100.0),
        orders=(_stop_order(), _target_order()),
    )
    adapter = FakeAdapter([flat, flat, opened, stopped, bracketed])
    engine = _engine(tmp_path, adapter)

    assert engine.start().state is HulkSmashLiveState.FLAT
    snapshot = engine.enter(_decision())

    assert snapshot.state is HulkSmashLiveState.OPEN
    assert snapshot.entry_oid == 101
    assert snapshot.stop_oid == 201
    assert snapshot.target_oid == 202
    assert snapshot.stop_price == pytest.approx(100.5)
    assert snapshot.target_price == pytest.approx(98.5)
    market = next(payload for name, payload in adapter.calls if name == "market_entry")
    assert isinstance(market, dict)
    assert market["side"] == "short"
    assert market["requested_notional_usd"] == pytest.approx(75.0)
    assert ("leverage", 5) in adapter.calls
    ledger_path = tmp_path / "data/live/hulk_smash/decisions.jsonl"
    records = [json.loads(line) for line in ledger_path.read_text().splitlines()]
    acknowledgements = [
        row
        for row in records
        if row["event_type"] in {"order_acknowledgement", "stop_order", "target_order"}
    ]
    assert acknowledgements
    assert all(row["payload"]["round_trip_latency_ms"] == 0 for row in acknowledgements)


def test_hulk_engine_persists_tick_normalized_venue_bracket_prices(
    tmp_path: Path,
) -> None:
    flat = _venue(_position())
    opened = _venue(_position(size=-0.75, entry=100.0))
    venue_stop = replace(_stop_order(), trigger_price=101.0)
    venue_target = replace(_target_order(), limit_price=98.0)
    stopped = _venue(
        _position(size=-0.75, entry=100.0),
        orders=(venue_stop,),
    )
    bracketed = _venue(
        _position(size=-0.75, entry=100.0),
        orders=(venue_stop, venue_target),
    )
    adapter = FakeAdapter([flat, flat, opened, stopped, bracketed])
    engine = _engine(tmp_path, adapter)
    engine.start()

    snapshot = engine.enter(_decision())

    assert snapshot.stop_price == pytest.approx(101.0)
    assert snapshot.target_price == pytest.approx(98.0)


def test_hulk_engine_cancels_residual_stop_after_verified_target_fill(
    tmp_path: Path,
) -> None:
    flat = _venue(_position())
    opened = _venue(_position(size=-0.75, entry=100.0))
    stopped = _venue(_position(size=-0.75, entry=100.0), orders=(_stop_order(),))
    bracketed = _venue(
        _position(size=-0.75, entry=100.0),
        orders=(_stop_order(), _target_order()),
    )
    adapter = FakeAdapter([flat, flat, opened, stopped, bracketed])
    engine = _engine(tmp_path, adapter)
    engine.start()
    engine.enter(_decision())
    target_fill = _fill(202, "Close Short")
    adapter.snapshots = [
        _venue(_position(), orders=(_stop_order(),), fills=(target_fill,)),
        _venue(_position(), fills=(target_fill,)),
    ]

    snapshot = engine.poll_market()

    assert snapshot.state is HulkSmashLiveState.FLAT
    assert ("cancel", 201) in adapter.calls
    assert engine.last_close_reason == "target"


def test_hulk_engine_recovers_lost_residual_cancel_response(tmp_path: Path) -> None:
    adapter, engine = _entered_engine(tmp_path)
    adapter.cancel_transport_error = True
    target_fill = _fill(202, "Close Short")
    adapter.snapshots = [
        _venue(_position(), orders=(_stop_order(),), fills=(target_fill,)),
        _venue(_position(), fills=(target_fill,)),
    ]

    snapshot = engine.poll_market()

    assert snapshot.state is HulkSmashLiveState.FLAT
    assert ("order_status", 201) in adapter.calls


def test_hulk_engine_cancels_residual_target_after_verified_stop_fill(
    tmp_path: Path,
) -> None:
    adapter, engine = _entered_engine(tmp_path)
    stop_fill = _fill(201, "Close Short")
    adapter.snapshots = [
        _venue(_position(), orders=(_target_order(),), fills=(stop_fill,)),
        _venue(_position(), fills=(stop_fill,)),
    ]

    snapshot = engine.poll_market()

    assert snapshot.state is HulkSmashLiveState.FLAT
    assert ("cancel", 202) in adapter.calls
    assert engine.last_close_reason == "protective_stop"


def test_hulk_engine_stops_polling_after_bracket_recovery_finds_target_fill(
    tmp_path: Path,
) -> None:
    adapter, engine = _entered_engine(tmp_path)
    target_fill = _fill(202, "Close Short")
    adapter.snapshots = [
        _venue(_position(size=-0.75, entry=100.0), orders=(_stop_order(),)),
        _venue(_position(), orders=(_stop_order(),), fills=(target_fill,)),
        _venue(_position(), fills=(target_fill,)),
    ]

    snapshot = engine.poll_market()

    assert snapshot.state is HulkSmashLiveState.FLAT
    assert engine.last_close_reason == "target"
    assert not any(record[0] == "close" for record in adapter.calls)


def test_hulk_engine_closes_at_maximum_hold_after_cancelling_bracket(
    tmp_path: Path,
) -> None:
    now = [datetime(2026, 8, 1, 12, tzinfo=UTC)]
    adapter, engine = _entered_engine(tmp_path, now_fn=lambda: now[0])
    now[0] = now[0].replace(day=2, hour=13)
    adapter.snapshots = [
        _venue(
            _position(size=-0.75, entry=100.0),
            orders=(_stop_order(), _target_order()),
        ),
        _venue(_position(size=-0.75, entry=100.0), orders=(_stop_order(),)),
        _venue(_position(), orders=(_stop_order(),)),
        _venue(_position()),
    ]

    snapshot = engine.poll_market()

    assert snapshot.state is HulkSmashLiveState.FLAT
    assert engine.last_close_reason == "maximum_hold"
    assert ("cancel", 201) in adapter.calls
    assert ("cancel", 202) in adapter.calls
    assert any(name == "close" for name, _ in adapter.calls)


def test_hulk_engine_recovers_lost_maximum_hold_close_response(
    tmp_path: Path,
) -> None:
    now = [datetime(2026, 8, 1, 12, tzinfo=UTC)]
    adapter, engine = _entered_engine(tmp_path, now_fn=lambda: now[0])
    adapter.close_transport_error = True
    now[0] = now[0].replace(day=2, hour=13)
    adapter.snapshots = [
        _venue(
            _position(size=-0.75, entry=100.0),
            orders=(_stop_order(), _target_order()),
        ),
        _venue(_position(size=-0.75, entry=100.0), orders=(_stop_order(),)),
        _venue(_position(), orders=(_stop_order(),)),
        _venue(_position()),
    ]

    snapshot = engine.poll_market()

    assert snapshot.state is HulkSmashLiveState.FLAT
    assert engine.last_close_reason == "maximum_hold"
    assert any(name == "status_by_client_id" for name, _ in adapter.calls)


def test_hulk_engine_confirms_flat_after_close_status_remains_unavailable(
    tmp_path: Path,
) -> None:
    now = [datetime(2026, 8, 1, 12, tzinfo=UTC)]
    adapter, engine = _entered_engine(tmp_path, now_fn=lambda: now[0])
    adapter.close_transport_error = True
    adapter.status_unavailable = True
    now[0] = now[0].replace(day=2, hour=13)
    adapter.snapshots = [
        _venue(
            _position(size=-0.75, entry=100.0),
            orders=(_stop_order(), _target_order()),
        ),
        _venue(_position(size=-0.75, entry=100.0), orders=(_stop_order(),)),
        _venue(_position(), orders=(_stop_order(),)),
        _venue(_position()),
    ]

    snapshot = engine.poll_market()

    assert snapshot.state is HulkSmashLiveState.FLAT
    assert engine.last_close_reason == "maximum_hold"
    assert ("cancel", 202) in adapter.calls
    assert ("cancel", 201) in adapter.calls


def test_hulk_engine_keeps_stop_when_ambiguous_close_remains_open(
    tmp_path: Path,
) -> None:
    now = [datetime(2026, 8, 1, 12, tzinfo=UTC)]
    adapter, engine = _entered_engine(tmp_path, now_fn=lambda: now[0])
    adapter.close_transport_error = True
    adapter.status_unavailable = True
    now[0] = now[0].replace(day=2, hour=13)
    protected = _venue(
        _position(size=-0.75, entry=100.0),
        orders=(_stop_order(),),
    )
    adapter.snapshots = [
        _venue(
            _position(size=-0.75, entry=100.0),
            orders=(_stop_order(), _target_order()),
        ),
        protected,
        protected,
        protected,
    ]

    with pytest.raises(HulkSmashLiveEngineError, match="protected exposure"):
        engine.poll_market()

    assert engine.snapshot.state is HulkSmashLiveState.FAULTED
    assert ("cancel", 202) in adapter.calls
    assert ("cancel", 201) not in adapter.calls


def test_hulk_engine_faults_safely_when_target_cancel_is_ambiguous(
    tmp_path: Path,
) -> None:
    now = [datetime(2026, 8, 1, 12, tzinfo=UTC)]
    adapter, engine = _entered_engine(tmp_path, now_fn=lambda: now[0])
    adapter.cancel_transport_error = True
    adapter.status_unavailable = True
    now[0] = now[0].replace(day=2, hour=13)
    adapter.snapshots = [
        _venue(
            _position(size=-0.75, entry=100.0),
            orders=(_stop_order(), _target_order()),
        )
    ]

    with pytest.raises(HulkSmashLiveEngineError, match="cancel_target_for_close"):
        engine.poll_market()

    assert engine.snapshot.state is HulkSmashLiveState.FAULTED
    assert ("cancel", 201) not in adapter.calls


def test_hulk_engine_flattens_exposure_after_ambiguous_entry(
    tmp_path: Path,
) -> None:
    flat = _venue(_position())
    exposed = _venue(_position(size=-0.75, entry=100.0))
    adapter = FakeAdapter([flat, flat, exposed, _venue(_position())])
    adapter.entry_transport_error = True
    adapter.status_unavailable = True
    engine = _engine(tmp_path, adapter)
    engine.start()

    with pytest.raises(HulkSmashLiveEngineError, match="ambiguous entry"):
        engine.enter(_decision())

    assert engine.snapshot.state is HulkSmashLiveState.FAULTED
    assert any(name == "close" for name, _ in adapter.calls)


def test_hulk_engine_retries_ambiguous_unprotected_emergency_close(
    tmp_path: Path,
) -> None:
    flat = _venue(_position())
    opened = _venue(_position(size=-0.75, entry=100.0))
    adapter = FakeAdapter([flat, flat, opened, opened, opened, flat])
    adapter.stop_ack = HyperliquidOrderAck(False, None, "rejected", error="bad stop")
    adapter.close_transport_error = True
    adapter.status_unavailable = True
    engine = _engine(tmp_path, adapter)
    engine.start()

    with pytest.raises(HulkSmashLiveEngineError, match="protective stop rejected"):
        engine.enter(_decision())

    assert engine.snapshot.state is HulkSmashLiveState.FAULTED
    assert sum(name == "close" for name, _ in adapter.calls) == 2


def test_hulk_engine_reports_unprotected_exposure_after_close_retries(
    tmp_path: Path,
) -> None:
    flat = _venue(_position())
    opened = _venue(_position(size=-0.75, entry=100.0))
    adapter = FakeAdapter([flat, flat, opened, opened, opened, opened, opened])
    adapter.stop_ack = HyperliquidOrderAck(False, None, "rejected", error="bad stop")
    adapter.close_transport_error = True
    adapter.status_unavailable = True
    engine = _engine(tmp_path, adapter)
    engine.start()

    with pytest.raises(HulkSmashLiveEngineError, match="unprotected exposure"):
        engine.enter(_decision())

    assert engine.snapshot.state is HulkSmashLiveState.FAULTED
    assert sum(name == "close" for name, _ in adapter.calls) == 2


def test_hulk_engine_emergency_flattens_when_stop_is_rejected(tmp_path: Path) -> None:
    flat = _venue(_position())
    opened = _venue(_position(size=-0.75, entry=100.0))
    adapter = FakeAdapter([flat, flat, opened, _venue(_position())])
    adapter.stop_ack = HyperliquidOrderAck(False, None, "rejected", error="bad stop")
    engine = _engine(tmp_path, adapter)
    engine.start()

    with pytest.raises(HulkSmashLiveEngineError, match="protective stop rejected"):
        engine.enter(_decision())

    assert engine.snapshot.state is HulkSmashLiveState.FAULTED
    assert any(name == "close" for name, _ in adapter.calls)


def test_hulk_engine_emergency_flattens_when_postfill_risk_is_invalid(
    tmp_path: Path,
) -> None:
    flat = _venue(_position())
    opened = _venue(_position(size=-0.75, entry=100.0))
    invalid = replace(
        opened,
        account=replace(opened.account, account_value_usd=0.0),
    )
    adapter = FakeAdapter([flat, flat, invalid, _venue(_position())])
    engine = _engine(tmp_path, adapter)
    engine.start()

    with pytest.raises(HulkSmashLiveEngineError, match="postfill risk plan invalid"):
        engine.enter(_decision())

    assert engine.snapshot.state is HulkSmashLiveState.FAULTED
    assert any(name == "close" for name, _ in adapter.calls)


def test_hulk_engine_recovers_lost_stop_response_by_exact_client_id(
    tmp_path: Path,
) -> None:
    flat = _venue(_position())
    opened = _venue(_position(size=-0.75, entry=100.0))
    stopped = _venue(_position(size=-0.75, entry=100.0), orders=(_stop_order(),))
    bracketed = _venue(
        _position(size=-0.75, entry=100.0),
        orders=(_stop_order(), _target_order()),
    )
    adapter = FakeAdapter([flat, flat, opened, stopped, bracketed])
    adapter.stop_transport_error = True
    engine = _engine(tmp_path, adapter)
    engine.start()

    snapshot = engine.enter(_decision())

    assert snapshot.state is HulkSmashLiveState.OPEN
    assert snapshot.stop_oid == 201
    assert any(name == "status_by_client_id" for name, _ in adapter.calls)


def test_hulk_engine_emergency_flattens_when_stop_never_becomes_visible(
    tmp_path: Path,
) -> None:
    flat = _venue(_position())
    opened = _venue(_position(size=-0.75, entry=100.0))
    adapter = FakeAdapter([flat, flat, opened, opened, opened, flat])
    engine = _engine(tmp_path, adapter)
    engine.start()

    with pytest.raises(HulkSmashLiveEngineError, match="not venue-visible"):
        engine.enter(_decision())

    assert engine.snapshot.state is HulkSmashLiveState.FAULTED
    assert ("cancel", 201) not in adapter.calls
    assert any(name == "close" for name, _ in adapter.calls)


def test_hulk_engine_faults_when_accepted_entry_is_not_venue_confirmed(
    tmp_path: Path,
) -> None:
    flat = _venue(_position())
    adapter = FakeAdapter([flat, flat, flat, flat, flat])
    engine = _engine(tmp_path, adapter)
    engine.start()

    with pytest.raises(HulkSmashLiveEngineError, match="not venue-confirmed"):
        engine.enter(_decision())

    assert engine.snapshot.state is HulkSmashLiveState.FAULTED
    assert not any(name == "close" for name, _ in adapter.calls)


def test_hulk_engine_handles_stop_fill_before_target_submission(tmp_path: Path) -> None:
    flat = _venue(_position())
    opened = _venue(_position(size=-0.75, entry=100.0))
    stopped_out = _venue(_position(), fills=(_fill(201, "Close Short"),))
    adapter = FakeAdapter([flat, flat, opened, stopped_out])
    engine = _engine(tmp_path, adapter)
    engine.start()

    snapshot = engine.enter(_decision())

    assert snapshot.state is HulkSmashLiveState.FLAT
    assert engine.last_close_reason == "protective_stop"
    assert not any(name == "target" for name, _ in adapter.calls)


def test_hulk_engine_handles_target_fill_during_bracket_reconciliation(
    tmp_path: Path,
) -> None:
    flat = _venue(_position())
    opened = _venue(_position(size=-0.75, entry=100.0))
    stopped = _venue(_position(size=-0.75, entry=100.0), orders=(_stop_order(),))
    target_fill = _fill(202, "Close Short")
    target_hit = _venue(
        _position(),
        orders=(_stop_order(),),
        fills=(target_fill,),
    )
    cleared = _venue(_position(), fills=(target_fill,))
    adapter = FakeAdapter([flat, flat, opened, stopped, target_hit, cleared])
    engine = _engine(tmp_path, adapter)
    engine.start()

    snapshot = engine.enter(_decision())

    assert snapshot.state is HulkSmashLiveState.FLAT
    assert engine.last_close_reason == "target"
    assert ("cancel", 201) in adapter.calls


def test_hulk_engine_refuses_unowned_restart_exposure(tmp_path: Path) -> None:
    exposed = _venue(
        _position(size=-0.75, entry=100.0),
        orders=(_stop_order(), _target_order()),
    )
    adapter = FakeAdapter([exposed])
    engine = _engine(tmp_path, adapter)

    with pytest.raises(HulkSmashLiveEngineError, match="unowned BTC exposure"):
        engine.start()

    assert not any(
        name in {"market_entry", "stop", "target"} for name, _ in adapter.calls
    )


@pytest.mark.parametrize("durable_state", ["OPEN", "STOPPED"])
def test_hulk_engine_restores_exact_owned_bracket(
    tmp_path: Path,
    durable_state: str,
) -> None:
    exposed = _venue(
        _position(size=-0.75, entry=100.0),
        orders=(_stop_order(), _target_order()),
    )
    adapter = FakeAdapter([exposed])
    prior = HulkSmashLiveSnapshot(
        state=HulkSmashLiveState[durable_state],
        entry_oid=101,
        stop_oid=201,
        target_oid=202,
        position_size_signed=-0.75,
        opened_at_ms=1_785_549_600_000,
        entry_price=100.0,
        stop_price=100.5,
        target_price=98.5,
    )
    engine = _engine(tmp_path, adapter, prior_snapshot=prior)

    snapshot = engine.start()

    assert snapshot.state is HulkSmashLiveState.OPEN
    assert snapshot.stop_oid == 201
    assert snapshot.target_oid == 202
    assert not any(
        name in {"market_entry", "stop", "target"} for name, _ in adapter.calls
    )


def test_hulk_engine_recovers_funding_from_owned_open_time_after_long_downtime(
    tmp_path: Path,
) -> None:
    opened_at = datetime(2026, 8, 1, 12, tzinfo=UTC)
    now = datetime(2026, 8, 4, 12, tzinfo=UTC)
    exposed = _venue(
        _position(size=-0.75, entry=100.0),
        orders=(_stop_order(), _target_order()),
    )
    adapter = FakeAdapter(
        [
            exposed,
            exposed,
            _venue(_position(size=-0.75, entry=100.0), orders=(_stop_order(),)),
            _venue(_position(), orders=(_stop_order(),)),
            _venue(_position()),
        ]
    )
    prior = HulkSmashLiveSnapshot(
        state=HulkSmashLiveState.STOPPED,
        entry_oid=101,
        stop_oid=201,
        target_oid=202,
        position_size_signed=-0.75,
        opened_at_ms=int(opened_at.timestamp() * 1_000),
        entry_price=100.0,
        stop_price=100.5,
        target_price=98.5,
    )
    engine = _engine(
        tmp_path,
        adapter,
        now_fn=lambda: now,
        prior_snapshot=prior,
    )
    engine.start()

    engine.poll_market()

    funding = next(payload for name, payload in adapter.calls if name == "funding")
    assert isinstance(funding, dict)
    assert funding["start_time_ms"] == prior.opened_at_ms
    assert engine.last_close_reason == "maximum_hold"


def test_hulk_engine_attributes_owned_target_filled_while_stopped(
    tmp_path: Path,
) -> None:
    target_fill = replace(
        _fill(202, "Close Short"),
        timestamp_ms=int(datetime(2026, 8, 1, 12, tzinfo=UTC).timestamp() * 1_000),
    )
    adapter = FakeAdapter([_venue(_position(), fills=(target_fill,))])
    prior = HulkSmashLiveSnapshot(
        state=HulkSmashLiveState.STOPPED,
        entry_oid=101,
        stop_oid=201,
        target_oid=202,
        position_size_signed=-0.75,
        opened_at_ms=1_785_549_600_000,
        entry_price=100.0,
        stop_price=100.5,
        target_price=98.5,
    )
    engine = _engine(tmp_path, adapter, prior_snapshot=prior)

    snapshot = engine.start()

    assert snapshot.state is HulkSmashLiveState.FLAT
    assert engine.last_close_reason == "target"
    records = HulkSmashLiveLedger(
        path=tmp_path / "data/live/hulk_smash/decisions.jsonl",
        profile_id="unused",
        profile_fingerprint="unused",
        run_fingerprint="unused",
        run_id="unused",
    ).read_all()
    closes = [record for record in records if record["event_type"] == "close"]
    assert closes[-1]["payload"] == {
        "reason": "target",
        "verified_flat": True,
        "oid": 202,
    }


def test_hulk_engine_refuses_flat_restart_without_owned_exit_fill(
    tmp_path: Path,
) -> None:
    adapter = FakeAdapter([_venue(_position())])
    prior = HulkSmashLiveSnapshot(
        state=HulkSmashLiveState.STOPPED,
        entry_oid=101,
        stop_oid=201,
        target_oid=202,
        position_size_signed=-0.75,
        opened_at_ms=1_785_549_600_000,
        entry_price=100.0,
        stop_price=100.5,
        target_price=98.5,
    )
    engine = _engine(tmp_path, adapter, prior_snapshot=prior)

    with pytest.raises(HulkSmashLiveEngineError, match="owned exit fill"):
        engine.start()

    assert engine.snapshot.state is HulkSmashLiveState.FAULTED


def test_hulk_engine_refuses_restart_when_target_price_does_not_match(
    tmp_path: Path,
) -> None:
    mismatched = replace(_target_order(), limit_price=98.4)
    exposed = _venue(
        _position(size=-0.75, entry=100.0),
        orders=(_stop_order(), mismatched),
    )
    adapter = FakeAdapter([exposed])
    prior = HulkSmashLiveSnapshot(
        state=HulkSmashLiveState.OPEN,
        entry_oid=101,
        stop_oid=201,
        target_oid=202,
        position_size_signed=-0.75,
        opened_at_ms=1_785_549_600_000,
        entry_price=100.0,
        stop_price=100.5,
        target_price=98.5,
    )
    engine = _engine(tmp_path, adapter, prior_snapshot=prior)

    with pytest.raises(HulkSmashLiveEngineError, match="does not match venue"):
        engine.start()

    assert engine.snapshot.state is HulkSmashLiveState.FAULTED


def _entered_engine(
    tmp_path: Path,
    *,
    now_fn: Callable[[], datetime] | None = None,
) -> tuple[FakeAdapter, HulkSmashLiveEngine]:
    flat = _venue(_position())
    opened = _venue(_position(size=-0.75, entry=100.0))
    stopped = _venue(_position(size=-0.75, entry=100.0), orders=(_stop_order(),))
    bracketed = _venue(
        _position(size=-0.75, entry=100.0),
        orders=(_stop_order(), _target_order()),
    )
    adapter = FakeAdapter([flat, flat, opened, stopped, bracketed])
    engine = _engine(tmp_path, adapter, now_fn=now_fn)
    engine.start()
    engine.enter(_decision())
    return adapter, engine


def _engine(
    tmp_path: Path,
    adapter: FakeAdapter,
    *,
    now_fn: Callable[[], datetime] | None = None,
    prior_snapshot: HulkSmashLiveSnapshot | None = None,
) -> HulkSmashLiveEngine:
    base = load_hulk_smash_live_config(
        "configs/hulk_smash_short_robust_v3_canary.toml",
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )
    path = tmp_path / "data/live/hulk_smash/decisions.jsonl"
    config = replace(base, backend_ledger=path)
    ledger = HulkSmashLiveLedger(
        path=path,
        profile_id=config.profile_id,
        profile_fingerprint=config.profile_fingerprint,
        run_fingerprint=config.run_fingerprint,
        run_id="hulk-live-test",
    )
    if prior_snapshot is not None:
        ledger.append(
            event_type="state_transition",
            observed_at_utc="2026-08-01T11:00:00+00:00",
            live_armed=True,
            execution_authority="hyperliquid_mainnet",
            payload=prior_snapshot.as_payload(),
        )
    identities = iter([f"0x{index:032x}" for index in range(1, 20)])
    return HulkSmashLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=now_fn or (lambda: datetime(2026, 8, 1, 12, tzinfo=UTC)),
        client_order_id_fn=lambda: next(identities),
        reconciliation_attempts=2,
        reconciliation_delay_seconds=0.0,
        sleep_fn=lambda _: None,
    )


def _decision() -> HulkSmashLiveDecision:
    return HulkSmashLiveDecision(
        decision_time_ms=1_785_549_600_000,
        bar_open_at=pd.Timestamp("2026-08-01T11:30:00Z"),
        reference_price=100.0,
        open_price=100.2,
        high_price=100.5,
        low_price=99.8,
        volume=100.0,
        candidate="hulk_rebuilt_expansion_v1",
        score=8,
        minimum_score=7,
        trigger="squeeze_release",
        evidence=("squeeze_release", "supertrend", "adx_usable"),
        stop_anchor=100.5,
        entry_eligible=True,
        reason="eligible",
    )


def _position(*, size: float = 0.0, entry: float | None = None) -> SolPositionSnapshot:
    return SolPositionSnapshot(
        size,
        entry,
        120.0 if size else None,
        abs(size * (entry or 0.0)) / 5.0,
        abs(size * (entry or 0.0)),
        0.0,
        "isolated" if size else None,
        5 if size else None,
    )


def _venue(
    position: SolPositionSnapshot,
    *,
    orders: tuple[SolOpenOrder, ...] = (),
    fills: tuple[SolFill, ...] = (),
) -> SolReconciliationSnapshot:
    account = SolAccountSnapshot(
        150.0,
        150.0 - position.margin_used_usd,
        position.margin_used_usd,
        position.position_value_usd,
        position,
    )
    return SolReconciliationSnapshot(account, orders, fills)


def _preflight(position: SolPositionSnapshot) -> SolVenuePreflight:
    return SolVenuePreflight(
        SolMarketMetadata("BTC", 5, 40),
        100.0,
        0.1,
        0.00001,
        HyperliquidFeeSchedule(0.00015, 0.00045),
        150.0,
        150.0,
        position,
    )


def _stop_order() -> SolOpenOrder:
    return SolOpenOrder(201, 0.75, 0.75, "B", True, True, 100.5, "Stop Market", 1)


def _target_order() -> SolOpenOrder:
    return SolOpenOrder(202, 0.75, 0.75, "B", True, False, None, "Limit", 1, 98.5)


def _fill(oid: int, direction: str) -> SolFill:
    return SolFill(
        oid,
        98.5,
        0.75,
        "B",
        2,
        0.01,
        "USDC",
        1.0,
        False,
        direction,
        "tx",
        oid + 10_000,
    )


def _ack(oid: int) -> HyperliquidOrderAck:
    return HyperliquidOrderAck(True, oid, "accepted")


def _book() -> SolBookSnapshot:
    bid = SolBookLevel(99.9, 1.0, 1)
    ask = SolBookLevel(100.1, 1.0, 1)
    return SolBookSnapshot(1, (bid,), (ask,), 100.0, 20.0, 1.0, 1.0, 0.0)
